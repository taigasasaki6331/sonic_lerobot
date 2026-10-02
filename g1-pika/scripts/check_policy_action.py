"""Unit tests for the simulation-only current-TCP action boundary."""
from pathlib import Path
import sys
import unittest
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parent))
from policy_action import policy_target,decode_policy_rotation,TRACKER_TO_TCP


class PolicyActionTests(unittest.TestCase):
    def action(self):
        return np.array([0.,0.,0.,1.,0.,0.,0.,1.,0.,.04])

    def target(self,a,p=None,**kw):
        return policy_target(a,np.eye(4) if p is None else p,
            action_reference='local-relative-h1',rotation_layout='columns',**kw)

    def test_identity_and_width(self):
        target,width = self.target(self.action())
        np.testing.assert_allclose(target,np.eye(4))
        self.assertEqual(width,.04)

    def test_tracker_axis_transform(self):
        a=self.action(); a[:3]=[.001,.002,.003]
        target,_=self.target(a)
        np.testing.assert_allclose(target[:3,3],[.003,-.002,.001])

    def test_anchor_is_measured_pose_not_previous_target(self):
        a=self.action(); a[0]=.01
        pose=np.eye(4); pose[:3,3]=[.2,.3,.4]
        pose[:3,:3]=[[0,-1,0],[1,0,0],[0,0,1]]
        x,_=self.target(a,pose); y,_=self.target(a,pose)
        np.testing.assert_array_equal(x,y)
        np.testing.assert_allclose(x[:3,3],pose[:3,3]+pose[:3,:3]@TRACKER_TO_TCP@a[:3])

    def test_network_columns_projected(self):
        np.testing.assert_allclose(decode_policy_rotation([2,0,0,1,3,0]),np.eye(3))

    def test_invalid_actions_rejected(self):
        for index,value in [(0,np.nan),(0,.021),(9,-.001),(9,.101)]:
            a=self.action(); a[index]=value
            with self.assertRaises(ValueError): self.target(a)
        a=self.action(); a[3:9]=0
        with self.assertRaises(ValueError): self.target(a)
        a=self.action(); a[3:9]=[-1,0,0,0,-1,0]
        with self.assertRaises(ValueError): self.target(a)

    def test_invalid_contract_and_pose(self):
        with self.assertRaises(ValueError):
            policy_target(self.action(),np.eye(4),action_reference='absolute',rotation_layout='columns')
        p=np.eye(4); p[0,0]=-1
        with self.assertRaises(ValueError): self.target(self.action(),p)
        with self.assertRaises(ValueError): self.target(self.action(),max_translation_m=-1)


if __name__=='__main__':
    unittest.main()
