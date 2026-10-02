"""GPU-local ZMQ IPC -> persistent real SONIC inference; output to JSON only."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parent))
from sonic_process import SonicProcess
from record_session import RecordSession
from runtime_config import load
from zmq_transport import ZmqChannel


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for field in ('binary','encoder','decoder','input','baseline','report','config'):
        parser.add_argument('--'+field,type=Path,required=True)
    args=parser.parse_args()
    if args.report.exists(): raise ValueError('Report exists')
    config=load(args.config)
    request=json.loads(args.input.read_text()); baseline=json.loads(args.baseline.read_text())
    if request['source_sha256']!=baseline['source_sha256']: raise ValueError('Baseline source mismatch')
    errors=[]; rows=[]; timings=[]; ready=threading.Event(); process=None
    with args.report.with_suffix('.stderr.log').open('w') as log, tempfile.TemporaryDirectory(prefix='sonic-service-') as folder:
        process=SonicProcess(args.binary,args.encoder,args.decoder,log)
        endpoint='ipc://'+str(Path(folder)/'sonic.sock')
        def serve():
            channel=None
            try:
                channel=ZmqChannel(endpoint,server=True,timeout_ms=2000,max_message_bytes=2000000)
                ready.set(); hello=channel.read()
                if hello.get('op')!='hello' or hello.get('mode')!='record_only' or hello.get('schema')!=1:
                    raise ValueError('Invalid session hello')
                session=hello['session']; seq=0
                channel.send(dict(ready=True,session=session,schema=1,mode='record_only',hardware_output_enabled=False))
                while seq<=len(request['frames']):
                    message=channel.read()
                    if message.get('session')!=session: raise ValueError('Session mismatch')
                    if message.get('op')=='stop':
                        process.stop(); channel.send(dict(stopped=True,session=session)); break
                    if message.get('op')!='record' or type(message.get('seq')) is not int or message['seq']!=seq:
                        raise ValueError('Sequence mismatch')
                    output=process.infer(message['payload'])
                    channel.send(dict(session=session,seq=seq,result=output,hardware_output_enabled=False))
                    seq+=1
            except BaseException as exc: errors.append(type(exc).__name__+': '+str(exc))
            finally:
                ready.set(); process.close()
                if channel: channel.close()
        thread=threading.Thread(target=serve); thread.start()
        if not ready.wait(3): raise RuntimeError('Server startup timeout')
        client=RecordSession(ZmqChannel(endpoint,timeout_ms=1000),str(uuid.uuid4()),config['diagnostic_deadlines'])
        try:
            client.start()
            for seq,row in enumerate(request['frames']):
                before=time.monotonic(); rows.append(client.query(seq,row,source_age_s=0.))
                timings.append((time.monotonic()-before)*1000)
            client.stop()
        finally:
            client.close(); thread.join(4)
            if thread.is_alive(): process.close(); thread.join(3)
        if errors or thread.is_alive(): raise RuntimeError(str(errors))
    if len(rows)!=len(baseline['outputs']): raise ValueError('Result count mismatch')
    differences=[]
    for actual,expected in zip(rows,baseline['outputs']):
        if actual['seq']!=expected['seq']: raise ValueError('Capture identity mismatch')
        differences.extend(abs(a-b) for a,b in zip(actual['q_target_hardware'],expected['q_target_hardware']))
        if actual.get('gripper_width_m')!=expected.get('gripper_width_m'): raise ValueError('Width changed')
    report=dict(passed=max(differences)<1e-6 and process.process.poll()==0,
        scope='GPU_local_IPC_persistent_SONIC_inference_on_saved_inputs',
        freshness_scope='local_request_age_not_original_capture_age',
        hardware_ready=False,robot_commands_sent=False,g1_connected=False,
        model_loaded_once=True,worker_exit_code=process.process.returncode,
        max_batch_target_difference_rad=max(differences),roundtrip_ms=timings,outputs=rows)
    args.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='outputs'},indent=2))
    return 0 if report['passed'] else 1


if __name__=='__main__': raise SystemExit(main())
