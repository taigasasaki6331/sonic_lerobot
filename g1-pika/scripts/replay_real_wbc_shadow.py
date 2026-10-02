"""Recorded REAL inputs -> existing WBC -> JSON only. No DDS, SDK, or actuator.

Uses upstream BodyStateProcessor's real convention: base xyz/linear velocity zero,
wxyz IMU quaternion, local gyro, JOINT2MOTOR. Does NOT instantiate that processor
because its constructor can ReleaseMode. MuJoCo is FK-only here, never mj_step.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mujoco
import numpy as np
import yaml
from split_wbc import setup
from wbc_state import WbcState
from wbc_controller import WholeBodyController
from policy_action import policy_target


class RecordedState(WbcState):
    def packet(self):
        packet = super().packet()
        packet['source'] = 'recorded_G1_lowstate_upstream_real_zero_translation'
        packet['world_translation_and_linear_velocity_measured'] = False
        return packet


def convert(body, names, mapping, elapsed):
    if len(body['q']) != 35 or len(body['dq']) != 35:
        raise ValueError('Expected 35 motor slots')
    quat = np.asarray(body['quaternion'], dtype=float)
    gyro = np.asarray(body['gyroscope'], dtype=float)
    if quat.shape != (4,) or not np.isfinite(quat).all() or abs(np.linalg.norm(quat)-1) > .02:
        raise ValueError('Invalid wxyz IMU quaternion')
    if gyro.shape != (3,) or not np.isfinite(gyro).all():
        raise ValueError('Invalid gyro')
    quat = quat / np.linalg.norm(quat)
    return RecordedState(elapsed, names, np.asarray(body['q'])[mapping], np.asarray(body['dq'])[mapping],
                         np.r_[np.zeros(3), quat], np.r_[np.zeros(3), gyro]).validate(names)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--ik-seed-mode', choices=['measured', 'upstream_default', 'projected_measured'], default='measured')
    parser.add_argument('--lower-body-mode', choices=['balance', 'measured'], default='balance',
                        help='Offline ablation only; measured is NOT a physical safe-stop mode')
    parser.add_argument('--target-source', choices=['recorded_action', 'initial_tcp'], default='recorded_action')
    args = parser.parse_args()
    payload = json.loads(args.input.read_text())
    frames = payload['frames']
    if not payload['passed'] or [f['seq'] for f in frames] != list(range(30)):
        raise ValueError('Require complete input-shadow record')
    if any(f['width_source'] != 'encoder_with_legacy_linkage_geometry' for f in frames):
        raise ValueError('Require real encoder-based width')
    report = dict(passed=False, scope='recorded_real_input_WBC_output_only',
                  robot_commands_sent=False, hardware_ready=False, realtime_verified=False,
                  input_sha256=hashlib.sha256(args.input.read_bytes()).hexdigest(), outputs=[],
                  base_xyz_and_linear_velocity='zeros_per_upstream_real_state_processor_not_measured',
                  physics_stepped=False, fk_model='legacy_PIKA_fixed_gripper',
                  ik_seed_mode=args.ik_seed_mode,
                  lower_body_mode=args.lower_body_mode, target_source=args.target_source,
                  policy_observation_frame='current_TCP_relative_identity_plus_encoder_width')
    try:
        upstream, lock, model, data, defaults, urdf, names = setup(args.root)
        config = yaml.safe_load((upstream / 'decoupled_wbc/control/main/teleop/configs/g1_29dof_gear_wbc.yaml').read_text())
        mapping = config['JOINT2MOTOR']
        if mapping != list(range(29)):
            raise ValueError('Unexpected pinned motor mapping')
        first_time = frames[0]['capture']['g1_state']['receive_monotonic_s']
        first = convert(frames[0]['capture']['g1_state'], names, mapping, 0.)
        data.qpos[:] = np.r_[first.base_pose, first.q]
        data.qvel[:] = np.r_[first.base_velocity, first.dq]
        mujoco.mj_forward(model, data)
        wbc = WholeBodyController(upstream, lock, model, data, first.q, pika_urdf=urdf,
                                  ik_seed_mode=('upstream_default' if args.ik_seed_mode == 'projected_measured'
                                                else args.ik_seed_mode))
        if args.ik_seed_mode == 'projected_measured':
            # Numerical experiment only: project the SEED, not observations or outputs.
            full = wbc.robot.q_zero.copy()
            full[wbc.indices] = first.q
            raw_seed = wbc.reduced.full_to_reduced_configuration(full)
            seed = np.clip(raw_seed, wbc.reduced.lower_joint_limits, wbc.reduced.upper_joint_limits)
            wbc.ik.configuration.update(seed)
            for task in wbc.ik.tasks.values():
                task.set_target_from_configuration(wbc.ik.configuration)
            report['numerical_seed_projection'] = dict(
                raw=raw_seed.tolist(), projected=seed.tolist(),
                max_change_rad=float(np.max(np.abs(seed-raw_seed))),
                observations_modified=False, joint_limits_modified=False)
            wbc.ik_seed_mode = args.ik_seed_mode
        # Exercise the upstream activation switch, without any hardware transport.
        wbc.policy.lower_body_policy.use_policy_action = args.lower_body_mode == 'balance'

        class Target:
            value = None
            def target(self, now, origin, measured): return self.value.copy()
            def metrics(self): return {}
        target = Target()
        wbc.policy_bridge = target
        last_time = -1.
        for f in frames:
            body = f['capture']['g1_state']
            elapsed = body['receive_monotonic_s'] - first_time
            if elapsed <= last_time: raise ValueError('Non-increasing body timestamp')
            last_time = elapsed
            state = convert(body, names, mapping, elapsed)
            data.time = elapsed
            data.qpos[:] = np.r_[state.base_pose, state.q]
            data.qvel[:] = np.r_[state.base_velocity, state.dq]
            mujoco.mj_forward(model, data)
            poses = {side:wbc.wrist_pose(data, side) for side in wbc.frames}
            target.value, width = policy_target(f['action'], poses['right'],
                action_reference='local-relative-h1', rotation_layout='columns')
            if args.target_source == 'initial_tcp':
                target.value = wbc.origins['right'].copy()
            result = wbc.step_state(state, poses)
            report['outputs'].append(dict(seq=f['seq'], state=state.packet(),
                q_target=result.tolist(), kp=wbc.kp.tolist(), kd=wbc.kd.tolist(),
                ik_position_error_m=wbc.ik_errors[-2:],
                max_target_minus_measured_rad=float(np.max(np.abs(result-state.q))),
                right_tcp_fk=poses['right'].tolist(), right_tcp_target=target.value.tolist(),
                gripper_width_metadata_m=width))
        report['metrics'] = wbc.metrics()
        targets = np.asarray([row['q_target'] for row in report['outputs']])
        measured = np.asarray([row['state']['q'] for row in report['outputs']])
        times = np.asarray([row['state']['time'] for row in report['outputs']])
        report['joint_diagnostics'] = [dict(
            name=name, first_target_minus_measured_rad=float(targets[0, i]-measured[0, i]),
            max_target_minus_measured_rad=float(np.max(np.abs(targets[:, i]-measured[:, i]))),
            max_sampled_target_rate_rad_s=float(np.max(np.abs(np.diff(targets[:, i])/np.diff(times)))))
            for i, name in enumerate(names)]
        report['diagnostic_limitations'] = [
            'Recorded measurements do not respond to computed commands; this is not closed-loop motion.',
            'Sampled target rates at recording frequency cannot certify 50Hz command continuity.',
            'Measured lower-body targets with PD gains are not damping or zero torque.',
        ]
        report['computation_completed'] = len(report['outputs']) == 30
        report['ik_position_threshold_m'] = .02  # same preflight threshold as existing simulation
        report['ik_position_within_threshold'] = report['metrics']['ik_position_error_max_m'] <= .02
        report['passed'] = report['computation_completed'] and report['ik_position_within_threshold']
    except Exception as exc:
        report['error'] = str(exc)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as file:
        json.dump(report, file, indent=2, allow_nan=False)
    print(json.dumps({k:v for k,v in report.items() if k != 'outputs'}, indent=2))
    print('Recorded WBC outputs:', len(report['outputs']))
    return 0 if report['passed'] else 1


if __name__ == '__main__': raise SystemExit(main())
