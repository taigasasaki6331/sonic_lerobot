"""Versioned training contract. Positions are absolute radians, not residuals."""
from dataclasses import dataclass
import hashlib
import json
import math
import numpy as np

BODY_NAMES = tuple(
    [f"{s}_{j}" for s in ("left", "right") for j in
     ("hip_pitch", "hip_roll", "hip_yaw", "knee", "ankle_pitch", "ankle_roll")]
    + ["waist_yaw", "waist_roll", "waist_pitch"]
    + [f"{s}_{j}" for s in ("left", "right") for j in
       ("shoulder_pitch", "shoulder_roll", "shoulder_yaw", "elbow", "wrist_roll", "wrist_pitch", "wrist_yaw")]
)
# Same order as official FeedbackReader: waist, then interleaved L/R arms.
UPPER_INDEX = (12, 13, 14, 15, 22, 16, 23, 17, 24, 18, 25, 19, 26, 20, 27, 21, 28)
UPPER_NAMES = tuple(BODY_NAMES[i] for i in UPPER_INDEX)
MODE_NAMES = (
    "idle", "slow_walk", "walk", "run", "squat", "kneel_two_legs", "kneel",
    "lying_face_down", "crawling", "idle_boxing", "walk_boxing", "left_punch",
    "right_punch", "random_punch", "elbow_crawling", "left_hook", "right_hook",
    "forward_jump", "stealth_walk", "injured_walk", "ledge_walking", "object_carrying",
    "stealth_walk_2", "happy_dance_walk", "zombie_walk", "gun_walk", "scare_walk",
)
ACTION_NAMES = tuple(f"target.{n}" for n in UPPER_NAMES) + (
    "velocity.forward", "velocity.left", "velocity.yaw", "height",
) + tuple(f"mode.{n}" for n in MODE_NAMES)
STATE_NAMES = tuple(f"measured.{n}" for n in BODY_NAMES) + (
    "base_quat.w", "base_quat.x", "base_quat.y", "base_quat.z",
) + tuple(f"previous.{n}" for n in ACTION_NAMES)
ACTION_DIM = len(ACTION_NAMES)  # 48; one-hot ALL official modes, no scalar mode regression
STATE_DIM = len(STATE_NAMES)  # 81
SCHEMA = {"version": 1, "action_names": ACTION_NAMES, "state_names": STATE_NAMES,
          "joint_units": "rad", "velocity_frame": "command_heading", "quaternion": "wxyz"}
SCHEMA_ID = hashlib.sha256(json.dumps(SCHEMA, sort_keys=True).encode()).hexdigest()


def finite_vector(value, size):
    result = np.asarray(value, dtype=np.float64)
    if result.shape != (size,) or not np.isfinite(result).all():
        raise ValueError(f"Expected finite vector [{size}], got {result.shape}")
    return result


@dataclass(frozen=True)
class Action:
    upper: tuple[float, ...]
    vx: float = 0.0
    vy: float = 0.0
    yaw_rate: float = 0.0
    height: float = -1.0  # official planner default sentinel
    mode: int = 0

    def __post_init__(self):
        finite_vector(self.upper, 17)
        finite_vector([self.vx, self.vy, self.yaw_rate, self.height], 4)
        if isinstance(self.mode, bool) or int(self.mode) != self.mode or not 0 <= self.mode < 27:
            raise ValueError("Unknown official locomotion mode")

    def vector(self):
        result = np.zeros(ACTION_DIM, dtype=np.float32)
        result[:17] = self.upper
        result[17:21] = [self.vx, self.vy, self.yaw_rate, self.height]
        result[21 + self.mode] = 1.0
        return result

    @classmethod
    def from_vector(cls, value):
        a = finite_vector(value, ACTION_DIM)
        scores = a[21:]
        top = np.sort(scores)[-2:]
        if top[-1] - top[-2] < 0.15:
            raise ValueError("Ambiguous mode prediction")
        return cls(tuple(a[:17]), *a[17:21], int(np.argmax(scores)))

    def stopped(self):
        # Only validated static/slow-walk modes are executable in this initial release.
        mode = 0 if self.mode == 1 else self.mode
        return Action(self.upper, height=self.height, mode=mode)


def state_vector(raw, previous):
    q = finite_vector(raw["body_q_measured"], 29)
    quat = finite_vector(raw["base_quat_measured"], 4)
    norm = np.linalg.norm(quat)
    if norm < 0.5 or norm > 1.5:
        raise ValueError("Invalid measured quaternion")
    return np.concatenate((q, quat / norm, previous.vector())).astype(np.float32)


def initial_action(raw):
    q = finite_vector(raw["body_q_measured"], 29)
    return Action(tuple(q[list(UPPER_INDEX)]))


def planner_fields(action, yaw):
    c, s = math.cos(yaw), math.sin(yaw)
    speed = math.hypot(action.vx, action.vy)
    move = [0.0, 0.0, 0.0] if speed < 1e-8 else [
        (c * action.vx - s * action.vy) / speed,
        (s * action.vx + c * action.vy) / speed, 0.0,
    ]
    return dict(mode=action.mode, movement=move, facing=[c, s, 0.0],
                speed=speed, height=action.height, upper_body_position=action.upper)
