"""Connect pinned upstream IK, interpolation and WBC classes to local MuJoCo.

No ROS, DDS, robot SDK or device interface is imported here.
Targets are wrist frames, or PIKA TCP frames in the closed-gripper model.
"""

import hashlib
import sys
import time

import mujoco
import numpy as np
import onnxruntime as ort
import yaml


class WholeBodyController:
    def __init__(self, upstream, lock, model, data, defaults, pika_urdf=None, teacher=None,
                 ik_seed_mode='measured'):
        if ik_seed_mode not in ('measured', 'upstream_default'):
            raise ValueError('Unknown IK seed mode')
        self.ik_seed_mode = ik_seed_mode
        self.teacher = teacher
        self.policy_bridge = None
        self.sim_time = 0.0
        sys.path.insert(0, str(upstream))
        import torch
        from decoupled_wbc.control.robot_model.instantiation.g1 import instantiate_g1_robot_model
        from decoupled_wbc.control.robot_model.robot_model import ReducedRobotModel
        from decoupled_wbc.control.teleop.solver.body.body_ik_solver import BodyIKSolver
        from decoupled_wbc.control.teleop.solver.body.body_ik_solver_settings import BodyIKSolverSettings
        from decoupled_wbc.control.policy.g1_gear_wbc_policy import G1GearWbcPolicy
        from decoupled_wbc.control.policy.g1_decoupled_whole_body_policy import G1DecoupledWholeBodyPolicy
        from decoupled_wbc.control.policy.interpolation_policy import InterpolationPolicy

        torch.set_num_threads(1)
        class CpuPolicy(G1GearWbcPolicy):
            """Keep upstream observation/action logic, fix ORT provider/threads."""

            def load_onnx_policy(self, path):
                options = ort.SessionOptions()
                options.intra_op_num_threads = 1
                options.inter_op_num_threads = 1
                session = ort.InferenceSession(
                    path, sess_options=options, providers=["CPUExecutionProvider"]
                )
                if session.get_inputs()[0].shape[-1] != 516 or session.get_outputs()[0].shape[-1] != 15:
                    raise RuntimeError("Unexpected WBC network dimensions")
                return lambda tensor: torch.from_numpy(session.run(None, {
                    session.get_inputs()[0].name: tensor.cpu().numpy()
                })[0])

        resources = upstream / "decoupled_wbc/sim2mujoco/resources/robots/g1"
        walk = resources / "policy/GR00T-WholeBodyControl-Walk.onnx"
        if hashlib.sha256(walk.read_bytes()).hexdigest() != lock["walk_sha256"]:
            raise RuntimeError("Walk model checksum mismatch")
        if pika_urdf is not None:
            from pika_model import instantiate_pika_robot

            self.robot = instantiate_pika_robot(pika_urdf, upstream)
        else:
            self.robot = instantiate_g1_robot_model(waist_location="lower_body")
        names = [mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, i) for i in range(1, 30)]
        self.joint_names = tuple(names)
        self.latest_state = None
        self.indices = [self.robot.dof_index(name) for name in names]
        if self.indices != self.robot.get_joint_group_indices("body"):
            raise RuntimeError("MuJoCo and policy body joint order disagree")
        self.upper_indices = self.robot.get_joint_group_indices("upper_body")
        q = self.robot.q_zero.copy()
        q[self.indices] = defaults
        self.robot.cache_forward_kinematics(q, auto_clip=False)
        self.frames = self.robot.supplemental_info.hand_frame_names
        self.origins = {s: self.robot.frame_placement(f).homogeneous.copy() for s, f in self.frames.items()}
        self.pelvis = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "pelvis")
        self.wrists = {s: mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, f) for s, f in self.frames.items()}
        # Verify kinematics at the initial posture before commanding motion.
        for side in self.frames:
            actual = self.wrist_pose(data, side)
            if not np.allclose(actual, self.origins[side], atol=1e-5):
                raise RuntimeError(f"URDF and MuJoCo wrist frames disagree: {side}")
        self.reduced = ReducedRobotModel.from_active_groups(self.robot, ["arms"])
        settings = BodyIKSolverSettings()
        settings.dt = 0.02
        self.ik = BodyIKSolver(settings)
        self.ik.register_robot(self.reduced)
        # The upstream solver initializes its own feasible numerical seed.
        # Recorded physical observations may lie outside that solver's bounds;
        # they must not be confused with (or changed to match) the IK seed.
        if ik_seed_mode == 'measured':
            self.ik.configuration.update(self.reduced.full_to_reduced_configuration(q))
        for task in self.ik.tasks.values():
            task.set_target_from_configuration(self.ik.configuration)
        lower = CpuPolicy(self.robot, str(resources / "g1_gear_wbc.yaml"),
                               "policy/GR00T-WholeBodyControl-Balance.onnx,policy/GR00T-WholeBodyControl-Walk.onnx")
        self.clock_origin = time.monotonic()
        upper = InterpolationPolicy(self.clock_origin, {
            "target_upper_body_pose": q[self.upper_indices],
            "base_height_command": np.array([0.74]),
            "navigate_cmd": np.zeros(3),
        }, max_change_rate=2.0)
        self.policy = G1DecoupledWholeBodyPolicy(self.robot, lower, upper)
        # Activation applies only to this in-process simulated controller.
        lower.use_policy_action = True
        gains = yaml.safe_load((upstream / "decoupled_wbc/control/main/teleop/configs/g1_29dof_gear_wbc.yaml").read_text())
        self.kp = np.asarray(gains["MOTOR_KP"])
        self.kd = np.asarray(gains["MOTOR_KD"])
        self.tracking = []
        self.ik_errors = []
        self.orientations = []
        self.right_travel = []
        self.target_travel = []
        self.control_ms = []

    def wrist_pose(self, data, side):
        rotation = data.xmat[self.pelvis].reshape(3, 3)
        wrist = self.wrists[side]
        pose = np.eye(4)
        pose[:3, :3] = rotation.T @ data.xmat[wrist].reshape(3, 3)
        pose[:3, 3] = rotation.T @ (data.xpos[wrist] - data.xpos[self.pelvis])
        return pose

    def feedforward(self, data):
        q = self.robot.q_zero.copy()
        q[self.indices] = data.qpos[7:]
        # The Pinocchio model has a fixed pelvis; express world gravity in it.
        self.robot.pinocchio_wrapper.model.gravity.linear = (
            data.xmat[self.pelvis].reshape(3, 3).T @ np.array([0.0, 0.0, -9.81])
        )
        return self.robot.compute_gravity_compensation_torques(
            q, joint_groups="arms", auto_clip=False
        )[self.indices]

    def step(self, data):
        from wbc_state import WbcState
        state = WbcState(float(data.time), self.joint_names, data.qpos[7:], data.qvel[6:],
                         data.qpos[:7], data.qvel[:6]).validate(self.joint_names)
        return self.step_state(state, {side: self.wrist_pose(data, side) for side in self.frames})

    def step_state(self, state, measured_poses):
        """Validated state input; initialization/measurement adapter remains simulation-only."""
        state.validate(self.joint_names)
        for side in self.frames:
            pose = np.asarray(measured_poses[side], dtype=float)
            if (pose.shape != (4, 4) or not np.isfinite(pose).all()
                    or not np.allclose(pose[3], [0, 0, 0, 1])
                    or not np.allclose(pose[:3, :3].T @ pose[:3, :3], np.eye(3), atol=1e-5)
                    or abs(np.linalg.det(pose[:3, :3]) - 1) > 1e-5):
                raise ValueError('Invalid measured TCP pose')
        self.latest_state = state.packet()
        started = time.perf_counter()
        # A 10-second smooth out-and-back reach, following a 2-second settle.
        phase = max(0.0, state.time - 2.0)
        displacement = np.array([0.06, 0.0, 0.04]) * np.sin(np.pi * phase / 10.0) ** 2
        targets = {s: p.copy() for s, p in self.origins.items()}
        targets["right"][:3, 3] += displacement
        if self.teacher is not None:
            targets["right"] = self.teacher.target(state.time, self.origins["right"])
            displacement = targets["right"][:3, 3] - self.origins["right"][:3, 3]
        if self.policy_bridge is not None:
            targets['right']=self.policy_bridge.target(float(state.time),self.origins['right'],measured_poses['right'])
            displacement=targets['right'][:3,3]-self.origins['right'][:3,3]
        self.sim_time = float(state.time)
        solved = self.ik({self.frames[s]: p for s, p in targets.items()})
        q_goal = self.reduced.reduced_to_full_configuration(solved)
        for side in self.frames:
            ik_pose = self.reduced.frame_placement(self.frames[side]).homogeneous
            self.ik_errors.append(float(np.linalg.norm(ik_pose[:3, 3] - targets[side][:3, 3])))
            actual = measured_poses[side]
            self.tracking.append(float(np.linalg.norm(actual[:3, 3] - targets[side][:3, 3])))
            error_rotation = actual[:3, :3].T @ targets[side][:3, :3]
            self.orientations.append(float(np.arccos(np.clip((np.trace(error_rotation) - 1) / 2, -1, 1))))
        self.right_travel.append(float(np.linalg.norm(measured_poses['right'][:3, 3] - self.origins["right"][:3, 3])))
        self.target_travel.append(float(np.linalg.norm(displacement)))
        q, dq = self.robot.q_zero.copy(), np.zeros(self.robot.num_dofs)
        q[self.indices], dq[self.indices] = state.q, state.dq
        self.policy.set_observation({
            "q": q, "dq": dq, "floating_base_pose": state.base_pose.copy(),
            "floating_base_vel": state.base_velocity.copy(),
        })
        now = self.clock_origin + state.time
        self.policy.set_goal({
            "target_upper_body_pose": q_goal[self.upper_indices],
            "base_height_command": np.array([0.74]), "navigate_cmd": np.zeros(3),
            "target_time": now, "interpolation_garbage_collection_time": now - 0.04,
        })
        # Upstream's goal timestamp uses wall time. For synchronous simulation,
        # place it in the same clock domain as get_action (sim time + origin).
        self.policy.last_goal_time = now
        result = self.policy.get_action(time=now)["q"][self.indices]
        if not np.isfinite(result).all():
            raise RuntimeError("Non-finite WBC target")
        self.control_ms.append((time.perf_counter() - started) * 1000)
        return result

    def metrics(self):
        return {
            **(self.policy_bridge.metrics() if self.policy_bridge is not None else {}),
            **(self.teacher.metrics(self.sim_time) if self.teacher is not None else {}),
            "ik_position_error_max_m": max(self.ik_errors, default=0),
            "wrist_tracking_error_max_m": max(self.tracking, default=0),
            "wrist_orientation_error_max_rad": max(self.orientations, default=0),
            "right_wrist_travel_max_m": max(self.right_travel, default=0),
            "right_target_travel_max_m": max(self.target_travel, default=0),
            "whole_body_control_p95_ms": float(np.percentile(self.control_ms, 95)) if self.control_ms else None,
            "ik_solver": self.ik.solver,
            "ik_seed_mode": self.ik_seed_mode,
            "arm_gravity_compensation": True,
            "target_frame": "pelvis", "controlled_frame": self.frames["right"],
        }
