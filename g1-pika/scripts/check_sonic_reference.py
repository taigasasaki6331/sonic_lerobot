"""Serialization tests only; never starts SONIC or connects to a network."""
import json
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sonic_reference import ReferencePacker


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.packer = ReferencePacker()

    def args(self):
        return [np.arange(58).reshape(2,29), np.ones((2,29)),
                np.array([[1.,0,0,0]]*2), np.array([4,5])]

    def test_wire(self):
        msg = self.packer.encode(*self.args())
        self.assertEqual(msg[:4], b'pose')
        h = json.loads(msg[4:1284].rstrip(b'\0'))
        self.assertEqual(h['v'], 1)
        self.assertEqual(h['endian'], 'le')
        self.assertEqual([f['name'] for f in h['fields']], ['joint_pos','joint_vel','body_quat','frame_index'])
        q = np.frombuffer(msg[1284:1284+2*29*4], dtype='<f4').reshape(2,29)
        # Independent named-joint anchors: left hip, right hip, waist yaw, wrists.
        self.assertEqual(q[0,:3].tolist(), [0,6,12])
        self.assertEqual(q[0,23:].tolist(), [19,26,20,27,21,28])
        self.assertEqual(len(msg), 1284+2*(29+29+4)*4+2*8)
        self.assertEqual(np.frombuffer(msg[-16:],dtype='<i8').tolist(), [4,5])

    def test_reject_action10(self):
        a=self.args(); a[0]=np.zeros((2,10))
        with self.assertRaises(ValueError): self.packer.encode(*a)

    def test_reject_invalid(self):
        for index, value in [(0,np.full((2,29),np.nan)), (1,np.zeros((1,29))),
                             (2,np.zeros((2,4))), (3,np.array([5,4])),
                             (3,np.array([4.,5.])), (3,np.array([-1,0]))]:
            with self.subTest(index=index,value=str(value)[:25]):
                a=self.args(); a[index]=value
                with self.assertRaises(ValueError): self.packer.encode(*a)

    def test_does_not_mutate(self):
        a=self.args(); copies=[v.copy() for v in a]
        self.packer.encode(*a)
        for before,after in zip(copies,a): np.testing.assert_array_equal(before,after)


if __name__=='__main__': unittest.main()
