from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sonic_joint_trajectory import JointTrajectory


class Tests(unittest.TestCase):
    def test_boundary_and_analytic_velocity(self):
        q = np.linspace(-.3, .3, 29); dq = np.linspace(-.02, .02, 29)
        target = q+.15
        trajectory = JointTrajectory(q, dq, now=2., duration_s=.4)
        trajectory.update(target, now=2.)
        a,b,c = trajectory.sample(2.)
        np.testing.assert_allclose(a,q); np.testing.assert_allclose(b,dq)
        np.testing.assert_allclose(c,0)
        end = trajectory.sample(2.4)
        np.testing.assert_allclose(end[0],target)
        np.testing.assert_allclose(end[1:],0)
        for t in np.linspace(2.02,2.38,15):
            h=1e-6; left=trajectory.sample(float(t-h)); right=trajectory.sample(float(t+h))
            actual=trajectory.sample(float(t))
            np.testing.assert_allclose((right[0]-left[0])/(2*h),actual[1],atol=1e-8,rtol=0)
            np.testing.assert_allclose((right[1]-left[1])/(2*h),actual[2],atol=1e-7,rtol=0)

    def test_replanning_keeps_q_dq_ddq_and_forecast_is_non_mutating(self):
        trajectory=JointTrajectory(np.zeros(29),np.zeros(29),now=0.,duration_s=.4)
        trajectory.update(np.ones(29)*.1,now=0.)
        before=trajectory.sample(.07)
        trajectory.window(now=.07)
        trajectory.update(np.ones(29)*-.02,now=.07)
        for a,b in zip(before,trajectory.sample(.07)):
            np.testing.assert_allclose(a,b,atol=1e-12,rtol=0)
        np.testing.assert_allclose(trajectory.sample(.47)[0],-.02)

    def test_invalid_inputs_and_clock(self):
        for duration in (0.,float('nan'),6.):
            with self.assertRaises(ValueError):
                JointTrajectory(np.zeros(29),np.zeros(29),now=0.,duration_s=duration)
        trajectory=JointTrajectory(np.zeros(29),np.zeros(29),now=1.,duration_s=.4)
        with self.assertRaises(ValueError): trajectory.update(np.zeros(29),now=1.1)
        trajectory.update(np.ones(29),now=1.)
        with self.assertRaises(ValueError): trajectory.update(np.zeros(29),now=.9)
        with self.assertRaises(ValueError): trajectory.update([float('nan')]*29,now=1.1)
        with self.assertRaises(ValueError): trajectory.window(now=.9)

    def test_extrema_detect_between_frame_peak_and_known_smoothstep_rates(self):
        trajectory=JointTrajectory(np.zeros(29),np.zeros(29),now=0.,duration_s=.4)
        trajectory.update(np.ones(29)*.1,now=0.)
        extrema=trajectory.extrema(begin=0.,end=.4)
        np.testing.assert_allclose(extrema['q_min'],0.,atol=1e-12)
        np.testing.assert_allclose(extrema['q_max'],.1,atol=1e-12)
        np.testing.assert_allclose(extrema['dq_max'],1.875*.1/.4,atol=1e-12)
        np.testing.assert_allclose(extrema['ddq_max'],10/np.sqrt(3)*.1/.4**2,atol=1e-11)
        np.testing.assert_allclose(extrema['ddq_min'],-10/np.sqrt(3)*.1/.4**2,atol=1e-11)
        # Same start/end q with nonzero initial velocity must overshoot internally.
        moving=JointTrajectory(np.zeros(29),np.ones(29),now=0.,duration_s=.4)
        moving.update(np.zeros(29),now=0.)
        self.assertGreater(moving.extrema(begin=0.,end=.4)['q_max'][0],.05)
        with self.assertRaises(ValueError): moving.extrema(begin=.1,end=.09)


if __name__=='__main__': unittest.main()
