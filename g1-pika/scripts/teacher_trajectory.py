"""Pure 10D action decoding and time-based teacher replay; no hardware imports."""
import numpy as np
from scipy.spatial.transform import Rotation, Slerp


def decode_rotation(values, layout):
    values = np.asarray(values, dtype=float)
    if values.shape != (6,) or not np.isfinite(values).all():
        raise ValueError("Rotation must have six finite values")
    if layout == "columns":
        a, b = values[:3], values[3:]
    elif layout == "rows":
        a, b = values.reshape(3, 2).T
    else:
        raise ValueError("Explicit rotation layout required")
    # Teacher actions originate from rotation matrices, not unnormalized network
    # predictions. Reject a wrong layout instead of silently Gram-Schmidt fixing it.
    if max(abs(np.linalg.norm(a) - 1), abs(np.linalg.norm(b) - 1), abs(a @ b)) > 1e-3:
        raise ValueError("Teacher rotation columns are not orthonormal: check layout")
    a = a / np.linalg.norm(a)
    b = b - a * (a @ b)
    b /= np.linalg.norm(b)
    return np.column_stack((a, b, np.cross(a, b)))


def integrate_action(pose, action, alignment, layout):
    """T_next = T_current * (A * delta * A^-1), with zero axis-origin offset.

    Gripper is an independent future width, not part of SE(3).
    """
    action = np.asarray(action, dtype=float)
    if action.shape != (10,) or not np.isfinite(action).all() or action[9] < 0:
        raise ValueError("Expected finite 10D action and nonnegative gripper width")
    result = pose.copy()
    result[:3, 3] += pose[:3, :3] @ alignment @ action[:3]
    result[:3, :3] = pose[:3, :3] @ alignment @ decode_rotation(action[3:9], layout) @ alignment.T
    return result


class TeacherTrajectory:
    def __init__(self, payload, playback_rate=1.0):
        if payload["format"] != "g1-pika-teacher-v1" or payload["action_reference"] != "local-relative-h1":
            raise ValueError("Unsupported teacher contract")
        if not np.isfinite(playback_rate) or playback_rate <= 0:
            raise ValueError("Playback rate must be positive")
        fps = float(payload["fps"])
        if not np.isfinite(fps) or fps <= 0:
            raise ValueError("Invalid dataset fps")
        frames = payload["frames"]
        if not frames or [f["frame_index"] for f in frames] != list(range(len(frames))):
            raise ValueError("Non-contiguous teacher frames")
        if not np.allclose([f["timestamp"] for f in frames], np.arange(len(frames)) / fps, atol=1e-5):
            raise ValueError("Timestamps disagree with fps")
        alignment = np.asarray(payload["tracker_to_tcp_rotation"], dtype=float)
        expected = np.array([[0, 0, 1], [0, -1, 0], [1, 0, 0]])
        if not np.array_equal(alignment, expected):
            raise ValueError("Unexpected tracker/TCP axes for this model")
        poses = [np.eye(4)]
        for frame in frames:
            poses.append(integrate_action(poses[-1], frame["action"], alignment, payload["rotation_layout"]))
        self.poses = np.asarray(poses)
        self.times = np.arange(len(poses)) / fps / playback_rate
        self.slerp = Slerp(self.times, Rotation.from_matrix(self.poses[:, :3, :3]))
        self.duration = float(self.times[-1])
        self.settle = 2.0
        self.required_seconds = self.settle + self.duration + 2.0
        self.payload = payload
        self.playback_rate = playback_rate

    def target(self, sim_time, origin):
        t = np.clip(sim_time - self.settle, 0, self.duration)
        delta = np.eye(4)
        delta[:3, 3] = [np.interp(t, self.times, self.poses[:, axis, 3]) for axis in range(3)]
        delta[:3, :3] = self.slerp(t).as_matrix()
        return origin @ delta

    def metrics(self, sim_time):
        widths = [f["action"][9] for f in self.payload["frames"]]
        return {
            "teacher_episode": self.payload["episode"], "teacher_frames": len(widths),
            "teacher_fps": self.payload["fps"], "teacher_playback_rate": self.playback_rate,
            "teacher_duration_s": self.duration, "teacher_required_sim_seconds": self.required_seconds,
            "teacher_completed": bool(sim_time + 1e-8 >= self.required_seconds),
            "teacher_rotation_layout": self.payload["rotation_layout"],
            "teacher_translation_scale": 1.0, "teacher_reanchored_to_initial_tcp": True,
            "gripper_actuated": False, "teacher_gripper_width_range_m": [min(widths), max(widths)],
        }
