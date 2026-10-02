"""Validate the selected RGB smoke run's data split and preprocessing contract."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from train_rgb_smoke import runtime, rgb_input, CAMERAS
runtime()
import torch
from safetensors.torch import load_file

run = Path(json.loads((ROOT/'artifacts/rgb-smoke-latest.json').read_text())['run'])
manifest = json.loads((run/'manifest.json').read_text())
assert set(manifest['train_episodes']).isdisjoint(manifest['validation_episodes'])
assert hashlib.sha256((run/'samples.safetensors').read_bytes()).hexdigest() == manifest['samples_sha256']
assert hashlib.sha256((run/'training_script.py').read_bytes()).hexdigest() == manifest['script_sha256']
cache = load_file(run/'samples.safetensors')
assert cache['train/action'].shape == (64,10)
assert cache['validation/action'].shape == (32,10)
for selection in manifest['selection']:
    assert len(selection['selected']) == 16
    assert set(selection['selected']).isdisjoint(selection['excluded_gripper_mismatch'])
assert not any('depths.' in key for key in cache)
stats_path, = (run/'pretrained_model').glob('policy_preprocessor*normalizer*.safetensors')
stats = load_file(stats_path)
for key in [*CAMERAS,'observation.state','action']:
    x = cache['train/'+key]
    axes = (0,2,3) if key in CAMERAS else (0,)
    mean, std = x.mean(dim=axes), x.std(dim=axes,unbiased=False)
    if key in CAMERAS:
        mean, std = mean[:,None,None], std[:,None,None]
    torch.testing.assert_close(stats[key+'.mean'],mean)
    torch.testing.assert_close(stats[key+'.std'],std.clamp_min(1e-6))
raw = {'observation.state':torch.zeros(10), **{key:torch.full((3,480,640),128,dtype=torch.uint8) for key in CAMERAS}}
converted = rgb_input(raw)
for key in CAMERAS:
    assert converted[key].shape == (3,96,128)
    torch.testing.assert_close(converted[key], torch.full((3,96,128),128/255))
assert len(manifest['training_losses']) == manifest['steps']
print('PASS: split isolation, exclusions, sample/source hashes, train-only statistics, shared RGB preprocessing, recorded step count')
