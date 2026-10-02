"""Offline WBC output-boundary acceptance; never opens a robot transport."""
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    base = ROOT / 'artifacts/guarded-runtime'
    base.mkdir(parents=True, exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix='run-', dir=base))
    python = str(ROOT / '.venv/bin/python')
    summary = {'scope': 'simulation_output_boundary_not_hardware_stop',
               'hardware_ready': False, 'robot_commands_sent': False,
               'output': str(out), 'checks': []}
    cases = [('nominal', 'none', [], 12),
             *[(fault, fault, [], 12) for fault in ('stale', 'estop', 'nan', 'owner', 'order')],
             ('teacher', 'none', ['--teacher', 'assets/trajectories/episode0.json'], 30),
             ('lerobot', 'none', ['--policy-run', 'artifacts/full-rgb-residual/run-xg1fn3b_',
                                 '--policy-async', '--policy-episode', '39',
                                 '--policy-frames', '206'], 60)]
    with (out / 'unit.log').open('w') as log:
        run = subprocess.run([python, '-I', 'scripts/check_control_guard.py'], cwd=ROOT,
                             stdout=log, stderr=subprocess.STDOUT, timeout=30)
    summary['checks'].append({'name': 'unit', 'passed': run.returncode == 0})
    reasons = {'stale': 'stale_or_future_state', 'estop': 'operator_stop',
               'nan': 'invalid_q', 'owner': 'wrong_owner', 'order': 'joint_order_mismatch'}
    for name, fault, extra, seconds in cases:
        case = out / name
        cmd = [python, '-I', 'scripts/sim_balance.py', '--controller', 'wbc', '--pika',
               '--guard-output', '--guard-fault', fault, '--seconds', str(seconds),
               '--report-dir', str(case)] + extra
        check = {'name': name, 'passed': False}
        try:
            with (out / (name + '.log')).open('w') as log:
                run = subprocess.run(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=180)
            reports = list(case.glob('*-guard-*-latest.json'))
            if len(reports) != 1:
                raise ValueError('Expected exactly one guard report')
            report = json.loads(reports[0].read_text())
            frames = json.loads(next(case.glob('*-guard-*-frames.json')).read_text())
            guard = report['output_guard']
            valid = (len(frames) == guard['accepted_frames'] > 0
                     and [f['seq'] for f in frames] == list(range(len(frames)))
                     and report['motion_commands_sent'] is False
                     and report['hardware_ready'] is False)
            if fault == 'none':
                valid = valid and run.returncode == 0 and report['passed'] and guard['phase'] == 'active'
                if name == 'teacher':
                    valid = valid and report['teacher_completed']
                if name == 'lerobot':
                    valid = valid and report['policy_bridge']['accepted_actions'] == 206
            else:
                valid = (valid and run.returncode == 1 and report['passed'] is False
                         and guard['phase'] == 'fault' and guard['fault_reason'] == reasons[fault]
                         and guard['simulation_stopped_on_fault'] and len(frames) == 100)
            check.update(passed=bool(valid), returncode=run.returncode, guard=guard,
                         report=str(reports[0]))
        except (OSError, ValueError, KeyError, StopIteration, subprocess.TimeoutExpired) as exc:
            check['error'] = str(exc)
        summary['checks'].append(check)
    summary['passed'] = all(c['passed'] for c in summary['checks'])
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
