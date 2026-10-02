"""Persistent SONIC C++ child over bounded JSON pipes; no SDK/device imports."""
import json
import math
import os
import select
import subprocess
import time


def strict_message(line):
    """Reject ambiguous/non-finite worker messages, including float overflow."""
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate worker JSON key')
            result[key] = value
        return result

    def validate(value):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError('Non-finite worker JSON number')
        if isinstance(value, dict):
            for item in value.values(): validate(item)
        elif isinstance(value, list):
            for item in value: validate(item)

    value = json.loads(line, object_pairs_hook=pairs)
    if not isinstance(value, dict): raise ValueError('Worker message must be an object')
    validate(value)
    return value


class JsonProcess:
    def __init__(self, command, log, startup_timeout=30):
        self.process=subprocess.Popen(list(map(str,command)),
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,bufsize=0)
        self.buffer=b''; self.sequence=0
        os.set_blocking(self.process.stdin.fileno(),False)
        try:
            self.ready=self.read(startup_timeout)
            if self.ready.get('ready') is not True: raise ValueError('Worker not ready')
        except BaseException:
            self.close(); raise

    def send(self, value, timeout=.5):
        remaining=(json.dumps(value,allow_nan=False)+'\n').encode()
        if len(remaining)>2000000: raise ValueError('Oversized pipe request')
        end=time.monotonic()+timeout
        while remaining:
            wait=end-time.monotonic()
            if wait<=0 or not select.select([],[self.process.stdin],[],wait)[1]: raise TimeoutError('JSON worker pipe send timeout')
            try: count=os.write(self.process.stdin.fileno(),remaining)
            except BlockingIOError: continue
            if count<=0: raise RuntimeError('JSON worker pipe closed')
            remaining=remaining[count:]

    def read(self, timeout=.5):
        end=time.monotonic()+timeout
        while b'\n' not in self.buffer:
            wait=end-time.monotonic()
            if wait<=0 or not select.select([self.process.stdout],[],[],wait)[0]: raise TimeoutError('JSON worker pipe read timeout')
            chunk=os.read(self.process.stdout.fileno(),65536)
            if not chunk: raise RuntimeError('JSON worker exited; inspect its stderr log')
            self.buffer+=chunk
            if len(self.buffer)>2000000: raise ValueError('Oversized pipe response')
        line,self.buffer=self.buffer.split(b'\n',1)
        return strict_message(line)

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try: self.process.wait(timeout=2)
            except subprocess.TimeoutExpired: self.process.kill(); self.process.wait(timeout=2)
        for pipe in (self.process.stdin,self.process.stdout):
            if not pipe.closed: pipe.close()


class SonicProcess(JsonProcess):
    def __init__(self,binary,encoder,decoder,log):
        super().__init__([binary,'--stdio',encoder,decoder],log)
        if self.ready!=dict(ready=True,mode='record_only',hardware_output_enabled=False):
            self.close(); raise ValueError('Unexpected SONIC worker handshake')

    def infer(self,row):
        try:
            self.send(dict(op='infer',seq=self.sequence,row=row))
            response=self.read()
            if type(response.get('seq')) is not int or response['seq']!=self.sequence or response.get('hardware_output_enabled') is not False:
                raise ValueError('SONIC response identity/mode')
            if not isinstance(response.get('result'),dict): raise ValueError('SONIC result schema')
            self.sequence+=1
            return response['result']
        except BaseException:
            # A late response must never be consumed as a later request's output.
            self.close()
            raise

    def stop(self):
        try:
            self.send(dict(op='stop'))
            if self.read()!=dict(stopped=True): raise ValueError('SONIC stop acknowledgement')
            if self.process.wait(timeout=3)!=0: raise RuntimeError('SONIC exited with error')
        finally: self.close()
