"""Default: GPU-only archive diagnostics. Explicit online mode opens G1 inputs.

--online-config additionally requires --allow-device-read. No mode sends motor
commands. G1 input acquisition remains a separate, explicitly authorized step.
"""
import argparse
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parent))
from runtime_config import load,DEFAULT,ssh_options
from run_state_shadow import directory,run
from recover_outputs import recover


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=DEFAULT)
    parser.add_argument('--rate-check',action='store_true')
    parser.add_argument('--rate-seconds',type=int,choices=range(1,31),default=1)
    parser.add_argument('--measured-state',type=Path)
    parser.add_argument('--online-fixture',action='store_true',help='Synthetic input IO, real GPU models; never connects to G1')
    parser.add_argument('--joint-interpolation-seconds',type=float,choices=(.2,.4,.8),help='Optional record-only joint lookahead; not a balance planner')
    parser.add_argument('--online-config',type=Path,help='Explicit input-only live mode; connects to G1')
    parser.add_argument('--allow-device-read',action='store_true',help='Acknowledge camera/serial/body reads; serial open may reset MCU')
    parser.add_argument('--body-runtime',action='store_true',help='Include G1 native record-only INIT/writer/stop; requires online mode')
    parser.add_argument('--online-seconds',type=int,choices=range(1,31),help='Override duration in staged online config only')
    parser.add_argument('--record',type=Path,default=Path('artifacts/state-shadow/state-shadow-Pysyga/live-report.json'))
    parser.add_argument('--gpu-images',default='/home/gpu-user/g1-pika-training/artifacts/live-shadow/run-1c31drlw')
    args=parser.parse_args(); config=load(args.config)
    if args.body_runtime and not args.online_config: parser.error('--body-runtime requires --online-config; never a hardware-output mode')
    if args.online_seconds is not None and not args.online_config: parser.error('--online-seconds requires --online-config')
    if args.joint_interpolation_seconds is not None and not (args.online_fixture or args.online_config):
        parser.error('Joint interpolation requires --online-fixture or --online-config')
    if args.online_config:
        if not args.allow_device_read: parser.error('Online mode requires explicit --allow-device-read; no G1 connection made')
        if args.measured_state or args.rate_check or args.online_fixture: parser.error('Online and archive modes cannot be mixed')
        from online_record_config import load_online
        load_online(args.online_config)
    elif args.allow_device_read: parser.error('--allow-device-read requires --online-config')
    if sum(bool(v) for v in (args.measured_state,args.rate_check,args.online_fixture))>1: parser.error('Choose one archive diagnostic mode')
    if args.measured_state and not args.measured_state.is_file(): parser.error('Measured archive does not exist')
    # Validate the local archive before allocating any remote deployment.
    if not args.online_config and not args.measured_state and not args.record.is_file(): parser.error('Record file does not exist: '+str(args.record))
    root=Path(__file__).resolve().parents[1]; source=root/'scripts'
    from policy_bundle import verify
    policy_bundle=verify(root,root/'config/policy-bundle.json') if not args.measured_state else None
    parent=root/'artifacts/full-record'; parent.mkdir(parents=True,exist_ok=True)
    local=Path(tempfile.mkdtemp(prefix='run-',dir=parent))
    (local/'config.json').write_text(json.dumps(config,indent=2)+'\n')
    if policy_bundle:
        (local/'policy-bundle-check.json').write_text(json.dumps(policy_bundle,indent=2)+'\n')
    gpu=config['gpu_host']; opts=ssh_options(config); ssh=['ssh',*opts,gpu]
    remote=directory(ssh,config['gpu_root']+'/artifacts/sonic-full-')
    vendor=remote+'/vendor/GR00T-WholeBodyControl'
    setup=[['mkdir','-p',remote+'/scripts',vendor+'/gear_sonic/utils/teleop/zmq'],
           ['ln','-s',config['ik_deployment']+'/vendor/GR00T-WholeBodyControl/decoupled_wbc',vendor+'/decoupled_wbc'],
           ['ln','-s',config['sonic_build']+'/gear_sonic_deploy',vendor+'/gear_sonic_deploy'],
           ['ln','-s',config['sonic_build']+'/gear_sonic_deploy',remote+'/gear_sonic_deploy'],
           ['ln','-s',config['sonic_build']+'/build',remote+'/build']]
    run(ssh+[' && '.join(shlex.join(cmd) for cmd in setup)])
    helpers=['check_full_record_pipeline.py','sonic_process.py','sonic_ik_worker.py','prepare_sonic_tcp_pipeline.py',
             'sonic_tcp_reference.py','sonic_observation.py','sonic_reference.py','policy_action.py','pika_model.py',
             'state_history.py','runtime_config.py','runtime_gate.py','record_session.py','zmq_transport.py','probe_gpu_images.py',
             'reference_mailbox.py','rate_record_check.py','sonic_measured_stream.py','sonic_observation_worker.py','sonic_joint_trajectory.py',
             'body_history_transport.py','check_measured_record_pipeline.py','prepare_sonic_history_diagnostic.py',
             'online_record_loop.py','check_online_fixture_pipeline.py','record_capture.py','policy_bundle.py']
    run(['scp',*opts,*[str(source/name) for name in helpers],gpu+':'+remote+'/scripts/'])
    run(['scp',*opts,str(root/'config/policy-bundle.json'),gpu+':'+remote+'/scripts/'])
    if args.online_config:
        names=['online_record_main.py','online_record_loop.py','online_record_config.py','online_input_sources.py',
               'body_history_service.py','g1_camera_stream.py','gripper_observation.py','LICENSE.pika_geometry']
        run(['scp',*opts,'-r',*[str(source/name) for name in names],str(source/'state_receiver'),
             str(root/'vendor/lerobot/src/lerobot/robots/unitree_g1_pika/pika_gripper.py'),
             str(root/'vendor/lerobot/LICENSE'),str(root/'artifacts/gripper-motion-deps/pyserial-3.5-py2.py3-none-any.whl'),
             gpu+':'+remote+'/scripts/'])
        online_path=args.online_config
        if args.online_seconds is not None:
            online_values=load_online(args.online_config); online_values['seconds']=args.online_seconds
            online_path=local/'online-config.json'; online_path.write_text(json.dumps(online_values,indent=2)+'\n')
        run(['scp',*opts,str(online_path),gpu+':'+remote+'/online-config.json'])
        run(['scp',*opts,str(root/'assets/network/g1-runtime-access.json'),gpu+':'+remote+'/access-config.json'])
        if args.body_runtime:
            from run_body_runtime import build
            package=local/'body-runtime-package'; package.mkdir(); build(package)
            run(ssh+['mkdir '+shlex.quote(remote+'/body-runtime-package')])
            run(['scp',*opts,'-r',str(package/'runtime'),str(package/'manifest.json'),gpu+':'+remote+'/body-runtime-package/'])
            run(['scp',*opts,*[str(source/name) for name in ('sonic_body_bridge.py','body_lifecycle.py','sonic_startup_ablation.py')],
                 gpu+':'+remote+'/scripts/'])
    run(['scp',*opts,str(root/'vendor/GR00T-WholeBodyControl/gear_sonic/utils/teleop/zmq/zmq_planner_sender.py'),
         gpu+':'+vendor+'/gear_sonic/utils/teleop/zmq/'])
    run(['scp',*opts,str(source/'sonic_offline_infer.cpp'),str(source/'build_sonic_offline.sh'),
         str(local/'config.json'),gpu+':'+remote+'/'])
    if not args.online_config and not args.measured_state: run(['scp',*opts,str(args.record),gpu+':'+remote+'/record.json'])
    if args.measured_state: run(['scp',*opts,str(args.measured_state),gpu+':'+remote+'/measured-state.jsonl'])
    models=config['sonic_models']
    lock=json.loads((root/'sources.lock.json').read_text())['sonic']['checkpoint']
    commands=['cd '+shlex.quote(remote)]
    for name,key in [('model_encoder.onnx','encoder_sha256'),('model_decoder.onnx','decoder_sha256')]:
        commands.append('test "$(sha256sum '+shlex.quote(models+'/'+name)+' | cut -d " " -f 1)" = '+shlex.quote(lock[key]))
    commands.append(shlex.join(['env','SONIC_TRT_ROOT='+config['tensorrt_root'],'SONIC_CUDA_ROOT='+config['cuda_root'],
                            'bash','build_sonic_offline.sh',remote]))
    invocation=['python3','-I','scripts/check_full_record_pipeline.py','--config','config.json',
                             '--record','record.json','--images',args.gpu_images,'--output',remote+'/outputs']
    invocation+= (['--rate-check','--rate-seconds',str(args.rate_seconds)] if args.rate_check else [])
    invocation+= (['--online-fixture','--rate-seconds',str(args.rate_seconds)] if args.online_fixture else [])
    invocation+= (['--measured-state',remote+'/measured-state.jsonl'] if args.measured_state else [])
    if args.online_config:
        invocation=['python3','-I','scripts/online_record_main.py','--config','config.json',
                    '--online-config','online-config.json','--access-config','access-config.json',
                    '--output',remote+'/outputs','--allow-device-read']
        if args.body_runtime: invocation+=['--body-runtime']
    if args.joint_interpolation_seconds is not None:
        invocation+=['--joint-interpolation-seconds',str(args.joint_interpolation_seconds)]
    commands.append(shlex.join(['env','LD_LIBRARY_PATH='+config['tensorrt_root']+'/lib:'+config['cuda_root']+'/lib64',*invocation]))
    failure=None
    with (local/'gpu.log').open('w') as log:
        try:
            result=subprocess.run(ssh+[shlex.join(['timeout','--kill-after=3s','240s' if args.online_config else '180s','bash','-c',' && '.join(commands)])],
                                  stdout=log,stderr=subprocess.STDOUT,timeout=270 if args.online_config else 210)
            returncode=result.returncode
        except subprocess.TimeoutExpired:
            returncode=124
            failure='SSH deadline exceeded; remote timeout is configured but worker exit is unconfirmed'
    (local/'deployment.json').write_text(json.dumps(dict(remote=remote,returncode=returncode,error=failure),indent=2)+'\n')
    # Preserve logs even if the remote validation failed.
    (local/'outputs').mkdir(exist_ok=True)
    try:
        subprocess.run(['scp',*opts,gpu+':'+remote+'/outputs/report.json',
                        gpu+':'+remote+'/outputs/*.stderr.log',str(local/'outputs')+'/'],timeout=30)
    except subprocess.TimeoutExpired:
        print('Summary/log recovery deadline exceeded; bulk recovery will still be attempted')
    copy_returncode=recover(ssh,opts,gpu,remote,local)
    if copy_returncode: print('Output recovery failed; inspect remote directory:',remote)
    if failure: print(failure)
    if (local/'outputs/report.json').exists():
        try:
            report=json.loads((local/'outputs/report.json').read_text())
            print(json.dumps({k:v for k,v in report.items() if k not in ('outputs','policy_records','policy_timings','body_timings')},indent=2))
            if report.get('passed') and copy_returncode==0 and (args.online_fixture or args.online_config):
                from verify_online_record import verify
                integrity=verify(local/'outputs/report.json')
                (local/'integrity.json').write_text(json.dumps(integrity,indent=2)+'\n')
        except (ValueError,OSError,KeyError) as exc:
            copy_returncode=1
            print('Recovered result is incomplete or inconsistent:',type(exc).__name__,str(exc))
    deployment=dict(remote=remote,returncode=returncode,error=failure,recovery_returncode=copy_returncode)
    (local/'deployment.json').write_text(json.dumps(deployment,indent=2)+'\n')
    print('Saved:',local)
    return returncode or copy_returncode


if __name__=='__main__': raise SystemExit(main())
