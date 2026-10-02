"""Check joint mapping, TCP kinematics, mass and gravity across both engines."""
import json
from pathlib import Path
import sys

import mujoco
import numpy as np
import pinocchio as pin
from scipy.spatial.transform import Rotation

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / "vendor/GR00T-WholeBodyControl"
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(UPSTREAM))
from pika_model import build_pika_model, instantiate_pika_robot


def main():
    xml, urdf, provenance = build_pika_model(UPSTREAM, ROOT)
    model = mujoco.MjModel.from_xml_path(str(xml))
    data = mujoco.MjData(model)
    robot = instantiate_pika_robot(urdf, UPSTREAM)
    assert (model.nq, model.nv, model.nu, robot.num_dofs) == (36, 35, 29, 29)
    assert model.neq == 0 and model.jnt_type[0] == mujoco.mjtJoint.mjJNT_FREE
    names = [model.joint(i).name for i in range(1, 30)]
    indices = [robot.dof_index(name) for name in names]
    assert indices == robot.get_joint_group_indices("body")
    assert not any("_hand_" in model.body(i).name for i in range(model.nbody))
    for side in ("left", "right"):
        for suffix in ("gripper_base", "finger_a", "finger_b"):
            geom = model.geom(f"{side}_pika_{suffix}_collision")
            assert geom.contype[0] == 1 and geom.conaffinity[0] == 1
        assert abs(model.body(f"{side}_wrist_yaw_link").mass[0] - 0.08457647) < 1e-10
    # Pinocchio's fixed-base total excludes inertia attached to the universe.
    total_mass_pin = (pin.computeTotalMass(robot.pinocchio_wrapper.model)
                      + robot.pinocchio_wrapper.model.inertias[0].mass)
    total_mass_mj = float(model.body_mass.sum())
    assert abs(total_mass_pin - total_mass_mj) < 1e-8
    rng = np.random.default_rng(20260914)
    max_position, max_rotation, max_gravity = 0.0, 0.0, 0.0
    for _ in range(30):
        q = robot.clip_configuration(rng.normal(0, 0.15, robot.num_dofs))
        data.qpos[7:] = q[indices]
        data.qpos[3:7] = np.roll(Rotation.from_rotvec(rng.normal(0, 0.1, 3)).as_quat(), 1)
        mujoco.mj_forward(model, data)
        robot.cache_forward_kinematics(q, auto_clip=False)
        tcp_rotation = robot.frame_placement("right_pika_tcp").rotation
        tracker_rotation = robot.frame_placement("right_pika_tracking_frame").rotation
        assert np.allclose(tcp_rotation.T @ tracker_rotation,
                           [[0, 0, 1], [0, -1, 0], [1, 0, 0]], atol=1e-12)
        pelvis = data.body("pelvis")
        rotation = pelvis.xmat.reshape(3, 3)
        for side in ("left", "right"):
            name = f"{side}_pika_tcp"
            pose = robot.frame_placement(name)
            actual = data.body(name)
            position = rotation.T @ (actual.xpos - pelvis.xpos)
            orientation = rotation.T @ actual.xmat.reshape(3, 3)
            max_position = max(max_position, float(np.max(np.abs(position - pose.translation))))
            max_rotation = max(max_rotation, float(np.max(np.abs(orientation - pose.rotation))))
        robot.pinocchio_wrapper.model.gravity.linear = rotation.T @ model.opt.gravity
        gravity = pin.rnea(robot.pinocchio_wrapper.model, robot.pinocchio_wrapper.data,
                           q, np.zeros(29), np.zeros(29))[indices]
        max_gravity = max(max_gravity, float(np.max(np.abs(gravity - data.qfrc_bias[6:]))))
    assert max_position < 1e-5, max_position
    assert max_rotation < 1e-5, max_rotation
    assert max_gravity < 1e-4, max_gravity
    report = {"passed": True, "samples": 30, "robot_mass_mujoco_kg": total_mass_mj,
              "robot_mass_pinocchio_kg": total_mass_pin, "max_tcp_position_difference_m": max_position,
              "max_tcp_rotation_matrix_difference": max_rotation,
              "max_gravity_torque_difference_Nm": max_gravity, "pika_model": provenance}
    print(json.dumps(report, indent=2))
    (ROOT / "artifacts/pika-model-check.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
