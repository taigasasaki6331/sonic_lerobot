"""Causal joint-reference interpolation for record-only SONIC diagnostics.

Time and q/dq/ddq are mathematical references, not commanded/measured motion.
Replanning preserves position, velocity and acceleration. No balance/contact,
torque, collision, rate-limit or physical initial-pose validation is provided.
"""
import math
import numpy as np
from sonic_observation import array


class JointTrajectory:
    def __init__(self, q, dq, *, now, duration_s):
        if type(duration_s) not in (int, float) or not math.isfinite(duration_s) or not .02 <= duration_s <= 5:
            raise ValueError('Diagnostic duration must be 0.02..5 seconds')
        self.duration = float(duration_s)
        self.start = self._time(now)
        self.last_update = self.start
        self.coefficients = np.zeros((6, 29))
        self.coefficients[0] = array(q, (29,))
        self.coefficients[1] = array(dq, (29,)) * self.duration
        self.endpoint = array(q, (29,)).copy()
        self.initialized = False

    @staticmethod
    def _time(now):
        if type(now) not in (float, int) or not math.isfinite(now):
            raise ValueError('Finite reference time required')
        return float(now)

    def sample(self, now):
        now = self._time(now)
        if now < self.start:
            raise ValueError('Reference time precedes current segment')
        if not self.initialized:
            if now != self.start:
                raise ValueError('Initial reference only exists at its measured seed time')
            return self.endpoint.copy(), self.coefficients[1] / self.duration, np.zeros(29)
        if now >= self.start + self.duration:
            return self.endpoint.copy(), np.zeros(29), np.zeros(29)
        u = (now - self.start) / self.duration
        c = self.coefficients
        q = sum(c[i] * u**i for i in range(6))
        dq = sum(i*c[i]*u**(i-1) for i in range(1, 6)) / self.duration
        ddq = sum(i*(i-1)*c[i]*u**(i-2) for i in range(2, 6)) / self.duration**2
        return q, dq, ddq

    def update(self, target, *, now):
        now = self._time(now)
        target = array(target, (29,))
        if now < self.last_update:
            raise ValueError('Reference update clock moved backwards')
        if not self.initialized and now != self.start:
            raise ValueError('Initial target must share measured seed time')
        q, dq, ddq = self.sample(now)
        c = np.zeros((6, 29)); c[0] = q
        c[1] = dq * self.duration; c[2] = .5*ddq*self.duration**2
        residual = target - c[0] - c[1] - c[2]
        # Boundary conditions at u=1: q=target, dq=0, ddq=0.
        c[3:] = np.linalg.solve(np.array([[1.,1.,1.],[3.,4.,5.],[6.,12.,20.]]),
                                np.stack([residual, -c[1]-2*c[2], -2*c[2]]))
        if not np.isfinite(c).all():
            raise ValueError('Reference coefficient overflow')
        self.coefficients = c; self.endpoint = target.copy()
        self.start = now; self.last_update = now; self.initialized = True

    def window(self, *, now, frames=10, dt=.02):
        if frames != 10 or dt != .02:
            raise ValueError('Require pinned SONIC 10-frame/20ms lookahead')
        samples = [self.sample(self._time(now)+i*dt) for i in range(frames)]
        return tuple(np.asarray([row[i] for row in samples]) for i in range(3))

    def extrema(self, *, begin, end):
        """Numerical polynomial extrema, including between supplied time points.

        Uses stationary roots in normalized time, not an interval-arithmetic
        certificate. A forecast beyond segment completion includes the hold.
        """
        begin=self._time(begin); end=self._time(end)
        if not self.initialized or begin<self.start or end<begin:
            raise ValueError('Invalid initialized trajectory interval')
        low=min(1.,(begin-self.start)/self.duration)
        high=min(1.,(end-self.start)/self.duration)
        result={}
        for name,order in [('q',0),('dq',1),('ddq',2)]:
            bounds=[]
            for joint in range(29):
                polynomial=np.polynomial.polynomial.polyder(self.coefficients[:,joint],m=order)
                derivative=np.polynomial.polynomial.polyder(polynomial)
                candidates=[low,high]
                if np.any(derivative!=0):
                    for root in np.polynomial.polynomial.polyroots(derivative):
                        if abs(root.imag)<1e-7 and low<=root.real<=high:
                            candidates.append(float(root.real))
                values=np.polynomial.polynomial.polyval(candidates,polynomial)/self.duration**order
                if end>=self.start+self.duration:
                    values=np.append(values,self.endpoint[joint] if order==0 else 0.)
                if not np.isfinite(values).all(): raise ValueError('Nonfinite reference extrema')
                bounds.append((float(min(values)),float(max(values))))
            result[name+'_min']=np.asarray([a for a,b in bounds])
            result[name+'_max']=np.asarray([b for a,b in bounds])
        return result
