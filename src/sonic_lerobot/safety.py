"""Deterministic gateway state machine. No assertion of physical stability."""
from dataclasses import replace
import math
from .schema import Action, initial_action, state_vector


class Supervisor:
    def __init__(self, timeout=0.5, state_timeout=0.25, slew=0.5, dwell=1.0):
        self.timeout, self.state_timeout, self.slew, self.dwell = timeout, state_timeout, slew, dwell
        self.raw = None
        self.state_time = -math.inf
        self.last_input = -math.inf
        self.last_mode_change = -math.inf
        self.epoch = 0
        self.sequence = -1
        self.armed = False
        self.target = self.applied = None
        self.reason = "waiting_for_state"
        self.yaw = 0.0

    def update_state(self, raw, now):
        candidate = initial_action(raw)
        state_vector(raw, candidate)  # validate before refreshing the watchdog
        self.raw, self.state_time = raw, now
        if self.applied is None:
            self.applied = self.target = candidate

    def trip(self, reason):
        if self.armed:
            self.epoch += 1
        self.armed = False
        self.reason = reason
        if self.applied is not None:
            self.target = self.applied = self.applied.stopped()

    def arm(self, now):
        if now - self.state_time > self.state_timeout:
            raise ValueError("Fresh robot state required")
        self.epoch += 1
        self.sequence = -1
        self.armed = True
        self.last_input = now
        self.reason = "active"
        return self.epoch

    def accept(self, action, epoch, sequence, now):
        if not self.armed or epoch != self.epoch or sequence <= self.sequence:
            raise ValueError("Disarmed, stale session, or replayed action; explicit arm required")
        if now - self.state_time > self.state_timeout:
            self.trip("state_timeout")
            raise ValueError("State expired")
        if action.mode not in (0, 1, 4, 5):
            raise ValueError("Mode is represented in schema but not commissioned (allowed: 0,1,4,5)")
        if max(abs(x) for x in action.upper) > 3.2:
            raise ValueError("Upper reference outside broad radians sanity bound")
        if math.hypot(action.vx, action.vy) > 0.3 or abs(action.yaw_rate) > 0.3:
            raise ValueError("Velocity exceeds initial commissioning limits")
        if action.mode != 1 and (abs(action.vx) + abs(action.vy) + abs(action.yaw_rate)) > 1e-6:
            raise ValueError("Static mode requires zero movement")
        if action.height != -1 and not 0.2 <= action.height <= 0.4:
            raise ValueError("Initial height override limited to 0.2..0.4 m")
        if action.mode in (0, 1) and action.height != -1:
            raise ValueError("Standing/walking use planner default height")
        old_mode = self.target.mode
        if action.mode != old_mode:
            if now - self.last_mode_change < self.dwell:
                raise ValueError("Mode dwell not elapsed")
            if old_mode != 0 and action.mode != 0:
                raise ValueError("Transition must pass through IDLE")
            self.last_mode_change = now
        self.target, self.last_input, self.sequence = action, now, sequence

    def tick(self, now, dt):
        if self.armed and now - self.state_time > self.state_timeout:
            self.trip("state_timeout")
        if self.armed and now - self.last_input > self.timeout:
            self.trip("action_timeout")
        if self.applied is None:
            return None
        if self.armed:
            step = self.slew * min(max(dt, 0), 0.04)
            upper = tuple(a + max(-step, min(step, b-a)) for a, b in zip(self.applied.upper, self.target.upper))
            self.applied = replace(self.target, upper=upper)
            self.yaw += self.applied.yaw_rate * min(max(dt, 0), 0.04)
        return self.applied
