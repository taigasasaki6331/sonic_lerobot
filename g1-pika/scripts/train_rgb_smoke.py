"""Small, reproducible LeRobot ACT training/inference test; no hardware."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
DATASET = Path('/home/developer/workspaces/pika_ws2/datasets/data_2608261323_valid49_g1_zero_relative_h1_final_v3')
CAMERAS = ['observation.images.pikaDepthCamera', 'observation.images.pikaFisheyeCamera']


def runtime():
    if sys.version_info[:3] != (3, 12, 13):
        raise RuntimeError('Use .venv-policy Python 3.12.13')
    for line in (ROOT/'requirements-policy.lock').read_text().splitlines():
        if '==' in line and not line.startswith('#'):
            name, version = line.split('==')
            if importlib.metadata.version(name) != version:
                raise RuntimeError(f'Unpinned dependency: {name}')
    for key, value in {'HF_HUB_OFFLINE':'1', 'HF_DATASETS_OFFLINE':'1',
                       'HF_HUB_DISABLE_TELEMETRY':'1', 'HF_HOME':str(ROOT/'.cache/policy/hf'),
                       'TORCH_HOME':str(ROOT/'.cache/policy/torch')}.items():
        os.environ[key] = value
    def audit(event, args):
        if event in {'socket.connect', 'socket.bind', 'socket.sendto', 'socket.getaddrinfo'}:
            raise RuntimeError('Network forbidden in RGB smoke test')
    sys.addaudithook(audit)
    upstream = ROOT/'vendor/lerobot'
    commit = json.loads((ROOT/'sources.lock.json').read_text())['lerobot']['commit']
    if subprocess.check_output(['git','-C',str(upstream),'rev-parse','HEAD'], text=True).strip() != commit:
        raise RuntimeError('Wrong LeRobot commit')
    subprocess.run(['git','-C',str(upstream),'diff','--exit-code','HEAD'], check=True)
    sys.path.insert(0, str(upstream/'src'))
    return commit


def rgb_input(item):
    """The single shared preprocessing path for training and inference."""
    import torch
    import torch.nn.functional as F
    output = {'observation.state': item['observation.state'].float()}
    for key in CAMERAS:
        value = item[key]
        if value.dtype == torch.uint8:
            value = value.float()/255
        if value.shape != (3, 480, 640) or not torch.isfinite(value).all() or value.min()<0 or value.max()>1:
            raise ValueError(f'Unexpected RGB input: {key}')
        output[key] = F.interpolate(value[None], size=(96, 128), mode='bilinear',
                                    align_corners=False, antialias=True)[0]
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--steps', type=int, default=100)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument('--evaluate', type=Path, help='Reload and evaluate an existing smoke run')
    selection.add_argument('--evaluate-latest', action='store_true')
    args = parser.parse_args()
    if args.evaluate_latest:
        args.evaluate = Path(json.loads((ROOT/'artifacts/rgb-smoke-latest.json').read_text())['run'])
        if not args.evaluate.resolve().is_relative_to(ROOT/'artifacts/rgb-smoke'):
            parser.error('Latest run must be inside artifacts/rgb-smoke')
    if not 1 <= args.steps <= 1000:
        parser.error('--steps must be 1..1000; this is not a production trainer')
    commit = runtime()
    import numpy as np
    import torch
    import pyarrow.parquet as pq
    from safetensors.torch import save_file, load_file
    from lerobot.datasets.lerobot_dataset import LeRobotDataset
    from lerobot.configs.types import PolicyFeature, FeatureType
    from lerobot.policies.act.configuration_act import ACTConfig
    from lerobot.policies.act.modeling_act import ACTPolicy
    from lerobot.policies.factory import make_pre_post_processors
    torch.set_num_threads(4)
    torch.manual_seed(42)
    torch.use_deterministic_algorithms(True)
    if args.evaluate:
        run = args.evaluate.resolve()
        manifest = json.loads((run/'manifest.json').read_text())
        if hashlib.sha256((run/'samples.safetensors').read_bytes()).hexdigest() != manifest['samples_sha256']:
            raise RuntimeError('Sample cache checksum mismatch')
        tensors = load_file(run/'samples.safetensors')
        cfg = ACTConfig.from_pretrained(str(run/'pretrained_model'), local_files_only=True)
        policy = ACTPolicy.from_pretrained(str(run/'pretrained_model'), config=cfg, local_files_only=True, strict=True)
        pre, post = make_pre_post_processors(cfg, pretrained_path=str(run/'pretrained_model'))
    else:
        base = ROOT/'artifacts/rgb-smoke'
        base.mkdir(parents=True, exist_ok=True)
        run = Path(tempfile.mkdtemp(prefix='run-', dir=base))
        (run/'training_script.py').write_text(Path(__file__).read_text())
        manifest = {'lerobot_commit':commit, 'seed':42, 'source_dataset':str(DATASET),
            'train_episodes':[0,1,2,3], 'validation_episodes':[4,5], 'samples_per_episode':16,
            'gripper_handling':'exclude rows with abs(action.width - next_state.width) > 1e-6; do not repair labels',
            'resize':{'height':96,'width':128,'mode':'bilinear','antialias':True},
            'depth_used':False, 'pretrained_backbone':False, 'use_vae':False,
            'purpose':'training_pipeline_smoke_not_task_policy', 'selection':[],
            'requirements_sha256':hashlib.sha256((ROOT/'requirements-policy.lock').read_bytes()).hexdigest(),
            'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        collected = {'train':[], 'validation':[]}
        rng = np.random.default_rng(42)
        manifest['source_parquet_files'] = []
        for path in sorted((DATASET/'data').glob('chunk-*/*.parquet')):
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                for block in iter(lambda:stream.read(1024*1024), b''):
                    digest.update(block)
            manifest['source_parquet_files'].append({'path':str(path),'sha256':digest.hexdigest()})
        for episode in range(6):
            rows = pq.read_table(DATASET/'data', filters=[('episode_index','=',episode)],
                columns=['frame_index','observation.state','action']).to_pylist()
            rows.sort(key=lambda row:row['frame_index'])
            assert [r['frame_index'] for r in rows] == list(range(len(rows)))
            eligible = [i for i,r in enumerate(rows) if abs(r['action'][9]-rows[min(i+1,len(rows)-1)]['observation.state'][9]) <= 1e-6]
            if len(eligible) < 16:
                raise ValueError(f'Episode {episode}: fewer than 16 eligible samples; refusing incomplete split')
            indices = sorted(rng.choice(eligible, size=min(16,len(eligible)), replace=False).tolist())
            split = 'train' if episode < 4 else 'validation'
            manifest['selection'].append({'episode':episode,'split':split,'selected':indices,
                'excluded_gripper_mismatch':[i for i in range(len(rows)) if i not in eligible]})
            ds = LeRobotDataset('data', root=DATASET, episodes=[episode], return_uint8=True, video_backend='pyav')
            for i in indices:
                item = ds[i]
                assert int(item['frame_index']) == i
                sample = rgb_input(item)
                sample['action'] = item['action'].float()
                if not all(torch.isfinite(value).all() for value in sample.values()):
                    raise ValueError('Nonfinite training sample')
                collected[split].append(sample)
            print(f'Cached episode {episode}: {len(indices)} selected, {len(rows)-len(eligible)} excluded', flush=True)
        tensors = {f'{split}/{key}':torch.stack([s[key] for s in samples]).contiguous()
                   for split,samples in collected.items() for key in samples[0]}
        save_file(tensors, run/'samples.safetensors')
        manifest['samples_sha256'] = hashlib.sha256((run/'samples.safetensors').read_bytes()).hexdigest()
        features = {'observation.state':PolicyFeature(type=FeatureType.STATE, shape=(10,))}
        features.update({key:PolicyFeature(type=FeatureType.VISUAL,shape=(3,96,128)) for key in CAMERAS})
        cfg = ACTConfig(input_features=features, output_features={'action':PolicyFeature(type=FeatureType.ACTION,shape=(10,))},
            device='cpu',chunk_size=1,n_action_steps=1,dim_model=128,n_heads=4,dim_feedforward=512,
            n_encoder_layers=1,n_decoder_layers=1,use_vae=False,dropout=0,pretrained_backbone_weights=None)
        stats = {}
        for key in [*features,'action']:
            value = tensors['train/'+key]
            axes = (0,2,3) if key in CAMERAS else (0,)
            mean, std = value.mean(dim=axes), value.std(dim=axes,unbiased=False)
            if key in CAMERAS:
                mean, std = mean[:,None,None], std[:,None,None]
            stats[key] = {'mean':mean, 'std':std.clamp_min(1e-6)}
        manifest['normalization'] = 'mean/std from 64 selected TRAIN samples only; std floor 1e-6'
        pre, post = make_pre_post_processors(cfg, dataset_stats=stats)
        policy = ACTPolicy(cfg)
    def batch(split, indices, training=False):
        values = {key:tensors[split+'/'+key][indices] for key in cfg.input_features}
        if training:
            values['action'] = tensors[split+'/action'][indices,None,:]
            values['action_is_pad'] = torch.zeros((len(indices),1),dtype=torch.bool)
        return pre(values)
    def evaluate(split):
        policy.eval()
        predictions = []
        milliseconds = []
        with torch.inference_mode():
            for i in range(len(tensors[split+'/action'])):
                policy.reset()
                started = time.perf_counter()
                predictions.append(post(policy.select_action(batch(split,[i])))[0])
                milliseconds.append((time.perf_counter()-started)*1000)
        pred = torch.stack(predictions)
        target = tensors[split+'/action']
        baseline = torch.zeros_like(target); baseline[:,[3,7]]=1
        baseline[:,9]=tensors[split+'/observation.state'][:,9]
        return {'samples':len(pred),'translation_l2_mean_m':float((pred[:,:3]-target[:,:3]).norm(dim=1).mean()),
            'no_motion_translation_l2_mean_m':float(target[:,:3].norm(dim=1).mean()),
            'gripper_mae_m':float((pred[:,9]-target[:,9]).abs().mean()),
            'no_motion_gripper_mae_m':float((baseline[:,9]-target[:,9]).abs().mean()),
            'mae_per_dimension':(pred-target).abs().mean(dim=0).tolist(),
            'cached_inference_pipeline_p95_ms':float(np.percentile(milliseconds,95)),
            'timing_scope':'cached resized RGB -> processors -> ACT -> inverse normalization; excludes decoding/resize',
            'gripper_range_m':[float(pred[:,9].min()),float(pred[:,9].max())],
            'negative_gripper_predictions':int((pred[:,9]<0).sum())}, pred
    if not args.evaluate:
        initial, _ = evaluate('train')
        optimizer = torch.optim.AdamW(policy.parameters(), lr=1e-4, weight_decay=1e-4)
        losses = []
        for step in range(args.steps):
            policy.train()
            indices = torch.randint(len(tensors['train/action']), (4,))
            loss, _ = policy(batch('train',indices,training=True))
            if not torch.isfinite(loss):
                raise RuntimeError('Nonfinite training loss')
            optimizer.zero_grad(); loss.backward()
            norm = torch.nn.utils.clip_grad_norm_(policy.parameters(),1.0,error_if_nonfinite=True)
            optimizer.step()
            losses.append(float(loss.detach()))
            if (step+1)%10 == 0:
                print(f'Train {step+1}/{args.steps}: loss={losses[-1]:.5f}',flush=True)
        checkpoint = run/'pretrained_model'
        policy.save_pretrained(checkpoint)
        pre.save_pretrained(checkpoint)
        post.save_pretrained(checkpoint)
        manifest.update({'steps':args.steps,'batch_size':4,'optimizer':'AdamW lr=1e-4 weight_decay=1e-4 grad_clip=1',
                         'initial_train_metrics':initial,'training_losses':losses})
        (run/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    train_metrics, train_pred = evaluate('train')
    validation_metrics, validation_pred = evaluate('validation')
    report = {'status':'pipeline_smoke_completed','task_success_validated':False,'hardware_ready':False,
        'run':str(run),'train':train_metrics,'validation':validation_metrics,
        'train_validation_episodes_disjoint':True,'depth_used':False,'network_forbidden':True}
    output_name = 'reload-evaluation.json' if args.evaluate else 'evaluation.json'
    (run/output_name).write_text(json.dumps(report,indent=2)+'\n')
    pred_path = run/('reload-predictions.safetensors' if args.evaluate else 'predictions.safetensors')
    save_file({'train':train_pred.contiguous(),'validation':validation_pred.contiguous()},pred_path)
    if args.evaluate:
        original = load_file(run/'predictions.safetensors')
        if not torch.equal(original['train'],train_pred) or not torch.equal(original['validation'],validation_pred):
            raise RuntimeError('Reloaded model/processors do not reproduce predictions exactly')
        print('Reloaded checkpoint reproduces all predictions exactly')
    else:
        (ROOT/'artifacts/rgb-smoke-latest.json').write_text(json.dumps({'run':str(run)},indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
