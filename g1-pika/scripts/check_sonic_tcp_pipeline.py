import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare_sonic_tcp_pipeline import prepare
from sonic_observation import ObservationBuilder


class Tests(unittest.TestCase):
    def record(self):
        q = ObservationBuilder().defaults.tolist()+[0]*6
        history = [dict(q=q.copy(), dq=[0]*35, quaternion=[1,0,0,0], gyroscope=[0]*3,
                        tick=i, receive_monotonic_s=.02*i) for i in range(10)]
        return dict(frames=[dict(seq=0, action=[0,0,0,1,0,0,0,1,0,.04],
                    capture=dict(g1_state=history[-1], g1_state_history=history))])

    def test_actual_window_and_width(self):
        record = self.record()
        urdf = Path(__file__).resolve().parents[1]/'artifacts/models/g1_pika_closed.urdf'
        result = prepare(record, urdf)
        self.assertEqual(result['scope'], 'diagnostic_real_body_history_zero_prior_actions')
        self.assertEqual(result['frames'][0]['gripper_width_m'], .04)
        self.assertFalse(result['frames'][0]['gripper_actuated'])
        self.assertEqual(len(result['frames'][0]['encoder']), 1247)
        self.assertEqual(len(result['frames'][0]['decoder_tail']), 930)
        self.assertGreater(result['frames'][0]['reference_packet_bytes'], 1280)

    def test_mismatched_endpoint_rejected(self):
        record = self.record()
        record['frames'][0]['capture']['g1_state'] = copy.deepcopy(record['frames'][0]['capture']['g1_state'])
        record['frames'][0]['capture']['g1_state']['tick'] = 42
        urdf = Path(__file__).resolve().parents[1]/'artifacts/models/g1_pika_closed.urdf'
        with self.assertRaises(ValueError): prepare(record, urdf)


if __name__ == '__main__': unittest.main()
