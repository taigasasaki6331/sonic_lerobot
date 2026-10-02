"""Saved lifecycle replay and journal integrity tests; fixture tensors only."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from body_lifecycle import DEFAULT
from record_body_lifecycle import replay, verify_saved
from sonic_process import strict_message
from sonic_startup_ablation import save, sha
from check_body_lifecycle import profile, body


class Tests(unittest.TestCase):
    def data(self):
        config=strict_message(DEFAULT.read_bytes()); config.update(init_duration_s=.1,settle_duration_s=.04)
        frames=[body(i) for i in range(20)]
        return frames,profile(),config

    def test_fixture_pose_confirmation_never_means_physical_readiness(self):
        result,commands=replay(*self.data())
        self.assertIs(result['diagnostic_protocol_passed'],True)
        self.assertEqual(result['control_target_count'],0)
        self.assertTrue(any(event['op']=='diagnostic_pose_settled' for event in result['events']))
        self.assertIs(result['final_status']['physical_stop_validated'],False)
        self.assertEqual(len(commands),result['writer_record_count'])

    def test_repeated_source_clock_rejected(self):
        frames,p,c=self.data(); frames[1]['receive_monotonic_s']=frames[0]['receive_monotonic_s']
        with self.assertRaises(ValueError): replay(frames,p,c)

    def test_saved_journal_recomputed_and_tamper_rejected(self):
        frames,p,c=self.data(); result,commands=replay(frames,p,c)
        with tempfile.TemporaryDirectory(prefix='body-lifecycle-test-') as temporary:
            path=Path(temporary)
            save(path/'profile.json',p); save(path/'config.json',c); save(path/'source-body.json',dict(frames=frames))
            with (path/'commands.jsonl').open('x') as file:
                for command in commands: file.write(json.dumps(command)+'\n')
            result['output_file_sha256']={name:sha(path/name) for name in ('profile.json','config.json','source-body.json','commands.jsonl')}
            save(path/'report.json',result)
            self.assertIs(verify_saved(path)['integrity_passed'],True)
            with (path/'commands.jsonl').open('a') as file: file.write('{}\n')
            with self.assertRaisesRegex(ValueError,'checksum'): verify_saved(path)


if __name__=='__main__': unittest.main()
