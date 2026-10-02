"""Explicit simulation state contract. Not a Unitree motor/IMU mapping."""
from dataclasses import dataclass
import numpy as np


@dataclass
class WbcState:
    time: float
    names: tuple
    q: np.ndarray
    dq: np.ndarray
    base_pose: np.ndarray
    base_velocity: np.ndarray
    convention: str = 'mujoco_free_joint_qpos_qvel'

    def validate(self, names):
        if self.convention != 'mujoco_free_joint_qpos_qvel':
            raise ValueError('Unverified base-state convention')
        if (len(self.names) != 29 or len(set(self.names)) != 29 or tuple(self.names) != tuple(names)
                or not np.isfinite(self.time) or self.time < 0):
            raise ValueError('State clock/joint order mismatch')
        for key, size in [('q', 29), ('dq', 29), ('base_pose', 7), ('base_velocity', 6)]:
            value = np.asarray(getattr(self, key), dtype=float)
            if value.shape != (size,) or not np.isfinite(value).all():
                raise ValueError('Invalid state ' + key)
            setattr(self, key, value.copy())
        if abs(np.linalg.norm(self.base_pose[3:]) - 1) > 1e-5:
            raise ValueError('Base quaternion must be normalized wxyz')
        return self

    def packet(self):
        return {'time': float(self.time), 'names': list(self.names),
                'q': self.q.tolist(), 'dq': self.dq.tolist(),
                'base_pose': self.base_pose.tolist(), 'base_velocity': self.base_velocity.tolist(),
                'convention': self.convention, 'source': 'simulation_not_G1'}
