"""Audit full RGB baseline statistics, split, cache hashes and validation diagnostics."""
import hashlib
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from teacher_trajectory import decode_rotation
from gripper_codec import encode_action


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):
            value.update(chunk)
    return value.hexdigest()


def decode_prediction(values):
    """Network rotation6D is unconstrained; project columns with Gram-Schmidt."""
    import numpy as np
    values = np.asarray(values,dtype=float)
    if values.shape!=(6,) or not np.isfinite(values).all():
        raise ValueError('Invalid predicted rotation6D')
    a,b = values[:3],values[3:]
    if np.linalg.norm(a)<1e-8:
        raise ValueError('Degenerate first rotation column')
    a = a/np.linalg.norm(a)
    b = b-a*(a@b)
    if np.linalg.norm(b)<1e-8:
        raise ValueError('Degenerate second rotation column')
    b = b/np.linalg.norm(b)
    return np.column_stack((a,b,np.cross(a,b)))


def main():
    import numpy as np
    import torch
    from safetensors.torch import load_file
    torch.set_num_threads(4)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--residual',action='store_true')
    args=parser.parse_args()
    category='full-rgb-residual' if args.residual else 'full-rgb-baseline'
    report = json.loads((ROOT/'artifacts'/f'{category}-latest.json').read_text())
    run, cache_dir = Path(report['run']),Path(report['input_cache'])
    manifest = json.loads((cache_dir/'manifest.json').read_text())
    split = json.loads((ROOT/'assets/valid49-split.json').read_text())
    assert digest(cache_dir/'samples.safetensors') == report['samples_sha256'] == manifest['samples_sha256']
    assert digest(run/'training_script.py') == report['script_sha256']
    assert digest(run/'requirements-gpu.lock') == report['requirements_sha256']
    tensors = load_file(cache_dir/'samples.safetensors')
    assert not any('depths.' in k or k.startswith('test/') for k in tensors)
    for name in ['train','validation']:
        expected = [[s['episode'],i] for s in split['selection'] if s['split']==name for i in s['selected']]
        assert manifest['mapping'][name] == expected
        assert all(ep not in split['splits']['test'] for ep,_ in expected)
    files = list((run/'pretrained_model').glob('policy_preprocessor*normalizer*.safetensors'))
    assert len(files)==1
    stats = load_file(files[0])
    codec=report.get('action_codec','absolute_width')
    if args.residual:
        assert codec=='delta_from_measured_width'
        assert digest(run/'gripper_codec.py')==report['codec_script_sha256']
        assert digest(ROOT/'scripts/gripper_codec.py')==report['codec_script_sha256']
    for key in ['observation.state','action','observation.images.pikaDepthCamera','observation.images.pikaFisheyeCamera']:
        value = tensors['train/'+key]
        if key=='action':
            value=encode_action(value,tensors['train/observation.state'],codec)
        axes = (0,2,3) if value.ndim==4 else (0,)
        mean, std = value.mean(dim=axes),value.std(dim=axes,unbiased=False)
        if value.ndim==4:
            mean,std = mean[:,None,None],std[:,None,None]
        torch.testing.assert_close(stats[key+'.mean'],mean,rtol=0,atol=0)
        torch.testing.assert_close(stats[key+'.std'],std.clamp_min(1e-6),rtol=0,atol=0)
    pred = load_file(run/'predictions.safetensors')['validation']
    target = tensors['validation/action'][report['evaluation_indices']['validation']]
    assert len(pred)==1022 and torch.isfinite(pred).all()
    moving = target[:,:3].norm(dim=1) > .001
    errors, baseline, invalid = [],[],0
    for p,t in zip(pred.numpy(),target.numpy()):
        truth = decode_rotation(t[3:9],'columns')
        try:
            rotation = decode_prediction(p[3:9])
        except ValueError:
            invalid += 1
            continue
        errors.append(float(np.arccos(np.clip((np.trace(rotation.T@truth)-1)/2,-1,1))))
        baseline.append(float(np.arccos(np.clip((np.trace(truth)-1)/2,-1,1))))
    result = {'status':'passed','run':str(run),'train_only_statistics_exact':True,
        'action_codec':codec,
        'cache_and_source_hashes_match':True,'test_frames_used':False,
        'training_unique_samples_seen':report['unique_training_samples_seen'],
        'validation_frames':len(pred),'moving_threshold_m':.001,'moving_frames':int(moving.sum()),
        'validation_metrics':report['metrics']['validation'],
        'audit_script_sha256':digest(Path(__file__)),
        'moving_translation_error_m':float((pred[moving,:3]-target[moving,:3]).norm(dim=1).mean()),
        'moving_no_motion_error_m':float(target[moving,:3].norm(dim=1).mean()),
        'rotation_error_mean_rad':float(np.mean(errors)) if errors else None,
        'no_motion_rotation_error_mean_rad':float(np.mean(baseline)) if baseline else None,
        'invalid_rotation_predictions':invalid,
        'rotation_prediction_decode':'columns Gram-Schmidt; reject degenerate vectors; no action clipping',
        'predicted_gripper_range_m':[float(pred[:,9].min()),float(pred[:,9].max())],
        'hardware_ready':False,'task_success_validated':False}
    (run/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    (run/'audit_script.py').write_bytes(Path(__file__).read_bytes())
    output='full-rgb-residual-audit-latest.json' if args.residual else 'full-rgb-audit-latest.json'
    (ROOT/'artifacts'/output).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
