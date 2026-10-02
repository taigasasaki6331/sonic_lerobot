"""Stdlib-only integrity/IO checks for a diagnostic LeRobot ACT bundle.

Hashes detect accidental substitution, not signed provenance or task safety.
No inference, network, device access, dependency installation or model repair.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

FILES = (
    'config.json', 'model.safetensors', 'action_codec.json',
    'policy_preprocessor.json', 'policy_postprocessor.json',
    'policy_preprocessor_step_3_normalizer_processor.safetensors',
    'policy_postprocessor_step_0_unnormalizer_processor.safetensors',
)
CODE = ('scripts/train_rgb_smoke.py', 'scripts/gripper_codec.py', 'requirements-gpu.lock')
CAMERAS = {'realsense_rgb': 'observation.images.pikaDepthCamera',
           'fisheye': 'observation.images.pikaFisheyeCamera'}
CONTRACT = {
    'policy': 'act', 'n_obs_steps': 1, 'chunk_size': 1, 'n_action_steps': 1,
    'state_dim': 10, 'action_dim': 10, 'rotation_layout': 'columns',
    'translation': 'local_relative_h1_m', 'external_width': 'future_absolute_width_m',
    'codec': 'delta_from_measured_width', 'camera_roles': CAMERAS,
    'input_rgb_chw': [3, 480, 640], 'policy_rgb_chw': [3, 96, 128],
    'resize': {'mode': 'bilinear', 'align_corners': False, 'antialias': True},
    'depth_used': False,
    'decode_order': ['ACT', 'saved_postprocessor', 'codec_with_measured_width'],
}
FIELDS = {'schema_version', 'purpose', 'hardware_ready', 'checkpoint',
          'lerobot_commit', 'contract', 'files', 'runtime_files', 'training_provenance'}


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError('Duplicate JSON key: ' + key)
            result[key] = value
        return result
    def invalid(value): raise ValueError('Nonfinite JSON value: ' + value)
    return json.loads(Path(path).read_text(), object_pairs_hook=pairs, parse_constant=invalid)


def relative_path(value):
    if not isinstance(value, str) or not value or '\\' in value or any(ord(c) < 32 for c in value):
        raise ValueError('Expected canonical relative path')
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or str(path) != value or value == '.':
        raise ValueError('Expected canonical relative path: ' + value)
    return value


def contained(root, relative):
    relative_path(relative)
    path = root / relative
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Path escapes bundle root: ' + relative)
    # Do not share bundles whose integrity depends on external/symlinked files.
    for part in (path, *path.parents):
        if part == root: break
        if part.is_symlink(): raise ValueError('Symlink in bundle: ' + relative)
    return path


def validate_manifest(data):
    if not isinstance(data, dict) or set(data) != FIELDS:
        raise ValueError('Unknown policy bundle fields')
    if type(data['schema_version']) is not int or data['schema_version'] != 1:
        raise ValueError('Unknown policy bundle schema')
    if data['purpose'] != 'diagnostic_candidate_not_task_acceptance' or data['hardware_ready'] is not False:
        raise ValueError('Only a diagnostic candidate is supported')
    relative_path(data['checkpoint'])
    if not isinstance(data['lerobot_commit'], str) or not re.fullmatch('[0-9a-f]{40}', data['lerobot_commit']):
        raise ValueError('Invalid LeRobot commit')
    # Compare JSON representations as well to reject bool/int substitutions.
    if json.dumps(data['contract'], sort_keys=True) != json.dumps(CONTRACT, sort_keys=True):
        raise ValueError('Unsupported policy IO contract')
    for field, expected in (('files', FILES), ('runtime_files', CODE)):
        entries = data[field]
        if not isinstance(entries, dict) or set(entries) != set(expected):
            raise ValueError('Missing/unknown bundle file: ' + field)
        for entry in entries.values():
            if (not isinstance(entry, dict) or set(entry) != {'size_bytes', 'sha256'}
                    or type(entry['size_bytes']) is not int or entry['size_bytes'] <= 0
                    or not isinstance(entry['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', entry['sha256'])):
                raise ValueError('Invalid bundle file descriptor')
    provenance = data['training_provenance']
    if not isinstance(provenance, dict) or set(provenance) != {'dataset_manifest_sha256', 'split_sha256', 'test_set_used'}:
        raise ValueError('Invalid training provenance')
    if provenance['test_set_used'] is not False:
        raise ValueError('Test-set use must remain explicitly false for this candidate')
    for name in ('dataset_manifest_sha256', 'split_sha256'):
        if not isinstance(provenance[name], str) or not re.fullmatch('[0-9a-f]{64}', provenance[name]):
            raise ValueError('Invalid training provenance hash')
    return data


def check_checkpoint(checkpoint, data):
    cfg = read_json(checkpoint / 'config.json')
    for name in ('type', 'n_obs_steps', 'chunk_size', 'n_action_steps'):
        expected = CONTRACT['policy'] if name == 'type' else CONTRACT[name]
        if type(cfg.get(name)) is not type(expected) or cfg[name] != expected:
            raise ValueError('Incompatible ACT configuration: ' + name)
    features = {'observation.state': {'type': 'STATE', 'shape': [10]}}
    features.update({key: {'type': 'VISUAL', 'shape': [3, 96, 128]} for key in CAMERAS.values()})
    if cfg['input_features'] != features or cfg['output_features'] != {'action': {'type': 'ACTION', 'shape': [10]}}:
        raise ValueError('ACT feature mismatch')
    if cfg['normalization_mapping'] != {'VISUAL': 'MEAN_STD', 'STATE': 'MEAN_STD', 'ACTION': 'MEAN_STD'}:
        raise ValueError('Normalization mapping mismatch')
    codec = read_json(checkpoint / 'action_codec.json')
    if (codec.get('mode') != CONTRACT['codec'] or codec.get('requires_custom_action_decode') is not True
            or codec.get('external_action') != 'local-relative-h1-columns-future_absolute_width'
            or codec.get('codec_script_sha256') != data['runtime_files']['scripts/gripper_codec.py']['sha256']):
        raise ValueError('Action codec mismatch')
    for name, registries, state_file in (
        ('policy_preprocessor', ['rename_observations_processor', 'to_batch_processor', 'device_processor', 'normalizer_processor'], FILES[5]),
        ('policy_postprocessor', ['unnormalizer_processor', 'device_processor'], FILES[6]),
    ):
        processor = read_json(checkpoint / (name + '.json'))
        if processor.get('name') != name or [s.get('registry_name') for s in processor['steps']] != registries:
            raise ValueError('Processor order mismatch: ' + name)
        references = [s['state_file'] for s in processor['steps'] if 'state_file' in s]
        if references != [state_file]: raise ValueError('Processor state reference mismatch')
    return codec


def verify(root, manifest):
    root = Path(root).resolve()
    data = validate_manifest(read_json(manifest))
    checkpoint = contained(root, data['checkpoint'])
    if not checkpoint.is_dir(): raise ValueError('Checkpoint missing: ' + str(checkpoint))
    for base, entries in ((checkpoint, data['files']), (root, data['runtime_files'])):
        for name, descriptor in entries.items():
            path = contained(base, name)
            if not path.is_file(): raise ValueError('Bundle file missing: ' + str(path))
            if path.stat().st_size != descriptor['size_bytes'] or sha(path) != descriptor['sha256']:
                raise ValueError('Bundle file checksum mismatch: ' + name)
    if read_json(root / 'sources.lock.json')['lerobot']['commit'] != data['lerobot_commit']:
        raise ValueError('Bundle/source LeRobot commit mismatch')
    check_checkpoint(checkpoint, data)
    return {'passed': True, 'scope': 'policy_bundle_integrity_and_declared_IO_only',
            'hardware_ready': False, 'robot_commands_sent': False,
            'manifest_sha256': sha(manifest), 'model_sha256': data['files']['model.safetensors']['sha256'],
            'checkpoint_relative': data['checkpoint'], 'checked_checkpoint_files': len(FILES),
            'checked_runtime_files': len(CODE), 'lerobot_commit': data['lerobot_commit'],
            'codec': CONTRACT['codec']}


def create(root, checkpoint_relative):
    root = Path(root).resolve()
    checkpoint = contained(root, checkpoint_relative)
    def descriptors(base, names):
        return {name: {'size_bytes': contained(base, name).stat().st_size,
                       'sha256': sha(contained(base, name))} for name in names}
    data = {'schema_version': 1, 'purpose': 'diagnostic_candidate_not_task_acceptance',
            'hardware_ready': False, 'checkpoint': checkpoint_relative,
            'lerobot_commit': read_json(root / 'sources.lock.json')['lerobot']['commit'],
            'contract': CONTRACT, 'files': descriptors(checkpoint, FILES),
            'runtime_files': descriptors(root, CODE),
            'training_provenance': {'dataset_manifest_sha256': sha(root / 'assets/datasets/valid49-files.json'),
                                    'split_sha256': sha(root / 'assets/datasets/valid49-split.json'), 'test_set_used': False}}
    validate_manifest(data)
    check_checkpoint(checkpoint, data)
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('verify', 'describe'))
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--checkpoint', help='Root-relative candidate checkpoint; describe only')
    args = parser.parse_args()
    if args.operation == 'describe':
        if not args.checkpoint or args.manifest: parser.error('describe requires --checkpoint, not --manifest')
        result = create(args.root, args.checkpoint)
    else:
        if args.checkpoint: parser.error('--checkpoint is describe-only')
        result = verify(args.root, args.manifest or args.root / 'config/policy-bundle.json')
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == '__main__': main()
