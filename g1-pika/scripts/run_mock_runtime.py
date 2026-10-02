"""One-command, finite simulated G1 -> ZMQ -> ACT -> WBC acceptance.

Deploys only new temporary scripts under the GPU project's artifacts directory.
Never connects to G1 or installs dependencies; every output is simulation/recording.
"""
import argparse
import hashlib
import json
from pathlib import Path
import select
import shlex
import subprocess
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--local', action='store_true', help='CPU loopback fallback, no SSH/GPU')
    p.add_argument('--nominal-only', action='store_true')
    p.add_argument('--viewer', action='store_true', help='Show the nominal simulation only')
    a = p.parse_args()
    if a.viewer: a.nominal_only = True
    cfg = json.loads((ROOT / 'assets/network/mock-runtime.json').read_text())
    base = ROOT / 'artifacts/mock-runtime'
    base.mkdir(parents=True, exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix='run-', dir=base))
    observations = out / 'observations'
    with (out / 'export.log').open('w') as log:
        subprocess.run([str(ROOT / '.venv-policy/bin/python'), '-I', 'scripts/export_mock_observations.py',
                        '--output', str(observations), '--frames', str(cfg['frames'])],
                       cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
    ssh = ['ssh', '-i', cfg['ssh_key'], '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes',
           '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=5', cfg['gpu_host']]
    if a.local:
        remote = str(ROOT / 'scripts')
    else:
        remote = subprocess.check_output(ssh + [shlex.join(['mktemp', '-d',
            cfg['gpu_root'] + '/artifacts/mock-runtime-XXXXXX'])], text=True, timeout=15).strip()
        if not remote.startswith(cfg['gpu_root'] + '/artifacts/mock-runtime-') or '\n' in remote:
            raise ValueError('Unexpected deployment directory')
        subprocess.run(['rsync', '-a', '-e', shlex.join(ssh[:-1]),
                        *[str(ROOT / 'scripts' / f) for f in
                          ['mock_policy_server.py', 'zmq_transport.py', 'wbc_state.py']],
                        cfg['gpu_host'] + ':' + remote + '/'], check=True, timeout=30)
    endpoint = 'tcp://' + ('127.0.0.1' if a.local else cfg['gpu_ip']) + ':' + str(cfg['port'])
    summary = {'scope': 'recorded_mock_G1_network_inference_to_simulated_WBC',
               'hardware_ready': False, 'robot_commands_sent': False, 'camera_closed_loop': False,
               'gpu_used': not a.local, 'output': str(out), 'deployment': remote, 'checks': []}
    summary['source_sha256'] = {f: hashlib.sha256((ROOT / 'scripts' / f).read_bytes()).hexdigest()
        for f in ['mock_policy_server.py', 'zmq_transport.py', 'wbc_state.py', 'wbc_controller.py',
                  'zmq_policy_client.py', 'run_mock_runtime.py', 'sim_balance.py']}
    for script in ['check_wbc_state.py', 'check_control_guard.py', 'check_policy_action.py',
                   'check_policy_bridge.py', 'check_async_policy.py', 'check_zmq_transport.py']:
        with (out / (script + '.log')).open('w') as log:
            test = subprocess.run([str(ROOT / '.venv/bin/python'), '-I', 'scripts/' + script],
                                  cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=30)
        summary['checks'].append({'name': script, 'passed': test.returncode == 0})
    cases = [('nominal', 'none')] if a.nominal_only else [
        ('nominal', 'none'), ('stale', 'stale'), ('disconnect', 'disconnect'),
        ('delay', 'delay'), ('fresh_session_after_fault', 'none')]
    for name, fault in cases:
        session = uuid.uuid4().hex
        case = out / name
        case.mkdir()
        remote_report = str(case / 'server.json') if a.local else remote + '/' + name + '.json'
        server_cmd = [str(ROOT / '.venv-policy/bin/python') if a.local else cfg['gpu_root'] + '/.venv-gpu/bin/python',
            '-I', remote + '/mock_policy_server.py', '--root', str(ROOT) if a.local else cfg['gpu_root'],
            '--endpoint', endpoint, '--accept-ip', '127.0.0.1' if a.local else cfg['client_ip'],
            '--session', session, '--frames', str(cfg['frames']), '--device', 'cpu' if a.local else 'cuda',
            '--fault', fault, '--report', remote_report]
        launch = server_cmd if a.local else ssh + [shlex.join(['timeout', '180'] + server_cmd)]
        check = {'name': name, 'session': session, 'passed': False}
        with (case / 'server.log').open('w') as log:
            server = subprocess.Popen(launch, stdout=subprocess.PIPE, stderr=log, text=True)
            try:
                if not select.select([server.stdout], [], [], 100)[0]:
                    raise TimeoutError('Inference service startup timeout')
                ready = json.loads(server.stdout.readline())
                if ready.get('session') != session or ready.get('ready') is not True:
                    raise ValueError('Unexpected readiness response')
                cmd = [str(ROOT / '.venv/bin/python'), '-I', 'scripts/sim_balance.py',
                    '--controller', 'wbc', '--pika', '--guard-output', '--policy-async',
                    '--policy-run', 'artifacts/full-rgb-residual/run-xg1fn3b_',
                    '--policy-frames', str(cfg['frames']), '--seconds', str(cfg['seconds']),
                    '--policy-endpoint', endpoint, '--policy-session', session,
                    '--policy-observations', str(observations), '--report-dir', str(case)]
                if a.viewer: cmd.append('--viewer')
                with (case / 'simulation.log').open('w') as simlog:
                    run = subprocess.run(cmd, cwd=ROOT, stdout=simlog, stderr=subprocess.STDOUT, timeout=100)
                server.wait(timeout=25)
                if not a.local:
                    content = subprocess.check_output(ssh + [shlex.join(['cat', remote_report])], text=True, timeout=15)
                    (case / 'server.json').write_text(content)
                report = json.loads((case / 'policy-sim-async-guard-none-latest.json').read_text())
                remote_data = json.loads((case / 'server.json').read_text())
                bridge = report['policy_bridge']
                sent = bridge['worker']['sent_body_records']
                paired = all(record['seq'] == i and record['body_sha256'] == sent[i]['body_sha256']
                             and record['body_time'] == sent[i]['body_time']
                             for i, record in enumerate(remote_data['records']))
                balanced = (report['pelvis_height_min_m'] >= .45 and report['tilt_max_rad'] <= .8
                            and report['xy_displacement_max_m'] <= .25
                            and report['tcp_position_error_max_m'] <= .05
                            and report['tcp_orientation_error_max_rad'] <= .3)
                valid = (report['output_guard']['phase'] == 'active'
                         and report['output_guard']['accepted_frames'] == int(cfg['seconds'] * 50)
                         and report['mujoco_warning_count'] == 0
                         and remote_data['metadata']['session'] == session
                         and remote_data['metadata']['device'] == ('cpu' if a.local else 'cuda')
                         and server.returncode == 0 and paired and balanced)
                if fault == 'none':
                    valid = valid and run.returncode == 0 and report['passed'] and bridge['accepted_actions'] == cfg['frames']
                else:
                    reason = bridge['latched_stop_reason'] or ''
                    expected = 'Stale session/sequence' if fault == 'stale' else 'deadline exceeded'
                    valid = valid and run.returncode == 1 and bridge['accepted_actions'] == 5 and expected in reason
                check.update(passed=bool(valid), accepted_actions=bridge['accepted_actions'],
                             stop_reason=bridge['latched_stop_reason'], simulation_returncode=run.returncode,
                             wbc_output_frames=report['output_guard']['accepted_frames'],
                             server_records=len(remote_data['records']), request_p95_ms=bridge['request_wall_p95_ms'])
                check.update(body_records_paired=paired, within_simulation_balance_bounds=balanced)
            except (ValueError, OSError, KeyError, subprocess.TimeoutExpired) as exc:
                check['error'] = str(exc)
            finally:
                if server.poll() is None:
                    server.terminate()
                    try: server.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        server.kill()
                        server.wait()
                server.stdout.close()
        summary['checks'].append(check)
        (out / 'summary.json').write_text(json.dumps(summary, indent=2))
    summary['passed'] = all(c['passed'] for c in summary['checks'])
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))
    return 0 if summary['passed'] else 1


if __name__ == '__main__': raise SystemExit(main())
