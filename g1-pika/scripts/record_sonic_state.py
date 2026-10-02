"""Capture eight seconds of receive-only LowState; never opens command topics."""
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_state_shadow import GPU, GPU_ROOT, GPU_OPTS, directory, run


def main():
    source = Path(__file__).resolve().parent
    if '--on-gpu' not in sys.argv:
        dest = directory(['ssh', *GPU_OPTS, GPU], GPU_ROOT + '/artifacts/sonic-state-')
        run(['scp', *GPU_OPTS, '-r', str(source / 'record_sonic_state.py'),
             str(source / 'run_state_shadow.py'), str(source / 'state_receiver'),
             str(source.parent / 'assets/network/g1-runtime-access.json'), GPU + ':' + dest + '/'])
        result = subprocess.run(['ssh', *GPU_OPTS, GPU,
            'python3 -I ' + shlex.quote(dest + '/record_sonic_state.py') + ' --on-gpu'], timeout=60)
        local = source.parent / 'artifacts/sonic-state'
        local.mkdir(parents=True, exist_ok=True)
        run(['scp', *GPU_OPTS, '-r', GPU + ':' + dest, str(local) + '/'])
        print('Local capture: ' + str(local / Path(dest).name))
        return result.returncode
    access = json.loads((source / 'g1-runtime-access.json').read_text())
    opts = ['-i', access['gpu_ssh_identity'], '-o', 'IdentitiesOnly=yes',
            '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
            '-o', 'UserKnownHostsFile=' + access['gpu_known_hosts'],
            '-o', 'GlobalKnownHostsFile=/dev/null', '-o', 'ConnectTimeout=5']
    ssh = ['ssh', *opts, access['g1_host']]
    receiver = source / 'state_receiver'
    manifest = json.loads((receiver / 'generated/manifest.json').read_text())
    for name, digest in manifest['sha256'].items():
        if hashlib.sha256((receiver / name).read_bytes()).hexdigest() != digest:
            raise ValueError('Receiver checksum mismatch: ' + name)
    started = time.monotonic()
    dest = directory(ssh, '/tmp/g1-pika-record-')
    run(['scp', *opts, '-r', str(receiver), access['g1_host'] + ':' + dest + '/'])
    code = dest + '/state_receiver'
    run(ssh + ["grep -q '#define DDS_VERSION \"0.10.2\"' /usr/local/include/dds/version.h && "
        f'gcc -O2 -Wall -Wextra -I/usr/local/include -I{code}/generated '
        f'{code}/receive_state.c {code}/generated/State.c '
        f'-L/usr/local/lib -Wl,-rpath,/usr/local/lib -lddsc -lm -o {dest}/receive_state'])
    result = subprocess.run(ssh + ['env G1_STATE_INTERFACE=' + shlex.quote(access['g1_interface']) +
        ' timeout --signal=TERM --kill-after=2s 8s ' + dest + '/receive_state --stream'],
        capture_output=True, timeout=20)
    (source / 'state.jsonl').write_bytes(result.stdout)
    (source / 'stderr.txt').write_bytes(result.stderr)
    frames = [json.loads(line) for line in result.stdout.splitlines()]
    gaps = [b['receive_monotonic_s'] - a['receive_monotonic_s'] for a, b in zip(frames, frames[1:])]
    valid_windows = sum(all(.018 <= dt <= .022 for dt in gaps[i:i+9])
                        for i in range(max(0, len(gaps)-8)))
    passed = result.returncode == 124 and valid_windows > 0
    report = dict(scope='receive_only_lowstate_record', motion_commands_sent=False,
        camera_or_serial_opened=False, crc_verified=False, passed=passed,
        receiver_exit_code=result.returncode, bounded_capture_seconds=8,
        elapsed_deploy_compile_capture_s=time.monotonic()-started,
        frames=len(frames), valid_10_frame_windows_20ms_tolerance_2ms=valid_windows,
        maximum_gap_s=max(gaps, default=None),
        state_sha256=hashlib.sha256(result.stdout).hexdigest(),
        receiver_sha256=hashlib.sha256((receiver / 'receive_state.c').read_bytes()).hexdigest(),
        sample_clock_sha256=hashlib.sha256((receiver / 'sample_clock.h').read_bytes()).hexdigest(),
        g1_temporary_directory=dest)
    (source / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2), flush=True)
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
