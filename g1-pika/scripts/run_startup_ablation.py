"""One bounded GPU-only saved-input channel/reference comparison. No G1 IO."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parent))
from runtime_config import load, ssh_options, DEFAULT
from run_state_shadow import directory, run
from recover_outputs import recover
from sonic_startup_ablation import prepare, validate, save, verify_saved
from sonic_process import strict_message

ROOT = Path(__file__).resolve().parents[1]
BASELINE = Path('/home/developer/Documents/Codex/2026-09-30/task/sonic-startup-diagnostic-20260930-a41f')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=DEFAULT)
    parser.add_argument('--report',type=Path,default=ROOT/'artifacts/full-record/run-b5do1ocs/outputs/report.json')
    parser.add_argument('--baseline-directory',type=Path,default=BASELINE)
    parser.add_argument('--prepare-only',action='store_true',help='Files/oracle only; no SSH or GPU')
    parser.add_argument('--prepared',type=Path,help='Reuse previously verified prepared file; no archive re-reading')
    args = parser.parse_args(); config = load(args.config)
    data = validate(strict_message(args.prepared.read_bytes()) if args.prepared else prepare(args.report,args.baseline_directory))
    parent = ROOT/'artifacts/sonic-startup-ablation'; parent.mkdir(exist_ok=True,parents=True)
    local = Path(tempfile.mkdtemp(prefix='run-',dir=parent)); save(local/'input.json',data)
    save(local/'config.json',config)
    print('Prepared:',local,flush=True)
    if args.prepare_only: return 0
    options = ssh_options(config); gpu = config['gpu_host']; ssh = ['ssh',*options,gpu]
    remote = directory(ssh,config['gpu_root']+'/artifacts/sonic-startup-ablation-')
    source = ROOT/'scripts'
    run(['scp',*options,str(local/'input.json'),*[str(source/name) for name in
        ('sonic_startup_ablation.py','sonic_process.py','sonic_offline_infer.cpp','build_sonic_offline.sh')],gpu+':'+remote+'/'])
    commands = [shlex.join(['ln','-s',config['sonic_build']+'/build',remote+'/build']),
                shlex.join(['ln','-s',config['sonic_build']+'/gear_sonic_deploy',remote+'/gear_sonic_deploy']),
                shlex.join(['mkdir',remote+'/models'])]
    # Copy only the known model/cache files into a new deployment. Conversion
    # cannot update shared model caches or another experiment's files.
    for name in ('model_encoder.onnx','model_decoder.onnx','model_encoder.trt','model_decoder.trt'):
        commands.append(shlex.join(['cp',config['sonic_models']+'/'+name,remote+'/models/'+name]))
    commands.append(shlex.join(['env','SONIC_TRT_ROOT='+config['tensorrt_root'],
        'SONIC_CUDA_ROOT='+config['cuda_root'],'bash',remote+'/build_sonic_offline.sh',remote]))
    commands.append(shlex.join(['env','LD_LIBRARY_PATH='+config['tensorrt_root']+'/lib:'+config['cuda_root']+'/lib64',
        config['gpu_root']+'/.venv-gpu/bin/python','-I',remote+'/sonic_startup_ablation.py','infer',
        '--input',remote+'/input.json','--binary',remote+'/sonic_offline_infer','--models',remote+'/models',
        '--output',remote+'/outputs']))
    code = 124
    with (local/'gpu.log').open('x') as log:
        try:
            code = subprocess.run(ssh+[shlex.join(['nice','-n','10','timeout','--signal=TERM','--kill-after=3s',
                '150s','bash','-c',' && '.join(commands)])],stdout=log,stderr=subprocess.STDOUT,timeout=180).returncode
        except subprocess.TimeoutExpired: pass
    deployment = dict(remote=remote,gpu_returncode=code,remote_timeout_s=150,
                      worker_exit_not_confirmed_by_ssh_termination=True)
    save(local/'deployment.json',deployment)
    recovery = recover(ssh,options,gpu,remote,local)
    save(local/'recovery.json',dict(returncode=recovery))
    if code == 0 and recovery == 0:
        integrity = verify_saved(local/'input.json',local/'outputs')
        save(local/'integrity.json',integrity)
        print(json.dumps(integrity,indent=2))
    else: print('Diagnostic/recovery failed; inspect gpu.log. Remote:',remote)
    print('Saved:',local)
    return code or recovery


if __name__=='__main__': raise SystemExit(main())
