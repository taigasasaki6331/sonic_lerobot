"""IPC fault injection with saved SONIC outputs, never live robot observations."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parent))
from record_worker import RecordWorker
from record_session import RecordSession
from runtime_config import load
from zmq_transport import ZmqChannel


def case(request, result, fault):
    with tempfile.TemporaryDirectory(prefix='sonic-record-ipc-') as folder:
        endpoint='ipc://'+str(Path(folder)/'record.sock')
        ready=threading.Event(); server_errors=[]
        def serve():
            channel=None
            try:
                worker=RecordWorker(request,result)
                channel=ZmqChannel(endpoint,server=True,timeout_ms=500,max_message_bytes=2000000)
                ready.set()
                while worker.phase not in ('stopped','fault'):
                    message=channel.read(); response=worker.handle(message)
                    if message['op']=='record':
                        if fault=='disconnect': break
                        if fault=='wrong_session': response['session']='old-session'
                        if fault=='wrong_sequence': response['seq']+=1
                        if fault=='hardware_flag': response['hardware_output_enabled']=True
                        if fault=='late': time.sleep(.12)
                    channel.send(response)
                    if fault!='none' and message['op']=='record': break
            except BaseException as exc: server_errors.append(type(exc).__name__+': '+str(exc))
            finally:
                ready.set()
                if channel: channel.close()
        thread=threading.Thread(target=serve); thread.start()
        if not ready.wait(3): raise RuntimeError('IPC worker startup timeout')
        client=RecordSession(ZmqChannel(endpoint,timeout_ms=250),str(uuid.uuid4()),load()['diagnostic_deadlines'])
        accepted=0; error=None
        try:
            client.start()
            for seq in range(len(result['outputs'])):
                row=client.query(seq,{'source':'saved_record_replay'},source_age_s=0.)
                if row!=result['outputs'][seq]: raise ValueError('Result changed during transport')
                accepted+=1
            client.stop()
        except (OSError,ValueError,RuntimeError) as exc:
            error=type(exc).__name__+': '+str(exc)
        finally:
            client.close(); thread.join(3)
        passed=(not server_errors and not thread.is_alive() and client.closed and
                ((fault=='none' and error is None and accepted==len(result['outputs']) and client.gate.phase=='stopped')
                 or (fault!='none' and error is not None and accepted==0 and client.gate.phase=='fault')))
        return dict(fault=fault,passed=passed,accepted=accepted,error=error,server_errors=server_errors,
                    thread_exited=not thread.is_alive(),status=client.gate.status())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--results',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    if args.report.exists(): raise ValueError('Report already exists')
    request=json.loads(args.input.read_text()); result=json.loads(args.results.read_text())
    cases=[case(request,result,fault) for fault in ('none','wrong_session','wrong_sequence','hardware_flag','late','disconnect')]
    report=dict(passed=all(c['passed'] for c in cases),scope='IPC_saved_output_fault_injection',
                freshness_scope='local_replay_envelope_age_not_original_capture_freshness',
                robot_commands_sent=False,g1_connected=False,physical_stop_validated=False,cases=cases)
    args.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return 0 if report['passed'] else 1


if __name__=='__main__': raise SystemExit(main())
