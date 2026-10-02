"""Explicit experimental ACT target codec; raw residual checkpoints are not deployable."""
MODES = ('absolute_width','delta_from_measured_width')


def transform(action,state,mode,inverse=False):
    import torch
    if mode not in MODES:
        raise ValueError('Unknown action codec')
    if action.shape!=state.shape or action.shape[-1]!=10:
        raise ValueError('Action and measured state must have equal (...,10) shapes')
    if not torch.isfinite(action).all() or not torch.isfinite(state).all():
        raise ValueError('Nonfinite codec input')
    if (state[...,9]<0).any():
        raise ValueError('Measured gripper width must be nonnegative')
    result=action.clone()
    if mode=='delta_from_measured_width':
        result[...,9] = action[...,9]+state[...,9] if inverse else action[...,9]-state[...,9]
    return result


def encode_action(action,state,mode):
    return transform(action,state,mode)


def decode_action(action,state,mode):
    return transform(action,state,mode,inverse=True)
