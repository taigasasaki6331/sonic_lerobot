"""Stage pinned sources in a fresh GPU directory and BUILD ONLY; never deploy."""
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
GPU = 'galleria@192.0.2.9'
OPTS = ['-i', '/home/developer/.ssh/EXAMPLE_GPU_KEY', '-o', 'IdentitiesOnly=yes',
        '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=5']


def main():
    vendor = ROOT/'vendor/GR00T-WholeBodyControl'
    lock = json.loads((ROOT/'sources.lock.json').read_text())['sonic']
    commit = subprocess.check_output(['git','-C',str(vendor),'rev-parse','HEAD'],text=True).strip()
    if commit != lock['commit']:
        raise ValueError('SONIC commit mismatch')
    base = ROOT/'artifacts/sonic-build'
    base.mkdir(parents=True, exist_ok=True)
    local = Path(tempfile.mkdtemp(prefix='run-',dir=base))
    report = dict(passed=False,scope='compile_only_no_controller_execution',
                  robot_commands_sent=False,upstream_commit=commit)
    try:
        remote = subprocess.check_output(['ssh',*OPTS,GPU,
            'mktemp -d /home/gpu-user/g1-pika-training/artifacts/sonic-build-XXXXXX'],
            text=True,timeout=15).strip()
        if not remote.startswith('/home/gpu-user/g1-pika-training/artifacts/sonic-build-') or any(c.isspace() for c in remote):
            raise ValueError('Unexpected remote path')
        report['gpu_directory'] = remote
        # Record exact staged source hashes, including LFS libraries; no source edits.
        manifest = {str(p.relative_to(vendor)):hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sorted((vendor/'gear_sonic_deploy').rglob('*')) if p.is_file()}
        (local/'source-sha256.json').write_text(json.dumps(manifest,indent=2)+'\n')
        subprocess.run(['scp',*OPTS,'-r',str(vendor/'gear_sonic_deploy'),
                        str(ROOT/'scripts/resolve_sonic_build_lfs.py'),
                        str(vendor/'LICENSE'),str(local/'source-sha256.json'),GPU+':'+remote+'/'],
                       check=True,timeout=180)
        source = shlex.quote(remote+'/gear_sonic_deploy')
        build = shlex.quote(remote+'/build')
        command = ('python3 -I '+shlex.quote(remote+'/resolve_sonic_build_lfs.py')+' '+shlex.quote(remote)+' && '
                   'env HAS_ROS2=0 CUDAToolkit_ROOT=/usr/local/cuda-12.8 '
                   'cmake -S '+source+' -B '+build+
                   ' -DTensorRT_ROOT=/home/gpu-user/TensorRT-192.0.2.3'
                   ' -Donnxruntime_ROOT=/opt/onnxruntime -DCMAKE_POLICY_VERSION_MINIMUM=3.5'
                   ' -DCMAKE_BUILD_TYPE=Release && cmake --build '+build+
                   ' --target g1_deploy_onnx_ref -j4')
        with (local/'build.log').open('w') as log:
            result = subprocess.run(['ssh',*OPTS,GPU,command],stdout=log,stderr=subprocess.STDOUT,timeout=900)
        report['build_returncode'] = result.returncode
        report['passed'] = result.returncode == 0
    except Exception as exc:
        report['error'] = str(exc)
    (local/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)
    print('Logs:',local,flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
