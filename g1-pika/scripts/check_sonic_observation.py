from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from sonic_observation import ObservationBuilder, rotation


class Tests(unittest.TestCase):
    def setUp(self): self.builder=ObservationBuilder()
    def test_encoder(self):
        q=np.tile(np.arange(29),(10,1)); quat=np.tile([1,0,0,0],(10,1))
        v=self.builder.encoder(q,q+1,quat,quat[0])
        self.assertEqual(v.shape,(1247,))
        np.testing.assert_array_equal(v[:4],0)
        np.testing.assert_array_equal(v[4:7],[0,6,12])
        np.testing.assert_array_equal(v[584:590],[1,0,0,1,0,0])
        np.testing.assert_array_equal(v[644:],0)
    def test_decoder(self):
        q=np.tile(self.builder.defaults,(10,1)); quat=np.tile([1,0,0,0],(10,1))
        gyro=np.arange(30).reshape(10,3); action=np.arange(290).reshape(10,29)
        v=self.builder.decoder_tail(q,np.zeros_like(q),gyro,quat,action)
        self.assertEqual(v.shape,(930,))
        np.testing.assert_array_equal(v[:30],gyro.reshape(-1))
        np.testing.assert_array_equal(v[30:610],0)
        np.testing.assert_array_equal(v[610:900],action.reshape(-1))
        np.testing.assert_array_equal(v[-3:],[0,0,-1])
    def test_rotated(self):
        q=[np.sqrt(.5),0,0,np.sqrt(.5)]
        np.testing.assert_allclose(rotation(q) @ [1,0,0],[0,1,0],atol=1e-10)
    def test_timestamp(self):
        self.builder.require_50hz(np.arange(10)*.02)
        with self.assertRaises(ValueError): self.builder.require_50hz(np.arange(10)*.2)
    def test_invalid(self):
        for q in ([0,0,0,0],[1,0,0,np.nan],[1,0,0]):
            with self.assertRaises(ValueError): rotation(q)


if __name__=='__main__': unittest.main()
