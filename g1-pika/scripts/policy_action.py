"""Pure simulation-only policy boundary. No transport, robot SDK or actuator access."""
import numpy as np

TRACKER_TO_TCP = np.array([[0.,0.,1.],[0.,-1.,0.],[1.,0.,0.]])


def decode_policy_rotation(values):
    """Decode column-layout network rotation6D; reject nonfinite/degenerate values."""
    values = np.asarray(values,dtype=float)
    if values.shape != (6,) or not np.isfinite(values).all():
        raise ValueError('Expected six finite rotation values')
    a,b = values[:3],values[3:]
    if np.linalg.norm(a)<1e-8:
        raise ValueError('Degenerate first rotation column')
    a = a/np.linalg.norm(a)
    b = b-a*(a@b)
    if np.linalg.norm(b)<1e-8:
        raise ValueError('Degenerate second rotation column')
    b = b/np.linalg.norm(b)
    return np.column_stack((a,b,np.cross(a,b)))


def policy_target(action, measured_tcp_in_pelvis, *, action_reference, rotation_layout,
                  max_translation_m=.02, max_rotation_rad=.2, max_gripper_width_m=.1):
    """One fresh h1 action -> pelvis target anchored to current measured TCP.

    Bounds are conservative SIMULATION preflight choices, not measured hardware limits.
    Caller must implement timeouts, sequence handling, rate control and safe stopping.
    Width is returned as metadata only; this function never actuates a gripper.
    """
    if action_reference!='local-relative-h1' or rotation_layout!='columns':
        raise ValueError('Explicit current-TCP h1 / columns contract required')
    bounds = np.array([max_translation_m,max_rotation_rad,max_gripper_width_m])
    if not np.isfinite(bounds).all() or np.any(bounds<=0):
        raise ValueError('Bounds must be finite and positive')
    action = np.asarray(action,dtype=float)
    pose = np.asarray(measured_tcp_in_pelvis,dtype=float)
    if action.shape!=(10,) or not np.isfinite(action).all():
        raise ValueError('Expected finite 10D policy action')
    if (pose.shape!=(4,4) or not np.isfinite(pose).all()
            or not np.allclose(pose[3],[0,0,0,1],atol=1e-8,rtol=0)):
        raise ValueError('Invalid measured TCP transform')
    rotation = pose[:3,:3]
    if (not np.allclose(rotation.T@rotation,np.eye(3),atol=1e-6,rtol=0)
            or abs(np.linalg.det(rotation)-1)>1e-6):
        raise ValueError('Measured TCP rotation must be in SO(3)')
    delta_rotation = decode_policy_rotation(action[3:9])
    angle = float(np.arccos(np.clip((np.trace(delta_rotation)-1)/2,-1,1)))
    if np.linalg.norm(action[:3])>max_translation_m or angle>max_rotation_rad:
        raise ValueError('Action exceeds simulation step bound; not clipped')
    if not 0 <= action[9] <= max_gripper_width_m:
        raise ValueError('Width outside simulation bound; not clipped')
    target = pose.copy()
    target[:3,3] += rotation@TRACKER_TO_TCP@action[:3]
    target[:3,:3] = rotation@TRACKER_TO_TCP@delta_rotation@TRACKER_TO_TCP.T
    return target,float(action[9])
