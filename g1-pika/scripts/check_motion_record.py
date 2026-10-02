import math
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from audit_motion_record import summarize,joint_limits,ROOT


class Tests(unittest.TestCase):
    def test_offsets_limits_and_step(self):
        limits=[dict(name='joint',lower_rad=-1.,upper_rad=1.)]
        rows=[dict(seq=0,measured=[.1],target=[.2]),dict(seq=1,measured=[.2],target=[1.2])]
        result=summarize(rows,limits)[0]
        self.assertAlmostEqual(result['initial_target_offset_rad'],.1)
        self.assertEqual(result['max_target_offset_rad'],1.)
        self.assertEqual(result['max_target_step_rad'],1.)
        self.assertEqual(result['target_outside_urdf_count'],1)
        self.assertEqual(result['measured_outside_urdf_count'],0)

    def test_invalid_data(self):
        limits=[dict(name='joint',lower_rad=-1.,upper_rad=1.)]
        for measured in ([math.nan],[True],[]):
            with self.assertRaises(ValueError): summarize([dict(seq=0,measured=measured,target=[0.])],limits)
        with self.assertRaises(ValueError): summarize([],limits)

    def test_actual_pinned_joint_order(self):
        limits=joint_limits(ROOT/'artifacts/models/g1_pika_closed.urdf')
        self.assertEqual(len(limits),29)
        self.assertEqual(limits[0]['name'],'left_hip_pitch_joint')
        self.assertEqual(limits[-1]['name'],'right_wrist_yaw_joint')


if __name__=='__main__': unittest.main()
