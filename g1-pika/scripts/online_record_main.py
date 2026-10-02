"""GPU-side bounded input-only online diagnostic. Requires explicit read consent."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from runtime_config import load
from online_record_config import load_online
from online_input_sources import InputSources
from online_record_loop import run_online_loop
from sonic_process import JsonProcess,SonicProcess
from body_history_transport import BodyHistoryClient
from zmq_transport import ZmqChannel
from record_capture import archive_capture,archive_body
import uuid


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('config','online-config','access-config','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--allow-device-read',action='store_true')
    parser.add_argument('--joint-interpolation-seconds',type=float,choices=(.2,.4,.8))
    parser.add_argument('--body-runtime',action='store_true',help='Connect record-only native G1 runtime; NEVER actuator output')
    args=parser.parse_args()
    if not args.allow_device_read: parser.error('Explicit camera/serial/body read consent is required; serial open may reset MCU')
    config=load(args.config); online=load_online(args.online_config)
    access=json.loads(args.access_config.read_text()); args.output.mkdir(exist_ok=False)
    source=Path(__file__).resolve().parent; stage=source.parent
    children=[]; logs=[]; sources=None; camera=None; body=None; body_sink=None
    report=dict(passed=False,scope='online_measured_inputs_SONIC_record_only',hardware_ready=False,robot_commands_sent=False)
    def log(name):
        file=(args.output/(name+'.stderr.log')).open('w'); logs.append(file); return file
    try:
        root=Path(config['gpu_root']); ikroot=Path(config['ik_deployment']); models=Path(config['sonic_models'])
        actor=JsonProcess([root/'.venv-gpu/bin/python','-I',source/'probe_gpu_images.py','--root',root,
            '--policy-bundle',source/'policy-bundle.json',
            '--images',args.output,'--packet-width','--stream','--frames',str(30*online['seconds']+3),
            '--warmup-steps','3'],log('act'),startup_timeout=90); children.append(actor)
        if actor.ready.get('model_sha256')!=online['act_model_sha256']: raise ValueError('Online ACT checkpoint mismatch')
        ik=JsonProcess([ikroot/'.venv/bin/python','-I',source/'sonic_ik_worker.py','--urdf',
            ikroot/'artifacts/models/g1_pika_closed.urdf','--input-mode','measured'],log('ik')); children.append(ik)
        observer=JsonProcess([root/'.venv-gpu/bin/python','-I',source/'sonic_observation_worker.py'],log('observation')); children.append(observer)
        sonic=SonicProcess(stage/'sonic_offline_infer',models/'model_encoder.onnx',models/'model_decoder.onnx',log('sonic')); children.append(sonic)
        # Device acquisition begins only AFTER all inference workers are ready.
        package=stage/'body-runtime-package' if args.body_runtime else None
        sources=InputSources(source,access,online,log,audit=report,body_runtime_package=package,
            body_runtime_report=args.output/'body-runtime-report.json' if args.body_runtime else None)
        camera=ZmqChannel(online['camera_endpoint'],timeout_ms=200)
        body=BodyHistoryClient(ZmqChannel(online['body_endpoint'],timeout_ms=1500),str(uuid.uuid4()))
        if args.body_runtime:
            from sonic_body_bridge import BodyRecordClient
            from record_session import RecordSession
            profile=json.loads((package/'runtime/profile.json').read_bytes())
            body_sink=BodyRecordClient(RecordSession(ZmqChannel('tcp://192.0.2.11:6077',timeout_ms=1000,max_message_bytes=65536),
                str(uuid.uuid4()),dict(max_source_age_s=.1,max_roundtrip_s=.1,max_tick_gap_s=.1)),profile['names'])
        report=run_online_loop(actor,ik,observer,sonic,camera,body,seconds=online['seconds'],
                               joint_interpolation_s=args.joint_interpolation_seconds,
                               body_sink=body_sink,
                               capture_recorder=lambda packet: archive_capture(args.output,packet),
                               body_recorder=lambda seq,history: archive_body(args.output,seq,history))
        report['act_provenance']=actor.ready
        if report['passed']: report['source_exit_codes']=sources.wait()
    except Exception as exc:
        report.update(passed=False,error=type(exc).__name__+': '+str(exc))
    finally:
        if camera: camera.close()
        if body: body.close()
        if body_sink: body_sink.close()
        if sources:
            sources.close(); report['source_directory']=sources.directory
            report['source_cleanup']=sources.cleanup
            if not sources.cleanup or sources.cleanup.get('confirmed') is not True:
                report.update(passed=False,cleanup_error='Remote input process shutdown not confirmed')
            report['source_process_exit_codes']=[child.process.returncode for child in sources.children]
            if args.body_runtime:
                report.update(body_runtime_build=sources.runtime_build,
                    body_runtime_report_recovered=sources.runtime_report_recovered)
                if not sources.runtime_report_recovered: report['passed']=False
        for child in children: child.close()
        for file in logs: file.close()
        report.update(worker_exit_codes=[child.process.returncode for child in children],configuration=online,
                      body_runtime_mode='record_only_native_memory' if args.body_runtime else 'disabled',
                      remote_input_timeout_s=90,remote_exit_on_failure='not_confirmed_by_SSH_termination')
        (args.output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
        print(json.dumps({k:v for k,v in report.items() if k not in ('outputs','policy_records','policy_timings','body_timings')},indent=2))
    return 0 if report['passed'] else 1


if __name__=='__main__': raise SystemExit(main())
