"""Local negative tests for data transfer manifests and bounded job arguments."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parent


class TrainingToolsTests(unittest.TestCase):
    def test_legacy_adapter_rejects_residual_checkpoint(self):
        sys.path.insert(0,str(SCRIPTS))
        from check_policy import check
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)
            (path/'action_codec.json').write_text(json.dumps({'mode':'delta_from_measured_width',
                                                            'requires_custom_action_decode':True}))
            with self.assertRaisesRegex(ValueError,'dedicated decoder'):
                check(path,path)

    def test_gripper_codec_roundtrip_and_no_mutation(self):
        sys.path.insert(0,str(SCRIPTS))
        import torch
        from gripper_codec import encode_action,decode_action
        action=torch.tensor([[.01,0,0,1,0,0,0,1,0,.03]],dtype=torch.float32)
        state=action.clone(); state[0,9]=.04
        original=action.clone()
        encoded=encode_action(action,state,'delta_from_measured_width')
        self.assertLess(float(encoded[0,9]),0)
        torch.testing.assert_close(decode_action(encoded,state,'delta_from_measured_width'),action)
        self.assertTrue(torch.equal(action,original))
        self.assertTrue(torch.equal(encoded[:,:9],action[:,:9]))
        with self.assertRaises(ValueError): encode_action(action,state,'unknown')
        with self.assertRaises(ValueError): encode_action(action,state[:,:9],'absolute_width')

    def test_network_rotation_projection(self):
        sys.path.insert(0,str(SCRIPTS))
        from check_full_rgb_run import decode_prediction
        import numpy as np
        np.testing.assert_allclose(decode_prediction([2,0,0,1,3,0]),np.eye(3))
        with self.assertRaises(ValueError):
            decode_prediction([0,0,0,0,1,0])
        with self.assertRaises(ValueError):
            decode_prediction([1,0,0,2,0,0])

    def run_script(self, script, *args):
        return subprocess.run([sys.executable,'-I',str(SCRIPTS/script),*map(str,args)],
                              capture_output=True,text=True)

    def test_manifest_roundtrip_and_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)/'data'
            (root/'meta').mkdir(parents=True)
            (root/'meta/info.json').write_text('{}')
            manifest = Path(directory)/'manifest.json'
            self.assertEqual(self.run_script('dataset_manifest.py','create','--dataset',root,
                                             '--manifest',manifest).returncode,0)
            self.assertEqual(self.run_script('dataset_manifest.py','verify','--dataset',root,
                                             '--manifest',manifest).returncode,0)
            (root/'meta/info.json').write_text('{"changed":true}')
            self.assertNotEqual(self.run_script('dataset_manifest.py','verify','--dataset',root,
                                                '--manifest',manifest).returncode,0)

    def test_manifest_symlink_and_inside_output_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)/'data'
            (root/'meta').mkdir(parents=True)
            (root/'meta/info.json').write_text('{}')
            self.assertNotEqual(self.run_script('dataset_manifest.py','create','--dataset',root,
                                                '--manifest',root/'manifest.json').returncode,0)
            (root/'linked').symlink_to(root/'meta/info.json')
            self.assertNotEqual(self.run_script('dataset_manifest.py','create','--dataset',root,
                                                '--manifest',Path(directory)/'manifest.json').returncode,0)

    def test_invalid_steps_rejected_before_gpu_or_job_creation(self):
        for script, args in [('train_gpu_smoke.py',[]),('gpu_job.py',['start'])]:
            result = self.run_script(script,*args,'--steps','0')
            self.assertEqual(result.returncode,2)


if __name__ == '__main__':
    unittest.main()
