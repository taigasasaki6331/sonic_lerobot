import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_sonic_replay import summarize


class Tests(unittest.TestCase):
    def setUp(self):
        self.request = dict(source_sha256='test', frames=[dict(seq=9, measured_q=[0]*29)])
        self.result = dict(source_sha256='test', action_history_mode='input_file',
                           outputs=[dict(seq=9, q_target_hardware=[.1]*29, encoder_decoder_wall_ms=1)])

    def test_summary(self):
        summary = summarize(self.request, self.result)
        self.assertAlmostEqual(summary['max_target_difference_rad'], .1)
        self.assertEqual(summary['windows'], 1)

    def test_source_and_sequence(self):
        for field in ('source', 'seq'):
            result = copy.deepcopy(self.result)
            if field == 'source': result['source_sha256'] = 'wrong'
            else: result['outputs'][0]['seq'] = 10
            with self.assertRaises(ValueError): summarize(self.request, result)

    def test_invalid_outputs(self):
        for target in ([0]*28, [float('nan')]*29):
            result = copy.deepcopy(self.result)
            result['outputs'][0]['q_target_hardware'] = target
            with self.assertRaises(ValueError): summarize(self.request, result)

    def test_gripper_separate(self):
        self.request['frames'][0]['gripper_width_m'] = .04
        self.result['outputs'][0].update(gripper_width_m=.04, gripper_actuated=False)
        self.assertEqual(summarize(self.request, self.result)['gripper_width_metadata_count'], 1)
        self.result['outputs'][0]['gripper_width_m'] = .05
        with self.assertRaises(ValueError): summarize(self.request, self.result)


if __name__ == '__main__': unittest.main()
