"""MuJoCo model/coordinate checks only; no SONIC, GPU or hardware connection."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import mujoco
import numpy as np
from sonic_mujoco import layout,body_state,validate_timing
from body_lifecycle_profile import load_profile


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=Path(__file__).resolve().parents[1]
        cls.profile=load_profile()
        cls.model=mujoco.MjModel.from_xml_path(str(root/'vendor/GR00T-WholeBodyControl/decoupled_wbc/sim2mujoco/resources/robots/g1/g1_gear_wbc.xml'))

    def test_free_base_name_based_actuator_layout(self):
        joints,actuators=layout(self.model,self.profile['names'])
        self.assertEqual((self.model.nq,self.model.nv,self.model.nu),(36,35,29))
        self.assertEqual(self.model.neq,0)
        self.assertEqual(list(self.model.actuator_trnid[actuators,0]),list(joints))
        reverse_j,reverse_a=layout(self.model,self.profile['names'][::-1])
        self.assertEqual(list(reverse_j),list(joints[::-1])); self.assertEqual(list(reverse_a),list(actuators[::-1]))

    def test_state_quaternion_and_angular_velocity_are_local_pelvis(self):
        model=self.model; data=mujoco.MjData(model); joints,_=layout(model,self.profile['names'])
        data.qpos[model.jnt_qposadr[joints]]=self.profile['defaults']
        data.qpos[3:7]=[2**-.5,0.,0.,2**-.5]
        data.qvel[3:6]=[.1,.2,.3]
        state=body_state(model,data,joints)
        np.testing.assert_allclose(state['quat'],data.qpos[3:7],atol=1e-12)
        np.testing.assert_allclose(state['gyro'],data.qvel[3:6],atol=1e-12)
        np.testing.assert_allclose(state['q'],self.profile['defaults'],atol=0)

    def test_bad_joint_name_or_duplicates_rejected(self):
        with self.assertRaises((ValueError,KeyError)): layout(self.model,['unknown']*29)
        with self.assertRaises(ValueError): layout(self.model,[self.profile['names'][0]]*29)

    def test_timing_rejects_nonfinite_off_grid_and_out_of_range(self):
        for seconds,warmup in ((3,.2),(15,.2),(30,1)):
            validate_timing(seconds,warmup)
        for seconds,warmup in ((float('nan'),.2),(3,float('inf')),(3,.21),(3.01,.2),(61,.2),(3,.1)):
            with self.assertRaises(ValueError): validate_timing(seconds,warmup)


if __name__=='__main__': unittest.main()
