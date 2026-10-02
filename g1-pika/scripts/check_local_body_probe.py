"""Probe helper tests: no SSH, sockets, devices or deployment."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from probe_local_body import causal_age,validate_topology


class Tests(unittest.TestCase):
    def test_causal_age_uses_only_local_roundtrip_and_reported_local_age(self):
        self.assertAlmostEqual(causal_age(.02,100.,100.01),.03)
        self.assertAlmostEqual(causal_age(.02,100000.,100000.01),.03)
    def test_age_rejects_invalid_and_expired_without_clipping(self):
        for values in ((-.01,1.,1.01),(.01,1.,.9),(.01,1.,1.1),(.1,1.,1.),
                       (float('nan'),1.,1.),(.01,True,1.)):
            with self.assertRaises(ValueError): causal_age(*values)
    def test_no_silent_topology_fallback(self):
        access=dict(g1_host='unitree@192.0.2.11',g1_interface='enP8p1s0',gpu_wired_ip='192.0.2.12')
        validate_topology(access)
        for key in access:
            changed=dict(access); changed[key]='different'
            with self.assertRaises(ValueError): validate_topology(changed)


if __name__=='__main__': unittest.main()
