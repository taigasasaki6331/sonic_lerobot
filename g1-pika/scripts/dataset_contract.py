"""Validate current-TCP-relative observations, not absolute-pose differences."""
import numpy as np

from teacher_trajectory import decode_rotation


def relative_observation(gripper_width, layout="columns"):
    if not np.isfinite(gripper_width) or gripper_width < 0:
        raise ValueError("Expected finite nonnegative gripper width in metres")
    if layout not in ("columns", "rows"):
        raise ValueError("Explicit rotation layout required")
    rotation = np.eye(3)[:, :2]
    rotation = rotation.T.reshape(-1) if layout == "columns" else rotation.reshape(-1)
    return np.r_[np.zeros(3), rotation, gripper_width].astype(np.float32)


def inspect_episode(rows, layout):
    if not rows:
        raise ValueError("Empty episode")
    states = np.asarray([r["observation.state"] for r in rows], dtype=float)
    actions = np.asarray([r["action"] for r in rows], dtype=float)
    if states.shape != (len(rows), 10) or actions.shape != states.shape:
        raise ValueError("Expected state/action shape [frames, 10]")
    if not np.isfinite(states).all() or not np.isfinite(actions).all():
        raise ValueError("Non-finite state/action")
    if np.min(states[:, 9]) < 0 or np.min(actions[:, 9]) < 0:
        raise ValueError("Negative gripper width")
    identity_error = float(np.max(np.abs(states[:, :9] - relative_observation(0, layout)[:9])))
    for action in actions:
        decode_rotation(action[3:9], layout)
    # This scalar comparison is meaningful if both streams use the same gripper
    # measurement. Unlike the pose, gripper width is not reset to an identity.
    future_width = np.r_[states[1:, 9], states[-1, 9]]
    width_residual = np.abs(actions[:, 9] - future_width)
    mismatches = np.flatnonzero(width_residual > 1e-6)
    return {
        "state_reference": "current_tcp_identity_plus_measured_gripper",
        "pose_difference_test": "not_applicable_frames_have_different_origins",
        "state_identity_error_max": identity_error,
        "state_contract_passed": identity_error <= 1e-6,
        "action_rotation_contract_passed": True,
        "absolute_pose_trajectory_verified": False,
        "gripper_h1_residual_max_m": float(np.max(width_residual)),
        "gripper_h1_mismatch_count": len(mismatches),
        "gripper_h1_mismatch_frames": [int(rows[i]["frame_index"]) for i in mismatches],
        "gripper_h1_alignment_verified": len(mismatches) == 0,
    }
