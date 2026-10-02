"""Compare saved inference-only ablations; not a physical tracking test."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_motion_record import joint_limits, summarize, ROOT
from verify_online_record import verify, checked_file


def compare(report_path, recorded_run, hold_run, urdf, trajectory_run=None):
    report_path = Path(report_path)
    integrity = verify(report_path)
    report = json.loads(report_path.read_bytes())
    limits = joint_limits(urdf)
    measured = [json.loads(checked_file(report_path.parent, out['body_input_record'],
                r'body-[0-9]{4}\.json'))['body_history'][-1]['q'][:29]
                for out in report['outputs']]
    result = dict(scope='saved_input_ablation_not_motion_validation', hardware_ready=False,
                  robot_commands_sent=False, integrity=integrity, conditions={})
    import hashlib
    source_sha = hashlib.sha256(report_path.read_bytes()).hexdigest()
    runs=[('recorded_ik', recorded_run), ('measured_hold', hold_run)]
    if trajectory_run is not None: runs.append(('causal_quintic_ik',trajectory_run))
    for reference, directory in runs:
        for history in ('zero', 'recurrent'):
            data = json.loads((Path(directory) / (history + '.json')).read_bytes())
            if (data['source_sha256'] != source_sha or data['reference'] != reference
                    or data['robot_commands_sent'] is not False
                    or len(data['outputs']) != len(measured)):
                raise ValueError('Ablation provenance/count mismatch')
            rows = []
            for original, output, q in zip(report['outputs'], data['outputs'], measured):
                if original['seq'] != output['seq']:
                    raise ValueError('Ablation sequence mismatch')
                rows.append(dict(seq=output['seq'], measured=q, target=output['q_target_hardware']))
            joints = summarize(rows, limits)
            result['conditions'][reference + '/' + history] = dict(
                max_offset_joint=max(joints, key=lambda j: j['max_target_offset_rad']),
                initial_max_target_offset_rad=max(j['initial_target_offset_rad'] for j in joints),
                target_limit_violations=[j for j in joints if j['target_outside_urdf_count']])
            if reference == 'recorded_ik' and history == 'recurrent':
                result['original_reconstruction_max_difference_rad'] = max(
                    abs(a-b) for row, original in zip(rows, report['outputs'])
                    for a,b in zip(row['target'], original['diagnostic_output']['q_target_hardware']))
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('report', 'recorded-run', 'hold-run', 'output'):
        p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--urdf', type=Path, default=ROOT/'artifacts/models/g1_pika_closed.urdf')
    p.add_argument('--trajectory-run',type=Path)
    args = p.parse_args()
    result = compare(args.report, args.recorded_run, args.hold_run, args.urdf,args.trajectory_run)
    with args.output.open('x') as f:
        json.dump(result, f, indent=2, allow_nan=False)
        f.write('\n')
    print(json.dumps(result, indent=2))
