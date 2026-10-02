"""Strict mode-0 observation layout for the pinned low_latency SONIC model.

Equations follow pinned G1Deploy Gather* functions (Apache-2.0, vendor LICENSE).
This module does not sample or fabricate histories; callers supply 10 frames.
"""
import re
import hashlib
import numpy as np
from sonic_reference import ReferencePacker, UPSTREAM, MAPPING


def rotation(q):
    q = np.asarray(q,dtype=float)
    if q.shape != (4,) or not np.isfinite(q).all() or abs(np.linalg.norm(q)-1)>1e-4:
        raise ValueError('Expected normalized wxyz')
    w,x,y,z=q
    return np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
                     [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
                     [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])


def array(value, shape):
    value = np.asarray(value,dtype=float)
    if (value.shape != shape or not np.isfinite(value).all()
            or np.any(np.abs(value)>np.finfo(np.float32).max)):
        raise ValueError('Invalid observation shape or finite values: '+str(shape))
    return value


class ObservationBuilder:
    def __init__(self):
        self.order = ReferencePacker().order
        gatherer=UPSTREAM/'gear_sonic_deploy/src/g1/g1_deploy_onnx_ref/src/g1_deploy_onnx_ref.cpp'
        if hashlib.sha256(gatherer.read_bytes()).hexdigest() != '6fa5594c372e89b4df6fe8f49114225dbfa77c2088abaddf04c555657cb1300c':
            raise ValueError('Upstream observation gatherer changed; re-audit required')
        source = (UPSTREAM/MAPPING).read_text()
        body = re.search(r'default_angles\s*=\s*\{([^}]+)\}',source).group(1)
        body = re.sub(r'//[^\n]*','',body)
        self.defaults = np.array([float(v) for v in body.split(',') if v.strip()])
        if self.defaults.shape != (29,): raise ValueError('Defaults schema changed')

    def encoder(self, reference_q, reference_dq, reference_quat, current_quat):
        # All inputs: hardware order, absolute joint radians; heading offset is zero.
        q=array(reference_q,(10,29)); dq=array(reference_dq,(10,29))
        quat=array(reference_quat,(10,4)); current=rotation(current_quat)
        orientation=np.array([(current.T @ rotation(v))[:,:2].reshape(6) for v in quat])
        result=np.zeros(1247,dtype=np.float32)
        # Mode scalar 0 plus 3 padding slots, NOT a one-hot indicator.
        result[4:294]=q[:,self.order].reshape(-1)
        result[294:584]=dq[:,self.order].reshape(-1)
        result[584:644]=orientation.reshape(-1)
        # Teleop/SMPL slots stay zero as in upstream mode-filtered gatherer.
        return result

    def decoder_tail(self, q, dq, gyro, quat, last_action):
        # Histories are oldest -> newest. Last action is raw SONIC output in IsaacLab order.
        q=array(q,(10,29)); dq=array(dq,(10,29)); gyro=array(gyro,(10,3))
        quat=array(quat,(10,4)); action=array(last_action,(10,29))
        gravity=np.array([rotation(v).T @ np.array([0.,0.,-1.]) for v in quat])
        return np.concatenate([gyro.reshape(-1), (q-self.defaults)[:,self.order].reshape(-1),
                               dq[:,self.order].reshape(-1),action.reshape(-1),gravity.reshape(-1)]).astype(np.float32)

    @staticmethod
    def require_50hz(timestamps):
        times=array(timestamps,(10,))
        if not np.allclose(np.diff(times),.02,rtol=0,atol=.002):
            raise ValueError('Require observed 50Hz history; do not treat sparse records as 50Hz')
