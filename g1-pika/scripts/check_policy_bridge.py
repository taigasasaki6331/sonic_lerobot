"""No-worker unit tests for sampling, rejection and reference-hold behavior."""
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from policy_replay_bridge import ReplayBridge


class Fake:
    metadata={'fake':True}
    def __init__(self,mode='good'): self.calls=[]; self.mode=mode
    def query(self,seq):
        self.calls.append(seq)
        if self.mode=='timeout': raise TimeoutError('test timeout')
        return {'seq':seq-1 if self.mode=='stale' else seq,'timestamp':seq/30,
                'action':[0,0,0,1,0,0,0,1,0,-1 if self.mode=='invalid' else .04]}


class BridgeTests(unittest.TestCase):
    def test_zero_action_holds_reference_despite_measured_offset(self):
        fake=Fake(); bridge=ReplayBridge(fake,frames=3)
        origin=np.eye(4); measured=origin.copy(); measured[2,3]=-.02
        for t in [0,2.,2.02,2.04,2.06,2.08,3.]:
            np.testing.assert_allclose(bridge.target(t,origin,measured),origin,atol=1e-14)
        self.assertEqual(fake.calls,[0,1,2]); self.assertIsNone(bridge.stop_reason)

    def test_faults_latch_and_stop_further_requests(self):
        for mode in ['stale','invalid','timeout']:
            fake=Fake(mode); bridge=ReplayBridge(fake)
            bridge.target(2.,np.eye(4),np.eye(4))
            bridge.target(2.04,np.eye(4),np.eye(4))
            self.assertIsNotNone(bridge.stop_reason)
            self.assertEqual(fake.calls,[0])

    def test_skipped_slot_rejected(self):
        fake=Fake(); bridge=ReplayBridge(fake)
        bridge.target(2.1,np.eye(4),np.eye(4))
        self.assertIsNotNone(bridge.stop_reason); self.assertEqual(fake.calls,[])

    def test_tracking_bound(self):
        bridge=ReplayBridge(Fake()); measured=np.eye(4); measured[2,3]=-.06
        bridge.target(2.,np.eye(4),measured)
        self.assertIn('tracking',bridge.stop_reason)


if __name__=='__main__': unittest.main()
