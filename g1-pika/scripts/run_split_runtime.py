"""Deploy isolated WBC environment on GPU PC, then finite simulation-only tests."""
import argparse
import hashlib
import json
from pathlib import Path
import select
import shlex
import subprocess
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]


def main():
    source_snapshot = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                       for path in (ROOT / 'scripts').glob('*.py')}
    p = argparse.ArgumentParser()
    p.add_argument('--reuse', help='Previously created split-wbc deployment directory')
    p.add_argument('--quick', action='store_true')
    p.add_argument('--new-deployment', action='store_true', help='Create a separate environment instead of cached deployment')
    p.add_argument('--nonblocking', action='store_true', help='Wall-clock physics with independent image and body streams')
    p.add_argument('--gpu-loopback', action='store_true', help='Diagnostic: also run MuJoCo on GPU PC, excluding Wi-Fi')
    a = p.parse_args()
    if a.gpu_loopback and not a.nonblocking: p.error('--gpu-loopback requires --nonblocking')
    cfg = json.loads((ROOT / 'assets/network/mock-runtime.json').read_text())
    base = ROOT / 'artifacts/split-runtime'
    base.mkdir(parents=True, exist_ok=True)
    cached = base / 'deployment.json'
    if not a.reuse and not a.new_deployment and cached.exists():
        a.reuse = json.loads(cached.read_text())['deployment']
    out = Path(tempfile.mkdtemp(prefix='run-', dir=base))
    unit_results = []
    for name in ['check_split_wbc.py', 'check_async_split.py', 'check_wbc_state.py', 'check_control_guard.py',
                 'check_policy_action.py', 'check_policy_bridge.py', 'check_async_policy.py', 'check_zmq_transport.py']:
        with (out / (name + '.log')).open('w') as log:
            run = subprocess.run([str(ROOT / '.venv/bin/python'), '-I', 'scripts/' + name],
                                 cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=30)
        unit_results.append({'name': name, 'passed': run.returncode == 0})
    ssh = ['ssh', '-i', cfg['ssh_key'], '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes',
           '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=5', cfg['gpu_host']]
    def remote(cmd, **kwargs): return subprocess.check_output(ssh + [shlex.join(cmd)], text=True, timeout=120, **kwargs).strip()
    def copy(sources, dest):
        subprocess.run(['rsync', '-az', '-e', shlex.join(ssh[:-1]), *map(str, sources),
                        cfg['gpu_host'] + ':' + dest], check=True, timeout=1200)
    deployment = a.reuse or remote(['mktemp', '-d', cfg['gpu_root'] + '/artifacts/split-wbc-XXXXXX'])
    if not deployment.startswith(cfg['gpu_root'] + '/artifacts/split-wbc-') or any(c in deployment for c in '\n '):
        raise ValueError('Invalid deployment directory')
    (out / 'deployment.json').write_text(json.dumps({'deployment': deployment}))
    if not a.reuse:
        remote(['mkdir', '-p', deployment + '/scripts', deployment + '/vendor', deployment + '/assets'])
        remote(['python3', '-m', 'venv', '--without-pip', deployment + '/.venv'])
        copy([str(ROOT / '.venv/lib/python3.10/site-packages') + '/'], deployment + '/.venv/lib/python3.10/site-packages/')
        copy([ROOT / 'vendor/GR00T-WholeBodyControl'], deployment + '/vendor/')
        copy([ROOT / 'assets/pika'], deployment + '/assets/')
        copy([ROOT / 'sources.lock.json', ROOT / 'requirements-wbc.lock'], deployment + '/')
    scripts = ['split_wbc.py', 'wbc_controller.py', 'wbc_state.py', 'control_guard.py', 'pika_model.py',
               'zmq_transport.py', 'mock_policy_server.py', 'policy_replay_bridge.py', 'policy_action.py',
               'teacher_trajectory.py', 'async_split.py']
    copy([ROOT / 'scripts' / name for name in scripts], deployment + '/scripts/')
    cached.write_text(json.dumps({'deployment': deployment}))
    frames = 30 if a.quick else 206
    observations = out / 'observations'
    with (out / 'export.log').open('w') as log:
        subprocess.run([str(ROOT / '.venv-policy/bin/python'), '-I', 'scripts/export_mock_observations.py',
                        '--output', str(observations), '--frames', str(frames), '--preprocessed'], cwd=ROOT,
                       stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
    checks = []
    remote_observations = None
    if a.gpu_loopback:
        remote_observations = remote(['mktemp', '-d', deployment + '/observations-XXXXXX'])
        copy([str(observations) + '/'], remote_observations + '/')
    cases = [('nominal', 'none', 12 if a.quick else 60)]
    if not a.quick: cases += [('disconnect', 'disconnect', 12), ('stale', 'stale', 12), ('delay', 'delay', 12)]
    if a.nonblocking and not a.quick: cases += [('policy_delay', 'policy_delay', 12)]
    for name, fault, seconds in cases:
        case = out / name
        case.mkdir()
        session = uuid.uuid4().hex
        endpoint = 'tcp://' + cfg['gpu_ip'] + ':6160'
        actor_endpoint = 'tcp://127.0.0.1:6161'
        if a.nonblocking: actor_endpoint = 'tcp://' + cfg['gpu_ip'] + ':6161'
        if a.gpu_loopback:
            endpoint = 'tcp://127.0.0.1:6160'
            actor_endpoint = 'tcp://127.0.0.1:6161'
        actor_report = deployment + '/' + session + '-actor.json'
        wbc_report = deployment + '/' + session + '-wbc.json'
        actor_cmd = [cfg['gpu_root'] + '/.venv-gpu/bin/python', '-I', deployment + '/scripts/mock_policy_server.py',
            '--root', cfg['gpu_root'], '--endpoint', actor_endpoint, '--accept-ip', '127.0.0.1',
            '--session', session, '--frames', str(frames), '--device', 'cuda', '--report', actor_report, '--idle-timeout', '120']
        wbc_cmd = [deployment + '/.venv/bin/python', '-I', deployment + '/scripts/split_wbc.py', 'server',
            '--root', deployment, '--policy-root', cfg['gpu_root'], '--endpoint', endpoint,
            '--actor-endpoint', actor_endpoint, '--accept-ip', cfg['client_ip'], '--session', session,
            '--frames', str(frames), '--fault', fault, '--report', wbc_report]
        if a.nonblocking:
            actor_cmd[actor_cmd.index('--accept-ip') + 1] = cfg['client_ip']
            actor_cmd += ['--publish-endpoint', 'tcp://127.0.0.1:6162']
            wbc_cmd += ['--async-control', '--policy-results', 'tcp://127.0.0.1:6162']
            if fault == 'policy_delay':
                wbc_cmd[wbc_cmd.index('--fault') + 1] = 'none'
                actor_cmd += ['--fault', 'delay']
        if a.gpu_loopback:
            actor_cmd[actor_cmd.index('--accept-ip') + 1] = '127.0.0.1'
            wbc_cmd[wbc_cmd.index('--accept-ip') + 1] = '127.0.0.1'
        processes = []
        logs = []
        check = {'name': name, 'passed': False}
        try:
            for role, cmd in [('actor', actor_cmd), ('wbc', wbc_cmd)]:
                log = (case / (role + '.log')).open('w')
                logs.append(log)
                process = subprocess.Popen(ssh + [shlex.join(['timeout', '600'] + cmd)],
                                           stdout=subprocess.PIPE, stderr=log, text=True)
                processes.append(process)
                if not select.select([process.stdout], [], [], 120)[0]: raise TimeoutError(role + ' startup timeout')
                ready = json.loads(process.stdout.readline())
                if ready.get('ready') is not True or ready.get('session') != session: raise ValueError(role + ' readiness')
            with (case / 'plant.log').open('w') as log:
                plant_cmd = [str(ROOT / '.venv/bin/python'), '-I', 'scripts/split_wbc.py', 'plant',
                    '--root', str(ROOT), '--endpoint', endpoint, '--session', session, '--frames', str(frames),
                    '--seconds', str(seconds), '--observations', str(observations), '--report', str(case / 'plant.json')]
                if a.nonblocking: plant_cmd += ['--async-control', '--actor-endpoint', actor_endpoint]
                if a.gpu_loopback:
                    plant_cmd[0] = deployment + '/.venv/bin/python'
                    plant_cmd[2] = deployment + '/scripts/split_wbc.py'
                    plant_cmd[plant_cmd.index('--root') + 1] = deployment
                    plant_cmd[plant_cmd.index('--observations') + 1] = remote_observations
                    plant_cmd[plant_cmd.index('--report') + 1] = remote_observations + '/' + session + '-plant.json'
                    plant_cmd += ['--policy-root', cfg['gpu_root']]
                    plant_cmd = ssh + [shlex.join(['timeout', '500'] + plant_cmd)]
                result = subprocess.run(plant_cmd,
                    cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=500)
            for process in processes: process.wait(timeout=30)
            for path, label in [(actor_report, 'actor'), (wbc_report, 'wbc')]:
                (case / (label + '.json')).write_text(remote(['cat', path]))
            if a.gpu_loopback:
                (case / 'plant.json').write_text(remote(['cat', remote_observations + '/' + session + '-plant.json']))
                (case / 'commands.json').write_text(remote(['cat', remote_observations + '/commands.json']))
            plant = json.loads((case / 'plant.json').read_text())
            wbc = json.loads((case / 'wbc.json').read_text())
            actor = json.loads((case / 'actor.json').read_text())
            n = wbc['metrics']['policy_bridge']['accepted_actions']
            valid = all(process.returncode == 0 for process in processes) and plant['mujoco_warnings'] == 0
            if fault == 'none':
                if a.nonblocking:
                    valid = (valid and result.returncode == 0 and plant['passed'] and n == frames
                             and len(actor['records']) == frames and abs(plant['sim_seconds'] - seconds) < .01
                             and abs(plant['wall_seconds'] - seconds) < .1
                             and plant['physics_steps_with_body_pending'] > 0
                             and plant['physics_steps_with_image_pending'] > 0
                             and all(plant['worker_shutdown_confirmed'].values())
                             and plant['max_command_age_s'] < .1)
                else:
                    valid = (valid and result.returncode == 0 and plant['passed'] and n == frames
                         and len(actor['records']) == frames and plant['accepted_commands'] == int(seconds * 50)
                         and wbc['guard']['accepted_frames'] == plant['accepted_commands'])
            elif fault == 'policy_delay':
                valid = (valid and result.returncode == 1 and not plant['passed']
                         and 'Image response deadline' in plant['termination'] and n == 5
                         and plant['accepted_commands'] > 100
                         and plant['physics_steps_with_image_pending'] >= 100)
            else:
                valid = valid and result.returncode == 1 and plant['accepted_commands'] == 200 and not plant['passed']
                if fault == 'stale': valid = valid and ('Stale WBC response' in plant['termination'] or 'Stale worker response' in plant['termination'])
                else: valid = valid and ('deadline' in plant['termination'] or 'temporarily unavailable' in plant['termination'])
            import statistics
            def p95(values):
                values = sorted(values)
                return values[round(.95 * (len(values) - 1))] if values else None
            check.update(passed=bool(valid), accepted_actions=n, accepted_commands=plant['accepted_commands'],
                         termination=plant['termination'], height_min=plant['height_min'], tilt_max=plant['tilt_max'],
                         xy_max=plant['xy_max'], actor_records=len(actor['records']),
                         roundtrip_no_image_p95_ms=p95([r['roundtrip_ms'] for r in plant['timings'] if not r['with_image']]),
                         roundtrip_image_p95_ms=p95([r['roundtrip_ms'] for r in plant['timings'] if r['with_image']]),
                         wbc_p95_ms=p95([r['wbc_ms'] for r in plant['timings']]),
                         actor_roundtrip_p95_ms=p95([r['actor_roundtrip_ms'] for r in plant['timings'] if r['with_image']]))
            if a.nonblocking:
                check.update(wall_seconds=plant['wall_seconds'], sim_seconds=plant['sim_seconds'],
                             max_command_age_s=plant['max_command_age_s'], max_physics_lag_s=plant['max_physics_lag_s'],
                             physics_steps_with_body_pending=plant['physics_steps_with_body_pending'],
                             physics_steps_with_image_pending=plant['physics_steps_with_image_pending'],
                             image_roundtrip_p95_ms=p95([r['roundtrip_ms'] for r in plant['image_timings']]))
        except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
            check['error'] = str(exc)
        finally:
            for process in processes:
                if process.poll() is None:
                    process.terminate()
                    try: process.wait(timeout=5)
                    except subprocess.TimeoutExpired: process.kill(); process.wait()
                process.stdout.close()
            for log in logs: log.close()
        checks.append(check)
    summary = {'passed': all(c['passed'] for c in checks + unit_results), 'checks': checks,
               'unit_tests': unit_results, 'deployment': deployment,
               'output': str(out), 'robot_commands_sent': False, 'hardware_ready': False,
               'scope': 'GPU_PC_ACT_and_CPU_WBC_to_local_MuJoCo_lockstep_not_realtime'}
    if a.nonblocking: summary['scope'] = 'wall_clock_physics_nonblocking_body_and_image_network_not_hard_realtime'
    summary['gpu_loopback_diagnostic'] = a.gpu_loopback
    summary['source_sha256'] = {name: source_snapshot[name]
                               for name in scripts + ['run_split_runtime.py', 'export_mock_observations.py']}
    (out / 'summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return 0 if summary['passed'] else 1


if __name__ == '__main__': raise SystemExit(main())
