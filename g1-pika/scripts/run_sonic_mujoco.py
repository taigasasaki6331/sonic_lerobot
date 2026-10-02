"""Deploy a bounded SONIC/MuJoCo-only job to galleria; never connect to G1."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parent))
from body_lifecycle_profile import load_profile
from runtime_config import load,ssh_options,DEFAULT
from run_state_shadow import directory,run
from recover_outputs import recover
from sonic_startup_ablation import ROOT,save,sha
from sonic_mujoco import validate_timing


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=DEFAULT)
    parser.add_argument('--seconds',type=float,default=5.)
    parser.add_argument('--warmup',type=float,default=1.,help='Explicit PD-only sim warmup before SONIC')
    parser.add_argument('--video',action='store_true')
    parser.add_argument('--pika',action='store_true',help='Existing fixed-gripper PIKA plant; no serial IO')
    parser.add_argument('--teacher',type=Path,help='Replay teacher TCP through pinned IK and SONIC')
    parser.add_argument('--lerobot',action='store_true',help='Saved RGB ACT + measured sim TCP; not visual/task validation')
    parser.add_argument('--native-body',action='store_true',help='Route every physics tick through native SIM ONLY body command gateway')
    parser.add_argument('--record',type=Path,default=Path('artifacts/state-shadow/state-shadow-Pysyga/live-report.json'))
    parser.add_argument('--gpu-images',default='/home/gpu-user/g1-pika-training/artifacts/live-shadow/run-1c31drlw')
    args=parser.parse_args()
    try: validate_timing(args.seconds,args.warmup)
    except ValueError as exc: parser.error(str(exc))
    if args.teacher and not args.pika: parser.error('Teacher requires --pika')
    if args.teacher:
        from teacher_trajectory import TeacherTrajectory
        teacher=TeacherTrajectory(json.loads(args.teacher.read_bytes()))
        if args.seconds<2+teacher.required_seconds: parser.error('Complete teacher replay with transition requires at least %.3fs'%(2+teacher.required_seconds))
    if args.lerobot and (not args.pika or args.teacher or args.seconds>30): parser.error('ACT requires PIKA, no teacher, maximum 30s')
    if args.lerobot:
        from policy_bundle import verify
        verify(ROOT,ROOT/'config/policy-bundle.json')
        if not args.record.is_file(): parser.error('Saved RGB/body record missing: '+str(args.record))
    config=load(args.config); parent=ROOT/'artifacts/sonic-mujoco'; parent.mkdir(parents=True,exist_ok=True)
    local=Path(tempfile.mkdtemp(prefix='run-',dir=parent)); save(local/'profile.json',load_profile())
    save(local/'config.json',config)
    source=ROOT/'scripts'; helpers=['sonic_mujoco.py','sonic_observation.py','sonic_reference.py','sonic_process.py']
    if args.teacher or args.lerobot: helpers+=['teacher_trajectory.py','sonic_tcp_reference.py','pika_model.py','policy_action.py','sonic_joint_trajectory.py']
    if args.lerobot: helpers+=['sonic_sim_actor.py','probe_gpu_images.py','policy_bundle.py']
    if args.native_body:
        from lowcmd_preview import export_data_headers
        headers=local/'body-data'; headers.mkdir(); export_data_headers(headers)
        save(local/'body-data-sources.json',{file.name:sha(file) for file in headers.iterdir()})
        helpers+=['sim_body_gateway.py','sim_body_gateway.cpp','body_io_adapter.hpp','body_writer.hpp']
    save(local/'sources.json',{name:sha(source/name) for name in helpers+['sonic_offline_infer.cpp','build_sonic_offline.sh']})
    save(local/'invocation.json',dict(seconds=args.seconds,warmup=args.warmup,video=args.video,pika=args.pika,
        teacher_sha256=sha(args.teacher) if args.teacher else None,lerobot=args.lerobot,native_body=args.native_body,g1_connected=False))
    options=ssh_options(config); gpu=config['gpu_host']; ssh=['ssh',*options,gpu]
    remote=directory(ssh,config['gpu_root']+'/artifacts/sonic-mujoco-')
    vendor=remote+'/vendor/GR00T-WholeBodyControl'; ikroot=config['ik_deployment']
    commands=[['mkdir','-p',remote+'/scripts',vendor+'/gear_sonic/utils/teleop/zmq'],
        ['ln','-s',config['sonic_build']+'/gear_sonic_deploy',vendor+'/gear_sonic_deploy'],
        ['ln','-s',config['sonic_build']+'/gear_sonic_deploy',remote+'/gear_sonic_deploy'],
        ['ln','-s',config['sonic_build']+'/build',remote+'/build'],['mkdir',remote+'/models']]
    if args.teacher or args.lerobot: commands.append(['ln','-s',ikroot+'/vendor/GR00T-WholeBodyControl/decoupled_wbc',vendor+'/decoupled_wbc'])
    # Fresh model/cache copies protect shared artifacts from TRT conversion.
    for name in ('model_encoder.onnx','model_decoder.onnx','model_encoder.trt','model_decoder.trt'):
        commands.append(['cp',config['sonic_models']+'/'+name,remote+'/models/'+name])
    run(ssh+[' && '.join(shlex.join(cmd) for cmd in commands)])
    run(['scp',*options,*[str(source/name) for name in helpers],gpu+':'+remote+'/scripts/'])
    if args.native_body: run(['scp',*options,*map(str,headers.iterdir()),gpu+':'+remote+'/scripts/'])
    run(['scp',*options,str(local/'profile.json'),str(source/'sonic_offline_infer.cpp'),
        str(source/'build_sonic_offline.sh'),gpu+':'+remote+'/'])
    run(['scp',*options,str(ROOT/'vendor/GR00T-WholeBodyControl/gear_sonic/utils/teleop/zmq/zmq_planner_sender.py'),
        gpu+':'+vendor+'/gear_sonic/utils/teleop/zmq/'])
    shell=[shlex.join(['env','SONIC_TRT_ROOT='+config['tensorrt_root'],'SONIC_CUDA_ROOT='+config['cuda_root'],
        'bash',remote+'/build_sonic_offline.sh',remote])]
    if args.native_body:
        shell.append(shlex.join(['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-pthread','-shared','-fPIC',
            remote+'/scripts/sim_body_gateway.cpp','-o',remote+'/sim-body-gateway.so']))
    invocation=[ikroot+'/.venv/bin/python','-I',remote+'/scripts/sonic_mujoco.py',
        '--model',(ikroot+'/artifacts/models/g1_pika_closed.xml' if args.pika else
            ikroot+'/vendor/GR00T-WholeBodyControl/decoupled_wbc/sim2mujoco/resources/robots/g1/g1_gear_wbc.xml'),
        '--models',remote+'/models','--binary',remote+'/sonic_offline_infer','--profile',remote+'/profile.json',
        '--output',remote+'/outputs','--seconds',str(args.seconds),'--warmup',str(args.warmup)]
    if args.video: invocation+=['--video']
    if args.pika: invocation+=['--pika']
    if args.native_body: invocation+=['--body-gateway',remote+'/sim-body-gateway.so']
    if args.teacher:
        save(local/'teacher.json',json.loads(args.teacher.read_bytes()))
        run(['scp',*options,str(local/'teacher.json'),gpu+':'+remote+'/'])
        invocation+=['--teacher',remote+'/teacher.json','--urdf',ikroot+'/artifacts/models/g1_pika_closed.urdf']
    if args.lerobot:
        run(['scp',*options,str(args.record),gpu+':'+remote+'/record.json'])
        run(['scp',*options,str(ROOT/'config/policy-bundle.json'),gpu+':'+remote+'/policy-bundle.json'])
        invocation+=['--lerobot','--urdf',ikroot+'/artifacts/models/g1_pika_closed.urdf',
            '--act-root',config['gpu_root'],'--act-record',remote+'/record.json',
            '--act-bundle',remote+'/policy-bundle.json','--act-images',args.gpu_images]
    shell.append(shlex.join(['env','MUJOCO_GL=egl','LD_LIBRARY_PATH='+config['tensorrt_root']+'/lib:'+config['cuda_root']+'/lib64',*invocation]))
    code=124; failure=None
    with (local/'gpu.log').open('x') as log:
        try:
            code=subprocess.run(ssh+[shlex.join(['timeout','--kill-after=3s','180s','bash','-c',' && '.join(shell)])],
                stdout=log,stderr=subprocess.STDOUT,timeout=210).returncode
        except subprocess.TimeoutExpired: failure='SSH deadline; remote exit is not confirmed'
    save(local/'deployment.json',dict(remote=remote,returncode=code,error=failure,remote_timeout_s=180,g1_connected=False))
    recovery=recover(ssh,options,gpu,remote,local); save(local/'recovery.json',dict(returncode=recovery))
    if (local/'outputs/report.json').exists():
        report=json.loads((local/'outputs/report.json').read_bytes()); print(json.dumps(report,indent=2))
    print('Saved:',local,flush=True)
    return code or recovery


if __name__=='__main__': raise SystemExit(main())
