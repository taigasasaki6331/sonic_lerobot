"""Deploy and run the bounded, receive-only G1 -> ZMQ -> GPU diagnostic."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys

GPU = 'galleria@192.0.2.9'
GPU_ROOT = '/home/gpu-user/g1-pika-training'
GPU_OPTS = ['-i', '/home/developer/.ssh/EXAMPLE_GPU_KEY', '-o', 'IdentitiesOnly=yes',
            '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=5']


def run(argv, **kw):
    return subprocess.run(argv, check=True, timeout=240, **kw)


def directory(argv, prefix):
    value = subprocess.check_output(argv + ['mktemp -d ' + prefix + 'XXXXXX'],
                                    text=True, timeout=15).strip()
    if not value.startswith(prefix) or any(c.isspace() for c in value):
        raise ValueError('Unexpected deployment path')
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--on-gpu', action='store_true')
    parser.add_argument('--gripper-state', action='store_true')
    parser.add_argument('--archive-sonic-inputs', action='store_true')
    args = parser.parse_args()
    source = Path(__file__).resolve().parent
    generated = source / 'state_receiver/generated'
    manifest = json.loads((generated / 'manifest.json').read_text())
    for name, digest in manifest['sha256'].items():
        if hashlib.sha256((source / 'state_receiver' / name).read_bytes()).hexdigest() != digest:
            raise ValueError('State receiver IDL/generated checksum mismatch: ' + name)
    if not args.on_gpu:
        root = source.parent
        dest = directory(['ssh', *GPU_OPTS, GPU], GPU_ROOT + '/artifacts/state-shadow-')
        files = [source / name for name in ('run_state_shadow.py', 'run_live_shadow.py',
                 'g1_camera_stream.py', 'probe_gpu_images.py', 'zmq_transport.py', 'policy_bundle.py')]
        files += [root / 'config/policy-bundle.json']
        files += [root / 'assets/network/g1-runtime-access.json', source / 'state_receiver']
        if args.archive_sonic_inputs: files += [source / 'state_history.py']
        if args.gripper_state:
            files += [source / 'gripper_observation.py', source / 'LICENSE.pika_geometry',
                      root / 'vendor/lerobot/src/lerobot/robots/unitree_g1_pika/pika_gripper.py',
                      root / 'vendor/lerobot/LICENSE',
                      root / 'artifacts/gripper-motion-deps/pyserial-3.5-py2.py3-none-any.whl']
        run(['scp', *GPU_OPTS, '-r', *map(str, files), GPU + ':' + dest + '/'])
        result = subprocess.run(['ssh', *GPU_OPTS, GPU,
            'python3 -I ' + shlex.quote(dest + '/run_state_shadow.py') + ' --on-gpu' +
            (' --gripper-state' if args.gripper_state else '') +
            (' --archive-sonic-inputs' if args.archive_sonic_inputs else '')], timeout=240)
        local = root / 'artifacts/state-shadow' / Path(dest).name
        local.parent.mkdir(parents=True, exist_ok=True)
        run(['scp', *GPU_OPTS, '-r', GPU + ':' + dest, str(local.parent) + '/'])
        return result.returncode

    config_path = source / 'g1-runtime-access.json'
    access = json.loads(config_path.read_text())
    # This diagnostic's bind/filter endpoints remain deliberately fixed.
    if (access['g1_host'], access['gpu_interface'], access['gpu_wired_ip']) != (
            'unitree@192.0.2.11', 'enp2s0', '192.0.2.12'):
        raise ValueError('Unsupported topology; do not silently fall back')
    opts = ['-i', access['gpu_ssh_identity'], '-o', 'IdentitiesOnly=yes',
            '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
            '-o', 'UserKnownHostsFile=' + access['gpu_known_hosts'],
            '-o', 'GlobalKnownHostsFile=/dev/null', '-o', 'ConnectTimeout=5']
    ssh = ['ssh', *opts, access['g1_host']]
    dest = directory(ssh, '/tmp/g1-pika-state-')
    run(['scp', *opts, '-r', str(source / 'state_receiver'), access['g1_host'] + ':' + dest + '/'])
    code = dest + '/state_receiver'
    command = ('test -f /usr/local/include/dds/version.h && '
        'grep -q \'#define DDS_VERSION "0.10.2"\' /usr/local/include/dds/version.h && '
        f'gcc -O2 -Wall -Wextra -I/usr/local/include -I{code}/generated '
        f'{code}/receive_state.c {code}/generated/State.c '
        f'-L/usr/local/lib -Wl,-rpath,/usr/local/lib -lddsc -lm -o {dest}/receive_state')
    run(ssh + [command])
    # Verify state reception before opening cameras or loading inference.
    check = subprocess.check_output(ssh + ['env G1_STATE_INTERFACE=' +
        shlex.quote(access['g1_interface']) + ' timeout 10s ' + dest + '/receive_state'],
        text=True, timeout=20)
    report = json.loads(check)
    (source / 'state-check.json').write_text(json.dumps(report, indent=2) + '\n')
    if not report['passed']: raise RuntimeError('Read-only state check failed')
    print(check, flush=True)
    result = subprocess.run([sys.executable, '-I', str(source / 'run_live_shadow.py'),
        '--direct-on-gpu', '--zmq', '--access-config', str(config_path),
        '--report-copy', str(source / 'live-report.json'),
        '--state-reader', dest + '/receive_state'] + (['--gripper-state'] if args.gripper_state else []) +
        (['--archive-sonic-inputs'] if args.archive_sonic_inputs else []), timeout=190)
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
