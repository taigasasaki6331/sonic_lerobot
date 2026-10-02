"""Offline lifecycle and stop-latch tests. No robot access."""
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from control_guard import ControlGuard,GuardFault,RecordingSink


class Tests(unittest.TestCase):
    def setUp(self):
        self.guard=ControlGuard(['joint'],[-1],[1]); self.owner=object()
        self.guard.start_simulation(self.owner); self.sink=RecordingSink(self.guard)
    def kwargs(self,**updates):
        result=dict(owner=self.owner,seq=0,now=1.,state_time=1.,state_q=[0],
                    names=['joint'],q=[.1],dq=[0],tau=[0],kp=[10],kd=[1])
        result.update(updates); return result
    def test_valid_and_copy(self):
        frame=self.guard.approve(**self.kwargs()); self.sink.append(frame); frame['q'][0]=.9
        self.assertEqual(self.sink.frames[0]['q'],[.1])
    def test_stale_and_latched(self):
        with self.assertRaises(GuardFault): self.guard.approve(**self.kwargs(state_time=.8))
        with self.assertRaises(GuardFault): self.guard.approve(**self.kwargs())
        with self.assertRaises(GuardFault): self.guard.start_simulation(self.owner)
        self.assertEqual(self.guard.accepted,0)
    def test_owner(self):
        with self.assertRaises(GuardFault): self.guard.approve(**self.kwargs(owner=object()))
    def test_estop(self):
        with self.assertRaises(GuardFault): self.guard.approve(**self.kwargs(estop=True))
        self.assertEqual(self.guard.reason,'operator_stop')
    def test_sequence(self):
        with self.assertRaises(GuardFault): self.guard.approve(**self.kwargs(seq=1))
    def test_order(self):
        with self.assertRaises(GuardFault): self.guard.approve(**self.kwargs(names=['other']))
    def test_nonfinite_and_bounds(self):
        for update in [dict(q=[np.nan]),dict(q=[1.1]),dict(tau=[np.inf]),dict(kp=[-1]),dict(q=[]),dict(now=np.nan)]:
            with self.subTest(update=update):
                self.setUp()
                with self.assertRaises(GuardFault): self.guard.approve(**self.kwargs(**update))
    def test_clock(self):
        for stamp in [1.,.9,1.2]:
            self.setUp(); self.guard.approve(**self.kwargs())
            with self.assertRaises(GuardFault): self.guard.approve(**self.kwargs(seq=1,now=stamp,state_time=stamp))
    def test_sink_duplicate(self):
        frame=self.guard.approve(**self.kwargs()); self.sink.append(frame)
        with self.assertRaises(GuardFault): self.sink.append(frame)
    def test_stop_blocks_existing_frame(self):
        frame=self.guard.approve(**self.kwargs())
        with self.assertRaises(GuardFault): self.guard.stop()
        with self.assertRaises(GuardFault): self.sink.append(frame)


if __name__=='__main__': unittest.main()
