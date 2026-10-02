"""Saved LeRobot actions -> upstream IK-only references; no physics or motors."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sonic_tcp_reference import TcpReference


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--urdf', type=Path, default=Path('artifacts/models/g1_pika_closed.urdf'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists(): raise ValueError('Output already exists')
    record = json.loads(args.input.read_text())
    if not record['passed']: raise ValueError('Incomplete input recording')
    builder = TcpReference(args.urdf)
    report = dict(scope='recorded_LeRobot_action_to_kinematic_SONIC_candidate', hardware_ready=False,
                  robot_commands_sent=False, physics_stepped=False,
                  input_sha256=hashlib.sha256(args.input.read_bytes()).hexdigest(),
                  urdf_sha256=builder.urdf_sha256, joint_names=builder.names, outputs=[])
    for frame in record['frames']:
        result = builder.candidate(frame['action'], frame['capture']['g1_state']['q'][:29])
        report['outputs'].append(dict(seq=frame['seq'], **result))
    report['computation_completed'] = True
    report['all_kinematic_targets_within_diagnostic_tolerance'] = all(
        r['kinematic_target_within_diagnostic_tolerance'] for r in report['outputs'])
    report['initial_configuration_violates_upstream_ik_limits'] = sorted(set(
        n for r in report['outputs'] for n in r['measured_outside_upstream_ik_limits']))
    with args.output.open('x') as output: json.dump(report, output, indent=2, allow_nan=False)
    print(json.dumps({k:v for k,v in report.items() if k not in ('outputs','joint_names')}, indent=2))


if __name__ == '__main__': main()
