"""Pure SONIC v1 serialization adapter. No sockets, SDK, simulation, or motor IO.

Input is a complete 29-joint reference, NOT a LeRobot 10D action. Reference
generation, physical validity, timing and controller inference are separate.
Uses unmodified Apache-2.0 upstream packer; see vendor LICENSE and source lock.
"""
import hashlib
import importlib.util
from pathlib import Path
import re
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / 'vendor/GR00T-WholeBodyControl'
PACKER = 'gear_sonic/utils/teleop/zmq/zmq_planner_sender.py'
MAPPING = 'gear_sonic_deploy/src/g1/g1_deploy_onnx_ref/include/policy_parameters.hpp'
HASHES = {
    PACKER: 'f33d7715d36cda8ae64b7ce48d4f5a4c74d73fb1eb9a6c17fe85b3456b023f63',
    MAPPING: 'b9332adf07c2c9b75c9b1e0756e57c7a1c2a890d8bb0aa53c3f1905fb739b791',
}


class ReferencePacker:
    def __init__(self, upstream=UPSTREAM):
        for name, digest in HASHES.items():
            if hashlib.sha256((upstream/name).read_bytes()).hexdigest() != digest:
                raise ValueError('SONIC source checksum mismatch: ' + name)
        mapping = (upstream/MAPPING).read_text()
        match = re.search(r'mujoco_to_isaaclab\s*=\s*\{([^}]+)\}', mapping)
        self.order = np.array([int(v) for v in match.group(1).split(',')])
        if sorted(self.order.tolist()) != list(range(29)):
            raise ValueError('Invalid upstream joint permutation')
        spec = importlib.util.spec_from_file_location('pinned_sonic_packer', upstream/PACKER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if module.HEADER_SIZE != 1280:
            raise ValueError('Unexpected header size')
        self.pack = module.pack_pose_message

    def encode(self, q, dq, body_quat, frame_index):
        """Hardware/MuJoCo joint order -> IsaacLab wire order, absolute radians.

        body_quat is a reference wxyz quaternion, NOT inferred world pose.
        The caller supplies velocity; this adapter never invents zero velocity.
        """
        q, dq, quat = (np.asarray(v, dtype=float) for v in (q, dq, body_quat))
        indices = np.asarray(frame_index)
        if q.ndim != 2 or q.shape[1] != 29 or not 1 <= len(q) <= 1000 or dq.shape != q.shape:
            raise ValueError('Require matching [N,29] complete joint references')
        if quat.shape != (len(q), 4) or indices.shape != (len(q),):
            raise ValueError('Quaternion/frame count mismatch')
        if indices.dtype.kind not in 'iu' or np.any(indices < 0) or np.any(indices > np.iinfo(np.int64).max):
            raise ValueError('Invalid frame indices')
        if any(int(b) <= int(a) for a, b in zip(indices[:-1], indices[1:])):
            raise ValueError('Frame indices must increase')
        if not all(np.isfinite(v).all() for v in (q, dq, quat)):
            raise ValueError('Nonfinite reference')
        if not np.allclose(np.linalg.norm(quat, axis=1), 1, atol=1e-4, rtol=0):
            raise ValueError('Nonunit wxyz quaternion')
        if any(np.max(np.abs(v)) > np.finfo(np.float32).max for v in (q, dq, quat)):
            raise ValueError('Float32 overflow')
        return self.pack(dict(joint_pos=q[:, self.order].astype('<f4'),
                              joint_vel=dq[:, self.order].astype('<f4'),
                              body_quat=quat.astype('<f4'),
                              frame_index=indices.astype('<i8')), topic='pose', version=1)
