"""File-only bundle tests; no torch, GPU, socket or robot needed."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tarfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent))
from policy_bundle import FILES, CODE, CAMERAS, create, verify, sha

ROOT = Path(__file__).resolve().parents[1]


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.relative = 'models/candidate'
        self.checkpoint = self.root / self.relative
        self.checkpoint.mkdir(parents=True)
        features = {'observation.state': {'type': 'STATE', 'shape': [10]}}
        features.update({key: {'type': 'VISUAL', 'shape': [3, 96, 128]} for key in CAMERAS.values()})
        templates = {
            'config.json': {'type': 'act', 'n_obs_steps': 1, 'chunk_size': 1, 'n_action_steps': 1,
                            'input_features': features, 'output_features': {'action': {'type': 'ACTION', 'shape': [10]}},
                            'normalization_mapping': {'VISUAL': 'MEAN_STD', 'STATE': 'MEAN_STD', 'ACTION': 'MEAN_STD'}},
            'action_codec.json': {'mode': 'delta_from_measured_width', 'requires_custom_action_decode': True,
                                  'external_action': 'local-relative-h1-columns-future_absolute_width',
                                  'codec_script_sha256': sha(ROOT / 'scripts/gripper_codec.py')},
        }
        for name, registries, state in (
            ('policy_preprocessor', ['rename_observations_processor', 'to_batch_processor', 'device_processor', 'normalizer_processor'], FILES[5]),
            ('policy_postprocessor', ['unnormalizer_processor', 'device_processor'], FILES[6]),
        ):
            steps = [{'registry_name': registry, 'config': {}} for registry in registries]
            steps[3 if name == 'policy_preprocessor' else 0]['state_file'] = state
            templates[name + '.json'] = {'name': name, 'steps': steps}
        # Synthetic config/weight blobs: no dependency on Git-external checkpoints.
        for name in FILES:
            target = self.checkpoint / name
            if name.endswith('.json'): target.write_text(json.dumps(templates[name]))
            else: target.write_bytes(b'not_real_weights_for_integrity_tests')
        for name in (*CODE, 'sources.lock.json', 'assets/datasets/valid49-files.json', 'assets/datasets/valid49-split.json'):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, path)
        self.data = create(self.root, self.relative)
        self.manifest = self.root / 'manifest.json'
        self.save()

    def save(self):
        self.manifest.write_text(json.dumps(self.data))

    def rehash(self, name):
        path = self.checkpoint / name
        self.data['files'][name] = {'size_bytes': path.stat().st_size, 'sha256': sha(path)}
        self.save()

    def test_roundtrip_and_cli(self):
        result = verify(self.root, self.manifest)
        self.assertTrue(result['passed'])
        self.assertFalse(result['hardware_ready'])
        self.assertFalse(result['robot_commands_sent'])
        self.assertEqual(result['checked_checkpoint_files'], 7)
        command = [sys.executable, '-I', str(ROOT / 'scripts/policy_bundle.py'),
                   'verify', '--root', str(self.root), '--manifest', str(self.manifest)]
        self.assertEqual(subprocess.run(command, capture_output=True).returncode, 0)

    def test_each_missing_checkpoint_file_rejected(self):
        for name in FILES:
            path = self.checkpoint / name
            value = path.read_bytes()
            path.unlink()
            with self.assertRaisesRegex(ValueError, 'missing'): verify(self.root, self.manifest)
            path.write_bytes(value)

    def test_each_runtime_file_corruption_rejected(self):
        for name in CODE:
            path = self.root / name
            value = path.read_bytes()
            path.write_bytes(value + b'\n')
            with self.assertRaisesRegex(ValueError, 'checksum'): verify(self.root, self.manifest)
            path.write_bytes(value)

    def test_model_same_size_corruption_rejected(self):
        path = self.checkpoint / 'model.safetensors'
        value = path.read_bytes()
        path.write_bytes(b'X' + value[1:])
        with self.assertRaisesRegex(ValueError, 'checksum'): verify(self.root, self.manifest)

    def test_worker_rejects_mismatch_before_ready_or_gpu_imports(self):
        self.data['files']['model.safetensors']['sha256'] = '0' * 64
        self.save()
        command = [sys.executable, '-I', str(ROOT / 'scripts/probe_gpu_images.py'),
                   '--root', str(self.root), '--policy-bundle', str(self.manifest),
                   '--images', str(self.root), '--diagnostic-width', '.04']
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '')
        self.assertIn('Bundle file checksum mismatch: model.safetensors', result.stderr)

    def test_manifest_and_path_rejections(self):
        original = copy.deepcopy(self.data)
        cases = [('hardware_ready', True), ('schema_version', True), ('unknown_field', False),
                 ('checkpoint', '../outside'), ('checkpoint', '/tmp/weights'), ('checkpoint', 'models//candidate'),
                 ('checkpoint', 'models/./candidate')]
        for name, value in cases:
            self.data = copy.deepcopy(original)
            self.data[name] = value
            self.save()
            with self.assertRaises(ValueError): verify(self.root, self.manifest)
        self.data = copy.deepcopy(original)
        self.data['contract']['action_dim'] = 9
        self.save()
        with self.assertRaisesRegex(ValueError, 'contract'): verify(self.root, self.manifest)

    def test_symlink_even_with_correct_hash_rejected(self):
        path = self.checkpoint / 'model.safetensors'
        target = self.checkpoint / 'other_weights'
        path.rename(target)
        path.symlink_to(target)
        with self.assertRaisesRegex(ValueError, 'Symlink'): verify(self.root, self.manifest)

    def test_json_duplicate_and_nan_rejected(self):
        self.manifest.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaisesRegex(ValueError, 'Duplicate'): verify(self.root, self.manifest)
        self.manifest.write_text('{"schema_version":NaN}')
        with self.assertRaisesRegex(ValueError, 'Nonfinite'): verify(self.root, self.manifest)

    def test_codec_requires_measured_width_even_if_rehashed(self):
        path = self.checkpoint / 'action_codec.json'
        codec = json.loads(path.read_text())
        codec['mode'] = 'absolute_width'
        path.write_text(json.dumps(codec))
        self.rehash(path.name)
        with self.assertRaisesRegex(ValueError, 'codec'): verify(self.root, self.manifest)

    def test_processor_path_and_order_even_if_rehashed(self):
        path = self.checkpoint / 'policy_preprocessor.json'
        processor = json.loads(path.read_text())
        original = copy.deepcopy(processor)
        processor['steps'][-1]['state_file'] = '../../outside.safetensors'
        path.write_text(json.dumps(processor))
        self.rehash(path.name)
        with self.assertRaisesRegex(ValueError, 'state reference'): verify(self.root, self.manifest)
        original['steps'].reverse()
        path.write_text(json.dumps(original))
        self.rehash(path.name)
        with self.assertRaisesRegex(ValueError, 'order'): verify(self.root, self.manifest)

    def test_chunk_and_feature_even_if_rehashed(self):
        path = self.checkpoint / 'config.json'
        config = json.loads(path.read_text())
        for name, value in [('chunk_size', 2), ('chunk_size', True)]:
            config[name] = value
            path.write_text(json.dumps(config))
            self.rehash(path.name)
            with self.assertRaisesRegex(ValueError, 'configuration'): verify(self.root, self.manifest)
        config['chunk_size'] = 1
        config['input_features']['observation.images.pikaDepthCamera']['shape'] = [1, 96, 128]
        path.write_text(json.dumps(config))
        self.rehash(path.name)
        with self.assertRaisesRegex(ValueError, 'feature'): verify(self.root, self.manifest)

    def test_source_pin_mismatch(self):
        path = self.root / 'sources.lock.json'
        lock = json.loads(path.read_text())
        lock['lerobot']['commit'] = '0' * 40
        path.write_text(json.dumps(lock))
        with self.assertRaisesRegex(ValueError, 'commit'): verify(self.root, self.manifest)

    def test_export_whitelist_reproducibility_no_overwrite(self):
        from export_policy_bundle import export, EXTRAS
        for name in EXTRAS:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, path)
        # Deliberately placed private/unrelated data must never be collected.
        (self.root / 'private-key').write_text('fake_secret_for_test')
        (self.checkpoint / 'unrelated-log').write_text('not_part_of_bundle')
        output = self.root / 'one.tar.gz'
        result = export(self.root, self.manifest, output)
        self.assertTrue(result['passed'])
        second = self.root / 'two.tar.gz'
        export(self.root, self.manifest, second)
        self.assertEqual(sha(output), sha(second))
        with self.assertRaises(FileExistsError): export(self.root, self.manifest, output)
        with tarfile.open(output) as tar:
            names = tar.getnames()
            expected = [self.relative + '/' + name for name in FILES]
            expected += list(CODE) + list(EXTRAS) + ['config/policy-bundle.json', 'README.md', 'bundle-export.json']
            self.assertEqual(set(names), set(expected))
            self.assertTrue(all(member.isfile() for member in tar.getmembers()))
            metadata = json.load(tar.extractfile('bundle-export.json'))
            self.assertFalse(metadata['contains_raw_dataset'])
            self.assertFalse(metadata['contains_ssh_credentials'])
            for name, record in metadata['files'].items():
                import hashlib
                blob = tar.extractfile(name).read()
                self.assertEqual(len(blob), record['size_bytes'])
                self.assertEqual(hashlib.sha256(blob).hexdigest(), record['sha256'])

    def test_export_refuses_corrupt_input(self):
        from export_policy_bundle import export
        output = self.root / 'corrupt.tar.gz'
        (self.checkpoint / 'model.safetensors').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'checksum'): export(self.root, self.manifest, output)
        self.assertFalse(output.exists())


if __name__ == '__main__': unittest.main()
