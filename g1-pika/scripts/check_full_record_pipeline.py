"""GPU-only archived RGB -> ACT -> upstream IK -> ZMQ -> SONIC, no robot IO."""
import argparse
import base64
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parent))
from runtime_config import load
from record_session import RecordSession
from sonic_process import JsonProcess,SonicProcess
from zmq_transport import ZmqChannel


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('config','record','images','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--rate-check',action='store_true')
    parser.add_argument('--rate-seconds',type=int,choices=range(1,31),default=1)
    parser.add_argument('--measured-state',type=Path)
    parser.add_argument('--online-fixture',action='store_true')
    parser.add_argument('--joint-interpolation-seconds',type=float,choices=(.2,.4,.8))
    args=parser.parse_args(); config=load(args.config)
    if args.online_fixture:
        from check_online_fixture_pipeline import run
        return run(config,args.record,args.images,args.output,seconds=args.rate_seconds,
                   joint_interpolation_s=args.joint_interpolation_seconds)
    if args.joint_interpolation_seconds is not None:
        parser.error('Joint interpolation requires --online-fixture')
    if args.measured_state:
        from check_measured_record_pipeline import run
        return run(config,args.measured_state,args.output)
    args.output.mkdir(exist_ok=False)
    source=Path(__file__).resolve().parent; stage=source.parent
    record=json.loads(args.record.read_text())
    if not record['passed'] or len(record['frames'])!=30: raise ValueError('Expected original 30-frame record')
    logs=[]; children=[]; rows=[]; errors=[]; ready=threading.Event(); thread=None; client=None
    def log(name):
        file=(args.output/(name+'.stderr.log')).open('w'); logs.append(file); return file
    report=dict(passed=False,hardware_ready=False,robot_commands_sent=False,g1_connected=False,
                scope='archived_RGB_ACT_IK_ZMQ_SONIC_all_on_GPU_PC',source_frames=[0,29],
                observation_history='repeated_snapshots_not_real_50Hz',source_sha256=hashlib.sha256(args.record.read_bytes()).hexdigest())
    try:
        root=Path(config['gpu_root']); ikroot=Path(config['ik_deployment']); models=Path(config['sonic_models'])
        actor=JsonProcess([root/'.venv-gpu/bin/python','-I',source/'probe_gpu_images.py','--root',root,
                           '--policy-bundle',source/'policy-bundle.json',
                           '--images',args.output,'--packet-width','--stream','--frames',
                           str(30*args.rate_seconds) if args.rate_check else '2','--warmup-steps','3'],log('act'),startup_timeout=90)
        children.append(actor)
        report['act_provenance']=actor.ready
        report['act_synthetic_warmup_steps']=actor.ready.get('synthetic_warmup_steps',0)
        if actor.ready['model_sha256']!=record['gpu']['model_sha256']: raise ValueError('ACT checkpoint mismatch')
        ik=JsonProcess([ikroot/'.venv/bin/python','-I',source/'sonic_ik_worker.py','--urdf',
                        ikroot/'artifacts/models/g1_pika_closed.urdf'],log('ik'))
        children.append(ik)
        if ik.ready!=dict(ready=True,mode='archived_record_only',hardware_output_enabled=False): raise ValueError('IK handshake')
        sonic=SonicProcess(stage/'sonic_offline_infer',models/'model_encoder.onnx',models/'model_decoder.onnx',log('sonic'))
        children.append(sonic)
        if args.rate_check:
            from rate_record_check import run_rate_check
            metrics=run_rate_check(actor,ik,sonic,record,args.images,config,seconds=args.rate_seconds)
            rows=metrics.pop('outputs'); report.update(metrics); report['passed']=True
            return 0
        with tempfile.TemporaryDirectory(prefix='g1-pika-full-record-') as directory:
            endpoint='ipc://'+str(Path(directory)/'sonic.sock')
            def serve():
                channel=None
                try:
                    channel=ZmqChannel(endpoint,server=True,timeout_ms=15000,max_message_bytes=2000000)
                    ready.set(); hello=channel.read()
                    if hello.get('mode')!='record_only' or hello.get('schema')!=1: raise ValueError('Hello schema')
                    session=hello['session']; expected=0
                    channel.send(dict(ready=True,session=session,schema=1,mode='record_only',hardware_output_enabled=False))
                    while expected<=2:
                        message=channel.read()
                        if message.get('session')!=session: raise ValueError('Session mismatch')
                        if message.get('op')=='stop':
                            sonic.stop(); channel.send(dict(stopped=True,session=session)); break
                        if message.get('op')!='record' or message.get('seq')!=expected: raise ValueError('Sequence mismatch')
                        output=sonic.infer(message['payload'])
                        channel.send(dict(session=session,seq=expected,result=output,hardware_output_enabled=False))
                        expected+=1
                except BaseException as exc: errors.append(type(exc).__name__+': '+str(exc))
                finally:
                    ready.set(); sonic.close()
                    if channel: channel.close()
            thread=threading.Thread(target=serve); thread.start()
            if not ready.wait(3): raise RuntimeError('ZMQ server startup timeout')
            # This gate covers the generated SONIC request, NOT original capture age or complete ACT/IK latency.
            client=RecordSession(ZmqChannel(endpoint,timeout_ms=1000),str(uuid.uuid4()),config['diagnostic_deadlines'])
            client.start()
            for seq,index in enumerate((0,29)):
                frame=copy.deepcopy(record['frames'][index]); packet=copy.deepcopy(frame['capture']); packet['seq']=seq
                for role,image in packet['images'].items():
                    blob=(args.images/f'{index:02d}-{role}.jpg').read_bytes()
                    if hashlib.sha256(blob).hexdigest()!=image['sha256']: raise ValueError('Image SHA mismatch')
                    image['jpeg']=base64.b64encode(blob).decode()
                started=time.monotonic(); actor.send(packet); action=actor.read(timeout=5)
                if action['seq']!=seq: raise ValueError('ACT sequence mismatch')
                frame.update(action); frame['capture']['seq']=seq
                ik.send(dict(op='infer',seq=seq,frame=frame)); candidate=ik.read(timeout=5)
                if candidate['seq']!=seq or candidate.get('hardware_output_enabled') is not False: raise ValueError('IK identity/mode')
                # Earlier stages can take >tick_gap: use one explicit session per stream, and query only when ready.
                result=client.query(seq,candidate['result'],source_age_s=0.)
                if result.get('gripper_actuated') is not False or result.get('gripper_width_m')!=action['action'][9]:
                    raise ValueError('Width channel mismatch')
                rows.append(dict(seq=seq,source_frame=index,action=action,ik=candidate['result']['ik'],sonic=result,
                                 archived_pipeline_wall_ms=(time.monotonic()-started)*1000))
            client.stop(); thread.join(3)
            if thread.is_alive() or errors: raise RuntimeError(str(errors))
        actor.send({'stop':True})
        if actor.process.wait(timeout=5)!=0: raise RuntimeError('ACT worker failed')
        ik.send(dict(op='stop'))
        if ik.read()!=dict(stopped=True) or ik.process.wait(timeout=5)!=0: raise RuntimeError('IK worker failed')
        report['passed']=True
    except Exception as exc: report['error']=type(exc).__name__+': '+str(exc)
    finally:
        if client: client.close()
        for child in children: child.close()
        if thread: thread.join(16)
        for file in logs: file.close()
        report.update(outputs=rows,worker_exit_codes=[child.process.returncode for child in children],worker_errors=errors)
        (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps({k:v for k,v in report.items() if k not in ('outputs','policy_records')},indent=2))
    return 0 if report['passed'] else 1


if __name__=='__main__': raise SystemExit(main())
