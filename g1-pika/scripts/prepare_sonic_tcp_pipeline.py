"""Saved 10D actions -> reused IK -> SONIC encoder input, width kept separate.

The 5Hz body snapshots are explicitly repeated, not relabelled as 50Hz history.
Endpoint references are held; this is not a dynamically valid whole-body plan.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sonic_tcp_reference import TcpReference
from sonic_observation import ObservationBuilder
from sonic_reference import ReferencePacker
from state_history import validate_history


def prepare(record, urdf, components=None):
    ik, observation, packer = components if components is not None else (
        TcpReference(urdf), ObservationBuilder(), ReferencePacker())
    rows = []
    history_flags = ['g1_state_history' in frame['capture'] for frame in record['frames']]
    if any(history_flags) and not all(history_flags): raise ValueError('Mixed measured/synthetic history')
    actual_history = all(history_flags) and bool(history_flags)
    for frame in record['frames']:
        body = frame['capture']['g1_state']
        measured = np.asarray(body['q'][:29])
        candidate = ik.candidate(frame['action'], measured)
        if not candidate['kinematic_target_within_diagnostic_tolerance']:
            raise ValueError('IK target rejected at seq '+str(frame['seq']))
        reference = np.tile(candidate['q_reference_hardware'], (10, 1))
        q = np.tile(measured, (10, 1))
        dq = np.tile(body['dq'][:29], (10, 1))
        quat = np.tile(np.asarray(body['quaternion'], dtype=float), (10, 1))
        norms = np.linalg.norm(quat, axis=1)
        if not np.isfinite(norms).all() or np.any(abs(norms-1) > .01):
            raise ValueError('Invalid measured quaternion')
        quat /= norms[:, None]
        reference_quat = quat.copy()
        gyro = np.tile(body['gyroscope'], (10, 1))
        if actual_history:
            history = validate_history(frame['capture']['g1_state_history'])
            if history[-1] != body: raise ValueError('Snapshot and history endpoint differ')
            q = np.asarray([h['q'][:29] for h in history])
            dq = np.asarray([h['dq'][:29] for h in history])
            quat = np.asarray([h['quaternion'] for h in history], dtype=float)
            quat /= np.linalg.norm(quat, axis=1)[:, None]
            gyro = np.asarray([h['gyroscope'] for h in history])
        packet = packer.encode(reference, np.zeros((10, 29)), reference_quat, np.arange(10))
        rows.append(dict(seq=frame['seq'], measured_q=measured.tolist(),
            absolute_reference=dict(q_hardware=reference.tolist(),dq_hardware=np.zeros((10,29)).tolist(),
                quaternion_wxyz=reference_quat.tolist(),gripper_width_m=candidate['gripper_width_m'],
                gripper_actuated=False,scope='IK_endpoint_hold_not_dynamic_balance_plan'),
            gripper_width_m=candidate['gripper_width_m'], gripper_actuated=False,
            encoder=observation.encoder(reference, np.zeros((10, 29)), reference_quat, quat[-1]).tolist(),
            decoder_tail=observation.decoder_tail(q, dq, gyro,
                                                 quat, np.zeros((10, 29))).tolist(),
            reference_packet_sha256=hashlib.sha256(packet).hexdigest(),
            reference_packet_bytes=len(packet), ik=candidate))
    return dict(scope=('diagnostic_real_body_history_zero_prior_actions' if actual_history else
                       'diagnostic_repeated_snapshot_not_50hz_history'),
        reference='recorded_LeRobot_10D_to_upstream_IK_endpoint_held_not_balance_plan',
        history=('measured_10_frame_body_windows_at_image_times_zero_prior_actions_not_closed_loop'
                 if actual_history else 'sparse_snapshot_repeated_10_times_zero_prior_actions_not_closed_loop'),
        hardware_ready=False, robot_commands_sent=False, physics_stepped=False,
        gripper_channel='separate_width_m_not_Dex3', urdf_sha256=ik.urdf_sha256, frames=rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--urdf', type=Path, default=Path('artifacts/models/g1_pika_closed.urdf'))
    args = parser.parse_args()
    if args.output.exists(): raise ValueError('Output already exists')
    raw = args.input.read_bytes()
    record = json.loads(raw)
    expected_count = 2 if record.get('scope') == 'archived_two_image_pairs_reinferred_not_live' else 30
    if not record['passed'] or [f['seq'] for f in record['frames']] != list(range(expected_count)):
        raise ValueError('Require complete saved input-shadow or two-endpoint reinference record')
    result = prepare(record, args.urdf)
    result['source_sha256'] = hashlib.sha256(raw).hexdigest()
    with args.output.open('x') as output: json.dump(result, output, allow_nan=False)
    print('Prepared recorded-action -> IK -> SONIC diagnostic:', len(result['frames']))


if __name__ == '__main__': main()
