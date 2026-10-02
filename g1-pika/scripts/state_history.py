"""Validate a measured body history without device/network imports."""
import math


def validate_state(frame):
    for name, size in (('q',35), ('dq',35), ('quaternion',4), ('gyroscope',3)):
        values = frame[name]
        if len(values) != size or not all(type(v) in (int,float) and math.isfinite(v) for v in values):
            raise ValueError('Invalid body history '+name)
    if type(frame['receive_monotonic_s']) not in (int,float) or not math.isfinite(frame['receive_monotonic_s']): raise ValueError('Invalid timestamp')
    if type(frame['tick']) is not int or not 0<=frame['tick']<=0xffffffff: raise ValueError('Invalid uint32 body tick')
    if abs(sum(v*v for v in frame['quaternion'])**.5-1) > .01:
        raise ValueError('Invalid quaternion norm')


def validate_history(frames):
    if len(frames) != 10: raise ValueError('Need ten actual body frames')
    for frame in frames: validate_state(frame)
    for a, b in zip(frames, frames[1:]):
        gap=b['receive_monotonic_s']-a['receive_monotonic_s']
        if not .018 <= gap <= .022:
            raise ValueError('Body history cadence outside 20ms +/-2ms: '+format(gap,'.9f')+'s; ticks '+str(a['tick'])+' -> '+str(b['tick']))
        if not 0<((b['tick']-a['tick']) & 0xffffffff)<0x80000000:
            raise ValueError('Repeated or reversed body tick')
    return frames
