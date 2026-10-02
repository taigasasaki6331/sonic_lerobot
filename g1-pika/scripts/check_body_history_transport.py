"""No-device tests; --ipc additionally opens only a temporary local IPC socket."""
import copy
from pathlib import Path
import sys
import json
import select
import subprocess
import time
import tempfile
import threading
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from body_history_transport import BodyHistoryBuffer,BodyHistoryServer,BodyHistoryClient

IPC='--ipc' in sys.argv
if IPC: sys.argv.remove('--ipc')


def frames():
    return [dict(q=[0]*35,dq=[0]*35,quaternion=[1,0,0,0],gyroscope=[0]*3,
                 tick=i,receive_monotonic_s=10000+i*.02) for i in range(10)]


class Loopback:
    def __init__(self,server): self.server=server; self.closed=False
    def send(self,request): self.response=self.server.handle(request)
    def read(self): return self.response
    def close(self): self.closed=True


class Tests(unittest.TestCase):
    def setUp(self):
        self.buffer=BodyHistoryBuffer(clock=lambda:10000.185)
        for frame in frames(): self.buffer.push(frame)
        self.server=BodyHistoryServer(self.buffer)
        self.channel=Loopback(self.server)

    def test_different_clock_origins(self):
        ticks=iter([2.,2.01]); client=BodyHistoryClient(self.channel,'session',clock=lambda:next(ticks))
        client.start(); result=client.read(); client.stop()
        self.assertAlmostEqual(result['source_age_s'],.015)
        self.assertEqual(result['received_at'],2.01)
        self.assertEqual(result['body_history'],frames())
        self.assertTrue(self.channel.closed)

    def test_transport_delay_rejected(self):
        ticks=iter([2.,2.2]); client=BodyHistoryClient(self.channel,'session',clock=lambda:next(ticks))
        client.start()
        with self.assertRaises(ValueError): client.read()
        self.assertEqual(client.phase,'fault'); self.assertTrue(self.channel.closed)

    def test_buffer_copy(self):
        result,_=self.buffer.snapshot(); result[0]['q'][0]=999
        self.assertEqual(self.buffer.snapshot()[0][0]['q'][0],0)

    def test_no_repeated_frame(self):
        with self.assertRaises(TimeoutError): self.buffer.snapshot(previous_tick=9,timeout_s=.001)

    def test_small_request_delay_does_not_skip_real_samples(self):
        for tick in (10,11):
            frame=copy.deepcopy(frames()[-1]); frame.update(tick=tick,receive_monotonic_s=10000+tick*.02)
            self.buffer.push(frame)
        self.buffer.clock=lambda:10000.225
        first,age=self.buffer.snapshot(previous_tick=9)
        second,_=self.buffer.snapshot(previous_tick=10)
        self.assertEqual(first[-1]['tick'],10); self.assertEqual(second[-1]['tick'],11)
        self.assertEqual(first[1:],second[:-1]); self.assertAlmostEqual(age,.025)
        self.buffer.clock=lambda:10001.
        with self.assertRaises(ValueError): self.buffer.snapshot(previous_tick=9)

    def test_history_eviction_is_not_filled_or_skipped(self):
        for tick in range(10,35):
            frame=copy.deepcopy(frames()[-1]); frame.update(tick=tick,receive_monotonic_s=10000+tick*.02)
            self.buffer.push(frame)
        self.buffer.clock=lambda:10000.69
        with self.assertRaises(ValueError): self.buffer.snapshot(previous_tick=9)

    def test_partial_history(self):
        buffer=BodyHistoryBuffer()
        buffer.push(frames()[0])
        with self.assertRaises(TimeoutError): buffer.snapshot(timeout_s=.001)

    def test_active_bad_window_rejected(self):
        frame=copy.deepcopy(frames()[-1]); frame['receive_monotonic_s']+=.1; frame['tick']+=1
        self.buffer.push(frame)
        with self.assertRaises(ValueError): self.buffer.snapshot()

    def test_invalid_measurement_latches(self):
        frame=copy.deepcopy(frames()[-1]); frame['q'][0]=float('nan')
        with self.assertRaises(ValueError): self.buffer.push(frame)
        with self.assertRaises(RuntimeError): self.buffer.snapshot()

    def test_warmup_waits_for_genuine_valid_window(self):
        buffer=BodyHistoryBuffer(clock=lambda:10000.5)
        sample=frames()
        sample[0]['receive_monotonic_s']-=.1
        for frame in sample: buffer.push(frame)
        def complete():
            time.sleep(.005)
            for i in range(10):
                frame=copy.deepcopy(sample[-1]); frame['tick']=10+i
                frame['receive_monotonic_s']=10000.32+i*.02; buffer.push(frame)
        thread=threading.Thread(target=complete); thread.start()
        try:
            history,_=buffer.warmup()
            self.assertEqual([f['tick'] for f in history],list(range(10,20)))
        finally: thread.join(1)

    def test_closed_buffer(self):
        self.buffer.close()
        with self.assertRaises(RuntimeError): self.buffer.snapshot()

    def test_stale_buffer(self):
        self.buffer.clock=lambda:10001
        with self.assertRaises(ValueError): self.buffer.snapshot()

    def test_wrong_session_latches(self):
        self.server.handle(dict(op='hello',session='a',schema=1))
        with self.assertRaises(ValueError): self.server.handle(dict(op='read',session='b',seq=0))
        self.assertTrue(self.server.closed)

    def test_sequence_and_bool_rejected(self):
        for sequence in (1,False,-1):
            server=BodyHistoryServer(self.buffer); server.handle(dict(op='hello',session='a',schema=1))
            with self.assertRaises(ValueError): server.handle(dict(op='read',session='a',seq=sequence))

    @unittest.skipUnless(IPC,'Local IPC is enabled separately')
    def test_real_ipc(self):
        from zmq_transport import ZmqChannel
        errors=[]; ready=threading.Event()
        with tempfile.TemporaryDirectory(prefix='body-history-check-') as folder:
            endpoint='ipc://'+str(Path(folder)/'body.sock')
            def serve():
                channel=None
                try:
                    channel=ZmqChannel(endpoint,server=True,timeout_ms=1000)
                    ready.set()
                    while not self.server.closed: channel.send(self.server.handle(channel.read()))
                except Exception as exc: errors.append(str(exc))
                finally:
                    ready.set()
                    if channel: channel.close()
            thread=threading.Thread(target=serve); thread.start()
            client=None
            try:
                self.assertTrue(ready.wait(2)); self.assertFalse(errors)
                client=BodyHistoryClient(ZmqChannel(endpoint,timeout_ms=1000),'ipc')
                client.start(); self.assertEqual(len(client.read()['body_history']),10); client.stop()
            finally:
                if client: client.close()
                thread.join(2)
            self.assertFalse(thread.is_alive()); self.assertFalse(errors)

    @unittest.skipUnless(IPC,'Local IPC is enabled separately')
    def test_real_stdin_service_process(self):
        from zmq_transport import ZmqChannel
        with tempfile.TemporaryDirectory(prefix='body-service-check-') as folder, tempfile.TemporaryFile() as log:
            endpoint='ipc://'+str(Path(folder)/'service.sock')
            child=subprocess.Popen([sys.executable,'-I',str(Path(__file__).with_name('body_history_service.py')),
                '--endpoint',endpoint,'--max-frames','1','--seconds','10'],
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log)
            client=None
            try:
                # Protocol fixture only: timestamps are synthesized, no physical state is sampled.
                fixture=frames(); now=time.monotonic()
                for i,frame in enumerate(fixture): frame['receive_monotonic_s']=now+(i-9)*.02
                child.stdin.write((''.join(json.dumps(frame)+'\n' for frame in fixture)).encode()); child.stdin.flush()
                self.assertTrue(select.select([child.stdout],[],[],3)[0])
                ready=json.loads(child.stdout.readline()); self.assertTrue(ready['ready'])
                client=BodyHistoryClient(ZmqChannel(endpoint,timeout_ms=1000),'process')
                client.start(); self.assertEqual(client.read()['body_history'],fixture); client.stop()
                self.assertEqual(child.wait(timeout=3),0)
            finally:
                if client: client.close()
                if child.poll() is None:
                    child.terminate()
                    try: child.wait(timeout=2)
                    except subprocess.TimeoutExpired: child.kill(); child.wait(timeout=2)
                child.stdin.close(); child.stdout.close()


if __name__=='__main__': unittest.main()
