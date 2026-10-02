"""One-command saved-state SONIC diagnostic on galleria. Never connects to G1."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare_sonic_history_diagnostic import prepare
from run_state_shadow import directory, run
from runtime_config import load, ssh_options, DEFAULT

MODEL_HASHES = {
    'model_encoder.onnx': '60be43157f57d812f38bdbb740a5de5d5d070e8840d9edc16f02a91a6d06255b',
    'model_decoder.onnx': 'c4ac2e74045e7cbfb568f15e6bf47ea7ce023df7a94322af50be223e0a628bab',
}


def summarize(request, result):
    source = request['frames']
    outputs = result['outputs']
    if ([r['seq'] for r in source] != [r['seq'] for r in outputs]
            or result['source_sha256'] != request['source_sha256']):
        raise ValueError('Inference result does not match input')
    q = np.array([r['measured_q'] for r in source])
    target = np.array([r['q_target_hardware'] for r in outputs])
    if target.shape != q.shape or not np.isfinite(target).all():
        raise ValueError('Invalid output targets')
    difference = abs(target-q)
    widths = []
    for before, after in zip(source, outputs):
        if 'gripper_width_m' in before:
            if after.get('gripper_actuated') is not False or after.get('gripper_width_m') != before['gripper_width_m']:
                raise ValueError('Gripper side-channel changed or actuated')
            widths.append(after['gripper_width_m'])
    return dict(windows=len(source), output_finite=True,
                gripper_width_metadata_count=len(widths),
                gripper_width_range_m=[min(widths),max(widths)] if widths else None,
                max_target_difference_rad=float(difference.max()),
                first_window_max_difference_rad=float(difference[0].max()),
                last_window_max_difference_rad=float(difference[-1].max()),
                max_difference_per_hardware_joint_rad=difference.max(axis=0).tolist(),
                encoder_decoder_wall_p95_ms=float(np.percentile(
                    [r['encoder_decoder_wall_ms'] for r in outputs], 95)),
                action_history_mode=result['action_history_mode'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=DEFAULT)
    parser.add_argument('--service-check', action='store_true', help='Also verify persistent SONIC via GPU-local ZMQ IPC')
    parser.add_argument('--compare-recurrent',action='store_true',help='Compare zero/computed action history for prepared saved inputs too')
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--state', type=Path)
    inputs.add_argument('--prepared', type=Path, help='Prepared recorded-action snapshot diagnostic')
    args = parser.parse_args()
    config=load(args.config)
    gpu=config['gpu_host']; options=ssh_options(config)
    build=config['sonic_build']; models=config['sonic_models']
    source = Path(__file__).resolve().parent
    request = prepare(args.state.read_bytes()) if args.state else json.loads(args.prepared.read_text())
    if args.prepared and request.get('scope') not in ('diagnostic_repeated_snapshot_not_50hz_history',
                                                   'diagnostic_real_body_history_zero_prior_actions'):
        raise ValueError('Unsupported prepared diagnostic')
    if request.get('skipped_windows', 0):
        raise ValueError('This paired comparison requires consecutive valid windows')
    parent = source.parent/'artifacts/sonic-replay'
    parent.mkdir(parents=True, exist_ok=True)
    local = Path(tempfile.mkdtemp(prefix='run-', dir=parent))
    (local/'input.json').write_text(json.dumps(request, allow_nan=False))
    (local/'resolved-config.json').write_text(json.dumps(config, indent=2)+'\n')
    remote = directory(['ssh', *options, gpu], config['gpu_root']+'/artifacts/sonic-replay-')
    run(['scp', *options, str(local/'input.json'), str(source/'sonic_offline_infer.cpp'),
         str(source/'build_sonic_offline.sh'), gpu+':'+remote+'/'])
    if args.service_check:
        helpers=['sonic_process.py','check_sonic_service.py','record_session.py','runtime_gate.py',
                 'runtime_config.py','zmq_transport.py']
        run(['scp',*options,*[str(source/name) for name in helpers],str(local/'resolved-config.json'),gpu+':'+remote+'/'])
    # All destinations are fresh. Existing pinned build/model assets are only read.
    commands = ['cd '+shlex.quote(remote), 'ln -s '+shlex.quote(build+'/build')+' build',
                'ln -s '+shlex.quote(build+'/gear_sonic_deploy')+' gear_sonic_deploy']
    for name, digest in MODEL_HASHES.items():
        commands.append('test "$(sha256sum '+shlex.quote(models+'/'+name)+
                        ' | cut -d " " -f 1)" = '+shlex.quote(digest))
    commands.append(shlex.join(['env', 'SONIC_TRT_ROOT='+config['tensorrt_root'],
                               'SONIC_CUDA_ROOT='+config['cuda_root'], 'bash','build_sonic_offline.sh',remote]))
    base = ['env', 'LD_LIBRARY_PATH='+config['tensorrt_root']+'/lib:'+config['cuda_root']+'/lib64',
            './sonic_offline_infer', models+'/model_encoder.onnx', models+'/model_decoder.onnx', 'input.json']
    conditions = ('zero', 'recurrent') if args.state or args.compare_recurrent else ('zero',)
    commands += [shlex.join(base+[name+'.json']+(['recurrent'] if name=='recurrent' else [])) for name in conditions]
    if args.service_check:
        commands.append(shlex.join(['env',base[1],'python3','-I','check_sonic_service.py',
            '--binary',remote+'/sonic_offline_infer','--encoder',models+'/model_encoder.onnx',
            '--decoder',models+'/model_decoder.onnx','--input','input.json','--baseline','zero.json',
            '--report','service-report.json','--config','resolved-config.json']))
    with (local/'gpu.log').open('w') as log:
        bounded=shlex.join(['timeout','--signal=TERM','--kill-after=3s','120s','bash','-c',' && '.join(commands)])
        try:
            result = subprocess.run(['ssh', *options, gpu, bounded],
                                    stdout=log, stderr=subprocess.STDOUT, timeout=180)
            code=result.returncode
        except subprocess.TimeoutExpired:
            code=124
    report = dict(scope='open_loop_record_replay_not_hardware_validation',
                  computation_completed=False, hardware_ready=False, robot_commands_sent=False,
                  g1_connected=False, remote_directory=remote, source_sha256=request['source_sha256'],
                  code_sha256=hashlib.sha256((source/'sonic_offline_infer.cpp').read_bytes()).hexdigest(),
                  gpu_returncode=code, remote_worker_timeout_s=120, reference=request['reference'],
                  history=request['history'], config=config, conditions={})
    if code == 0:
        for name in conditions:
            run(['scp', *options, gpu+':'+remote+'/'+name+'.json', str(local/(name+'.json'))])
            report['conditions'][name] = summarize(request, json.loads((local/(name+'.json')).read_text()))
        if args.service_check:
            run(['scp',*options,gpu+':'+remote+'/service-report.json',str(local/'service-report.json')])
            service=json.loads((local/'service-report.json').read_text())
            report['persistent_service']={k:v for k,v in service.items() if k!='outputs'}
            if not service['passed']: raise ValueError('Persistent service check failed')
        report['computation_completed'] = True
    (local/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))
    print('Saved:', local)
    return code


if __name__ == '__main__': raise SystemExit(main())
