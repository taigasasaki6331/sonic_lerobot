"""Persistent measured-history assembler over stdin/stdout, no device/socket IO."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from sonic_measured_stream import MeasuredStream
from sonic_process import strict_message


def main():
    stream=None
    print(json.dumps(dict(ready=True,mode='measured_record_only',hardware_output_enabled=False)),flush=True)
    try:
        for count in range(100000):
            line=sys.stdin.buffer.readline(2000001)
            if not line: break
            if len(line)>2000000 or not line.endswith(b'\n'): raise ValueError('Oversized/truncated request')
            request=strict_message(line); op=request.pop('op')
            if op=='start':
                if stream is not None: raise ValueError('Already started')
                stream=MeasuredStream(**request); result=dict(started=True)
            elif op=='stop':
                if stream is not None: stream.stop()
                print(json.dumps(dict(stopped=True)),flush=True); return
            else:
                if stream is None: raise ValueError('Not started')
                if op=='reference': stream.reference_update(**request); result=dict(accepted=True)
                elif op=='observe': result=stream.observe(**request)
                elif op=='commit': stream.commit(**request); result=dict(committed=True)
                else: raise ValueError('Unknown observation operation')
            print(json.dumps(dict(result=result,hardware_output_enabled=False),allow_nan=False),flush=True)
    finally:
        if stream is not None: stream.stop()


if __name__=='__main__': main()
