"""LeRobot TCP action -> kinematic full-joint candidate. No controller or IO.

Reuses fixed upstream BodyIKSolver/ReducedRobotModel and migrated PIKA URDF.
This is not a balance planner. Legs/waist are held at the measured configuration.
"""
import hashlib
import re
import sys
from pathlib import Path
import numpy as np

from sonic_reference import UPSTREAM, MAPPING, ReferencePacker
from policy_action import policy_target

IK_HASHES = {
    'control/robot_model/robot_model.py': '5a7bd1da874145bd74c40e67453db36f8feeaac136cb297c478b5e755732fca9',
    'control/teleop/solver/body/body_ik_solver.py': 'ead7b6521b778a169a4cb1402d913662ff7cc4ac7e7e01b49a9621ccdb6997df',
    'control/teleop/solver/body/body_ik_solver_settings.py': 'acc1cf37ecae55dd5ac896d25d2f27fe124ea682537d1d6bfaf8dbdf2942a0d0',
    'control/robot_model/supplemental_info/g1/g1_supplemental_info.py': 'ab973c2ca6cc84d4ac69a5b036bbc8388f22fa75106f64fdae343a2b4b3b0b6a',
}


def validate_pose(pose):
    pose = np.asarray(pose, dtype=float)
    if pose.shape != (4, 4) or not np.isfinite(pose).all():
        raise ValueError('Expected finite SE(3) TCP pose')
    r = pose[:3, :3]
    if (not np.allclose(pose[3], [0, 0, 0, 1], atol=1e-9, rtol=0)
            or not np.allclose(r.T @ r, np.eye(3), atol=1e-7, rtol=0)
            or abs(np.linalg.det(r)-1) > 1e-7):
        raise ValueError('Invalid SE(3) TCP pose')
    return pose.copy()


class TcpReference:
    def __init__(self, urdf):
        ReferencePacker()  # Verify fixed mapping and upstream packer hashes.
        for path, digest in IK_HASHES.items():
            if hashlib.sha256((UPSTREAM/'decoupled_wbc'/path).read_bytes()).hexdigest() != digest:
                raise ValueError('Upstream IK source changed: '+path)
        source = (UPSTREAM/MAPPING).read_text()
        body = re.search(r'default_angles\s*=\s*\{([^}]+)\}', source).group(1)
        self.names = re.findall(r'//\s*(\w+_joint)', body)
        if len(self.names) != 29: raise ValueError('Hardware joint name schema changed')
        sys.path.insert(0, str(UPSTREAM))
        from pika_model import instantiate_pika_robot
        from decoupled_wbc.control.robot_model.robot_model import ReducedRobotModel
        from decoupled_wbc.control.teleop.solver.body.body_ik_solver import BodyIKSolver
        from decoupled_wbc.control.teleop.solver.body.body_ik_solver_settings import BodyIKSolverSettings
        self.Reduced = ReducedRobotModel
        self.Solver = BodyIKSolver
        self.Settings = BodyIKSolverSettings
        self.robot = instantiate_pika_robot(Path(urdf), UPSTREAM)
        self.indices = [self.robot.dof_index(name) for name in self.names]
        self.urdf_sha256 = hashlib.sha256(Path(urdf).read_bytes()).hexdigest()

    def _measured(self, measured_q):
        measured_q = np.asarray(measured_q, dtype=float)
        if measured_q.shape != (29,) or not np.isfinite(measured_q).all():
            raise ValueError('Expected 29 finite measured joints in hardware order')
        full = self.robot.q_zero.copy()
        full[self.indices] = measured_q
        self.robot.cache_forward_kinematics(full, auto_clip=False)
        targets = {side: self.robot.frame_placement(frame).homogeneous.copy()
                   for side, frame in self.robot.supplemental_info.hand_frame_names.items()}
        return full, targets

    def tcp_pose(self, measured_q):
        """Measured right TCP in the fixed-base/pelvis IK frame, no clipping."""
        return self._measured(measured_q)[1]['right']

    def candidate(self, action, measured_q):
        return self._candidate(measured_q, action=action)

    def candidate_pose(self, pose, width, measured_q):
        """Absolute teacher TCP; not a per-step LeRobot action or balance plan."""
        pose = validate_pose(pose)
        if not np.isfinite(width) or not 0 <= width <= .1:
            raise ValueError('Teacher width outside 0..0.1m')
        return self._candidate(measured_q, pose=pose, width=float(width))

    def _candidate(self, measured_q, *, action=None, pose=None, width=None):
        import pinocchio as pin
        full, targets = self._measured(measured_q)
        right_measured = targets['right'].copy()
        if pose is None:
            targets['right'], width = policy_target(action, right_measured,
                action_reference='local-relative-h1', rotation_layout='columns')
        else:
            targets['right'] = pose.copy()
        # Upstream buildReducedModel locks at wrapper.q0, not fixed_values alone.
        # Set that numerical reference to this observation, including measured waist.
        self.robot.pinocchio_wrapper.q0 = full.copy()
        reduced = self.Reduced.from_active_groups(self.robot, ['arms'])
        measured_reduced = reduced.full_to_reduced_configuration(full)
        pin.framesForwardKinematics(reduced.pinocchio_wrapper.model,
                                    reduced.pinocchio_wrapper.data, measured_reduced)
        fk_error = 0.
        for side, frame in self.robot.supplemental_info.hand_frame_names.items():
            actual = reduced.pinocchio_wrapper.data.oMf[reduced.pinocchio_wrapper.model.getFrameId(frame)].homogeneous
            expected = right_measured if side == 'right' else targets[side]
            fk_error = max(fk_error, float(abs(actual-expected).max()))
        if fk_error > 1e-8: raise ValueError('Reduced/full measured FK mismatch')
        settings = self.Settings()
        settings.dt = .02
        solver = self.Solver(settings)
        solver.register_robot(reduced)
        seed = np.clip(measured_reduced, reduced.lower_joint_limits, reduced.upper_joint_limits)
        solver.configuration.update(seed)
        for task in solver.tasks.values(): task.set_target_from_configuration(solver.configuration)
        task_targets = {self.robot.supplemental_info.hand_frame_names[side]: pose for side, pose in targets.items()}
        errors = {}
        for iteration in range(20):
            solved = solver(task_targets)
            candidate = reduced.reduced_to_full_configuration(solved)
            self.robot.cache_forward_kinematics(candidate, auto_clip=False)
            errors = {}
            for side, frame in self.robot.supplemental_info.hand_frame_names.items():
                actual = self.robot.frame_placement(frame).homogeneous
                errors[side] = dict(position_m=float(np.linalg.norm(actual[:3, 3]-targets[side][:3, 3])),
                    orientation_rad=float(np.linalg.norm(pin.log3(actual[:3, :3].T@targets[side][:3, :3]))))
            if all(e['position_m'] < .001 and e['orientation_rad'] < .01 for e in errors.values()): break
        q = candidate[self.indices]
        outside = [name for name, index in zip(self.names, self.indices)
                   if full[index] < self.robot.lower_joint_limits[index]-1e-7
                   or full[index] > self.robot.upper_joint_limits[index]+1e-7]
        return dict(q_reference_hardware=q.tolist(), right_tcp_measured=right_measured.tolist(),
                    right_tcp_target=targets['right'].tolist(), gripper_width_m=width,
                    gripper_actuated=False, errors=errors, iterations=iteration+1,
                    measured_outside_upstream_ik_limits=outside,
                    numerical_seed_projection_max_rad=float(abs(seed-measured_reduced).max()),
                    reduced_full_fk_max_abs_error=fk_error,
                    kinematic_target_within_diagnostic_tolerance=all(
                        e['position_m'] <= .02 and e['orientation_rad'] <= .15 for e in errors.values()),
                    hardware_ready=False, lower_body_reference='measured_hold_not_balance_plan')
