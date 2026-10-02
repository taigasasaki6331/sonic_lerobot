"""Offline CUDA ACT plumbing test on the hash-verified CPU smoke sample cache."""
import argparse
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from gripper_codec import encode_action,decode_action


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--steps', type=int, default=100)
    parser.add_argument('--resume',type=Path,help='Own trusted resume-step checkpoint; total steps set by --steps')
    parser.add_argument('--checkpoint-every',type=int,default=50)
    parser.add_argument('--full-data',action='store_true',help='Use fixed valid49 train/validation cache; small ACT baseline')
    parser.add_argument('--gripper-residual',action='store_true',help='Experimental internal delta-width target; requires codec at inference')
    args = parser.parse_args()
    limit = 10000 if args.full_data else 1000
    if not 1 <= args.steps <= limit:
        parser.error(f'Only 1..{limit} steps for this mode; not a production policy')
    if args.checkpoint_every < 1:
        parser.error('checkpoint-every must be positive')
    if args.gripper_residual and not args.full_data:
        parser.error('Residual experiment requires --full-data')
    codec = 'delta_from_measured_width' if args.gripper_residual else 'absolute_width'
    if sys.version_info[:3] != (3, 12, 13):
        raise RuntimeError('Python 3.12.13 required')
    lock = ROOT/'requirements-gpu.lock'
    for line in lock.read_text().splitlines():
        if '==' in line and not line.startswith('#'):
            name, version = line.split('==')
            if metadata.version(name) != version:
                raise RuntimeError(f'Unpinned package: {name}')
    source = ROOT/'vendor/lerobot'
    commit = json.loads((ROOT/'sources.lock.json').read_text())['lerobot']['commit']
    if subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip() != commit:
        raise RuntimeError('Wrong LeRobot source')
    subprocess.run(['git', '-C', str(source), 'diff', '--exit-code', 'HEAD'], check=True)
    sys.path.insert(0, str(source/'src'))
    os.environ.update(HF_HUB_OFFLINE='1', HF_DATASETS_OFFLINE='1',
                      HF_HUB_DISABLE_TELEMETRY='1', CUBLAS_WORKSPACE_CONFIG=':4096:8')
    def audit(event, args):
        if event in {'socket.connect', 'socket.bind', 'socket.sendto', 'socket.getaddrinfo'}:
            raise RuntimeError('Network forbidden in GPU smoke test')
    sys.addaudithook(audit)
    import torch
    from safetensors.torch import load_file, save_file
    from lerobot.configs.types import PolicyFeature, FeatureType
    from lerobot.policies.act.configuration_act import ACTConfig
    from lerobot.policies.act.modeling_act import ACTPolicy
    from lerobot.policies.factory import make_pre_post_processors
    torch.set_num_threads(4)
    torch.manual_seed(42)
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.benchmark = False
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA required; no CPU fallback')
    inputs = ROOT/'assets/gpu-smoke-input'
    if args.full_data:
        inputs = Path(json.loads((ROOT/'artifacts/full-rgb-cache-latest.json').read_text())['cache'])
        if not inputs.resolve().is_relative_to(ROOT/'artifacts/full-rgb-cache'):
            raise RuntimeError('Cache must be inside full-rgb-cache')
    provenance = json.loads((inputs/'manifest.json').read_text())
    if sha(inputs/'samples.safetensors') != provenance['samples_sha256']:
        raise RuntimeError('Sample hash mismatch')
    tensors = load_file(inputs/'samples.safetensors')
    cameras = ['observation.images.pikaDepthCamera', 'observation.images.pikaFisheyeCamera']
    expected = {'observation.state', 'action', *cameras}
    if set(tensors) != {f'{split}/{key}' for split in ['train','validation'] for key in expected}:
        raise RuntimeError('Unexpected cache fields')
    counts = {'train':8693,'validation':1022} if args.full_data else {'train':64,'validation':32}
    if args.full_data:
        split_path = ROOT/'assets/valid49-split.json'
        frozen_split = json.loads(split_path.read_text())
        expected_mapping = {name:[[s['episode'],i] for s in frozen_split['selection']
            if s['split']==name for i in s['selected']] for name in counts}
        if (provenance['counts'] != counts or provenance['mapping'] != expected_mapping
                or provenance['split_sha256'] != sha(split_path)
                or provenance['requirements_sha256'] != sha(lock)):
            raise RuntimeError('Full-data cache provenance differs')
    for split, count in counts.items():
        for key in expected:
            value = tensors[f'{split}/{key}']
            shape = (count,3,96,128) if key in cameras else (count,10)
            if tuple(value.shape) != shape or not torch.isfinite(value).all():
                raise RuntimeError('Invalid cache tensor')
    features = {'observation.state':PolicyFeature(type=FeatureType.STATE,shape=(10,))}
    features.update({key:PolicyFeature(type=FeatureType.VISUAL,shape=(3,96,128)) for key in cameras})
    cfg = ACTConfig(input_features=features,
        output_features={'action':PolicyFeature(type=FeatureType.ACTION,shape=(10,))},
        device='cuda',chunk_size=1,n_action_steps=1,dim_model=128,n_heads=4,
        dim_feedforward=512,n_encoder_layers=1,n_decoder_layers=1,use_vae=False,
        dropout=0,pretrained_backbone_weights=None)
    stats = {}
    training_targets=encode_action(tensors['train/action'],tensors['train/observation.state'],codec)
    for key in expected:
        value = training_targets if key=='action' else tensors['train/'+key]
        axes = (0,2,3) if key in cameras else (0,)
        mean, std = value.mean(dim=axes), value.std(dim=axes,unbiased=False)
        if key in cameras:
            mean, std = mean[:,None,None], std[:,None,None]
        stats[key] = {'mean':mean,'std':std.clamp_min(1e-6)}
    policy = ACTPolicy(cfg).to('cuda')
    pre, post = make_pre_post_processors(cfg,dataset_stats=stats)
    evaluation_indices = {name:torch.arange(count) for name,count in counts.items()}
    if args.full_data:
        evaluation_indices['train'] = torch.linspace(0,counts['train']-1,256).long()
    def batch(split, indices, training=False):
        values = {key:tensors[split+'/'+key][indices] for key in features}
        if training:
            if split!='train':
                raise RuntimeError('Training on non-train split forbidden')
            values['action'] = training_targets[indices,None,:]
            values['action_is_pad'] = torch.zeros((len(indices),1),dtype=torch.bool)
        return pre(values)
    def evaluate():
        policy.eval()
        predictions, durations = {}, []
        with torch.inference_mode():
            for split in ['train','validation']:
                values = []
                for i in evaluation_indices[split].tolist():
                    policy.reset()
                    torch.cuda.synchronize()
                    start = time.perf_counter()
                    pred = post(policy.select_action(batch(split,[i])))[0].cpu()
                    pred = decode_action(pred,tensors[split+'/observation.state'][i],codec)
                    torch.cuda.synchronize()
                    durations.append((time.perf_counter()-start)*1000)
                    values.append(pred)
                predictions[split] = torch.stack(values).contiguous()
        return predictions, float(torch.tensor(durations).quantile(.95))
    category = 'full-rgb-baseline' if args.full_data else 'gpu-smoke'
    if args.gripper_residual:
        category='full-rgb-residual'
    base = ROOT/'artifacts'/category
    base.mkdir(parents=True,exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix='run-',dir=base))
    optimizer = torch.optim.AdamW(policy.parameters(),lr=1e-4,weight_decay=1e-4)
    losses = []
    completed = 0
    identity = {'samples':provenance['samples_sha256'],'lock':sha(lock),
                'script':sha(Path(__file__)),'lerobot':commit,'input_manifest':sha(inputs/'manifest.json'),
                'codec':codec,'codec_script':sha(ROOT/'scripts/gripper_codec.py')}
    batch_size = 16 if args.full_data else 4
    permutation = torch.randperm(counts['train']) if args.full_data else torch.empty(0,dtype=torch.long)
    cursor = 0
    seen = torch.zeros(counts['train'],dtype=torch.bool)
    examples_drawn = 0
    resume_sha = None
    if args.resume:
        resume_sha = sha(args.resume)
        saved = torch.load(args.resume,map_location='cpu',weights_only=True)
        if saved['identity'] != identity or saved['gpu'] != torch.cuda.get_device_name(0):
            raise RuntimeError('Resume source/environment identity differs')
        completed = saved['step']
        if not 0 < completed < args.steps or len(saved['losses']) != completed:
            raise RuntimeError('Resume step must be below requested total steps')
        policy.load_state_dict(saved['model'],strict=True)
        optimizer.load_state_dict(saved['optimizer'])
        losses = saved['losses']
        permutation, cursor = saved['permutation'],saved['cursor']
        seen, examples_drawn = saved['seen'],saved['examples_drawn']
        torch.set_rng_state(saved['cpu_rng'])
        torch.cuda.set_rng_state_all(saved['cuda_rng'])
    def save_resume(step):
        checkpoint = {'identity':identity,'gpu':torch.cuda.get_device_name(0),
            'step':step,'losses':losses,'model':policy.state_dict(),
            'optimizer':optimizer.state_dict(),'cpu_rng':torch.get_rng_state(),
            'cuda_rng':torch.cuda.get_rng_state_all(),'permutation':permutation,'cursor':cursor,
            'seen':seen,'examples_drawn':examples_drawn}
        target = run/f'resume-step-{step:06d}.pt'
        temporary = target.with_suffix('.pt.tmp')
        torch.save(checkpoint,temporary)
        os.replace(temporary,target)
    start = time.perf_counter()
    for step in range(completed,args.steps):
        policy.train()
        if args.full_data:
            if cursor == counts['train']:
                permutation, cursor = torch.randperm(counts['train']),0
            indices = permutation[cursor:cursor+batch_size]
            cursor += len(indices)
        else:
            indices = torch.randint(counts['train'],(batch_size,))
        seen[indices] = True
        examples_drawn += len(indices)
        loss, _ = policy(batch('train',indices,training=True))
        if not torch.isfinite(loss):
            raise RuntimeError('Nonfinite loss')
        optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(policy.parameters(),1.,error_if_nonfinite=True)
        optimizer.step()
        losses.append(float(loss.detach()))
        if (step+1)%args.checkpoint_every == 0 or step+1 == args.steps:
            save_resume(step+1)
        if (step+1)%10 == 0:
            print(f'GPU step {step+1}/{args.steps}: {losses[-1]:.6f}',flush=True)
    torch.cuda.synchronize()
    seconds = time.perf_counter()-start
    checkpoint = run/'pretrained_model'
    policy.save_pretrained(checkpoint)
    pre.save_pretrained(checkpoint)
    post.save_pretrained(checkpoint)
    codec_metadata={'mode':codec,'external_action':'local-relative-h1-columns-future_absolute_width',
        'requires_custom_action_decode':args.gripper_residual,
        'decode_order':'ACT -> postprocessor inverse normalization -> codec(measured state) -> external action',
        'codec_script_sha256':identity['codec_script'],
        'warning':'Residual ACT/processor output alone is NOT a future absolute gripper width.'}
    (checkpoint/'action_codec.json').write_text(json.dumps(codec_metadata,indent=2)+'\n')
    predictions, p95 = evaluate()
    save_file(predictions,run/'predictions.safetensors')
    del policy, optimizer
    torch.cuda.empty_cache()
    policy = ACTPolicy.from_pretrained(str(checkpoint),local_files_only=True,strict=True).to('cuda')
    if json.loads((checkpoint/'action_codec.json').read_text())!=codec_metadata:
        raise RuntimeError('Reload codec metadata differs')
    pre, post = make_pre_post_processors(policy.config,pretrained_path=str(checkpoint))
    reloaded, _ = evaluate()
    if not all(torch.equal(predictions[key],reloaded[key]) for key in predictions):
        raise RuntimeError('Strict reload predictions differ')
    metrics = {}
    for split, pred in predictions.items():
        target = tensors[split+'/action'][evaluation_indices[split]]
        metrics[split] = {
            'evaluated_samples':len(pred),
            'translation_l2_mean_m':float((pred[:,:3]-target[:,:3]).norm(dim=1).mean()),
            'no_motion_translation_l2_mean_m':float(target[:,:3].norm(dim=1).mean()),
            'gripper_mae_m':float((pred[:,9]-target[:,9]).abs().mean()),
            'hold_gripper_mae_m':float((tensors[split+'/observation.state'][evaluation_indices[split],9]-target[:,9]).abs().mean()),
            'negative_gripper_predictions':int((pred[:,9]<0).sum())}
    report = dict(status='passed',scope='cached_RGB_ACT_CUDA_training_and_strict_reload',
        hardware_ready=False,task_success_validated=False,steps=args.steps,seed=42,
        full_data=args.full_data,training_pool=counts['train'],batch_size=batch_size,
        action_codec=codec,codec_script_sha256=identity['codec_script'],
        unique_training_samples_seen=int(seen.sum()),examples_drawn=examples_drawn,
        input_cache=str(inputs),test_evaluated=False,
        resumed_from_step=completed,resume_sha256=resume_sha,
        gpu=torch.cuda.get_device_name(0),torch=torch.__version__,cuda=torch.version.cuda,
        lerobot_commit=commit,samples_sha256=provenance['samples_sha256'],
        requirements_sha256=sha(lock),script_sha256=sha(Path(__file__)),
        input_manifest_sha256=sha(inputs/'manifest.json'),losses=losses,
        training_seconds=seconds,training_timing_includes_resume_checkpoint_io=True,
        cached_inference_p95_ms=p95,
        timing_scope='synchronized CPU cache to GPU ACT to CPU output; excludes decoding and resize',
        reload_exact=True,reload_evaluated_samples=sum(len(i) for i in evaluation_indices.values()),
        evaluation_indices={k:v.tolist() for k,v in evaluation_indices.items()},metrics=metrics,run=str(run))
    (run/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    (run/'training_script.py').write_bytes(Path(__file__).read_bytes())
    (run/'gripper_codec.py').write_bytes((ROOT/'scripts/gripper_codec.py').read_bytes())
    (run/'requirements-gpu.lock').write_bytes(lock.read_bytes())
    (run/'input-manifest.json').write_bytes((inputs/'manifest.json').read_bytes())
    (ROOT/'artifacts'/f'{category}-latest.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in {'losses','evaluation_indices'}},indent=2))


if __name__ == '__main__':
    main()
