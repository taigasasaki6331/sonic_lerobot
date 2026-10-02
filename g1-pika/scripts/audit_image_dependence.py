"""Validation-only paired-image / gripper-state shuffle diagnostics, not task evaluation."""
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    source = ROOT/'vendor/lerobot'
    commit = json.loads((ROOT/'sources.lock.json').read_text())['lerobot']['commit']
    if subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()!=commit:
        raise RuntimeError('Source differs')
    subprocess.run(['git','-C',str(source),'diff','--exit-code','HEAD'],check=True)
    for line in (ROOT/'requirements-gpu.lock').read_text().splitlines():
        if '==' in line and not line.startswith('#'):
            name,version=line.split('==')
            if metadata.version(name)!=version:
                raise RuntimeError('Dependencies differ')
    sys.path.insert(0,str(source/'src'))
    os.environ.update(HF_HUB_OFFLINE='1',HF_DATASETS_OFFLINE='1',CUBLAS_WORKSPACE_CONFIG=':4096:8')
    def audit(event,args):
        if event in {'socket.connect','socket.bind','socket.sendto','socket.getaddrinfo'}:
            raise RuntimeError('Network forbidden')
    sys.addaudithook(audit)
    import torch
    from safetensors.torch import load_file
    from lerobot.policies.act.modeling_act import ACTPolicy
    from lerobot.policies.factory import make_pre_post_processors
    torch.set_num_threads(4)
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.benchmark=False
    torch.backends.cuda.matmul.allow_tf32=False
    torch.backends.cudnn.allow_tf32=False
    comparison=json.loads((ROOT/'artifacts/learning-curve-latest.json').read_text())
    if comparison['status']!='completed':
        raise RuntimeError('Learning comparison not finished')
    results=[]
    tensors=None
    sample_hash=None
    for entry in comparison['results']:
        run=Path(entry['run'])
        report=json.loads((run/'report.json').read_text())
        if tensors is None:
            cache=Path(report['input_cache'])/'samples.safetensors'
            digest=hashlib.sha256()
            with cache.open('rb') as stream:
                for block in iter(lambda:stream.read(1024*1024),b''): digest.update(block)
            sample_hash=digest.hexdigest()
            # Load only validation tensors into the diagnostic's working dictionary.
            from safetensors import safe_open
            with safe_open(cache,framework='pt',device='cpu') as reader:
                tensors={key.split('/',1)[1]:reader.get_tensor(key) for key in reader.keys() if key.startswith('validation/')}
        if sample_hash!=report['samples_sha256'] or len(tensors['action'])!=1022:
            raise RuntimeError('Cache differs')
        policy=ACTPolicy.from_pretrained(str(run/'pretrained_model'),local_files_only=True,strict=True).to('cuda').eval()
        pre,post=make_pre_post_processors(policy.config,pretrained_path=str(run/'pretrained_model'))
        permutation=torch.randperm(1022,generator=torch.Generator().manual_seed(314159))
        condition_results={}
        native=None
        with torch.inference_mode():
            for condition in ['native','paired_images_shuffled','gripper_state_shuffled']:
                values=[]
                for i in range(1022):
                    obs={key:tensors[key][i:i+1].clone() for key in policy.config.input_features}
                    if condition=='paired_images_shuffled':
                        for key in obs:
                            if key.startswith('observation.images.'):
                                obs[key]=tensors[key][permutation[i]:permutation[i]+1]
                    elif condition=='gripper_state_shuffled':
                        obs['observation.state'][0,9]=tensors['observation.state'][permutation[i],9]
                    policy.reset()
                    values.append(post(policy.select_action(pre(obs)))[0].cpu())
                pred=torch.stack(values)
                if condition=='native':
                    native=pred
                    if not torch.equal(pred,load_file(run/'predictions.safetensors')['validation']):
                        raise RuntimeError('Native reload differs from saved predictions')
                target=tensors['action']
                condition_results[condition]={
                    'translation_error_m':float((pred[:,:3]-target[:,:3]).norm(dim=1).mean()),
                    'gripper_error_m':float((pred[:,9]-target[:,9]).abs().mean()),
                    'prediction_translation_change_m':float((pred[:,:3]-native[:,:3]).norm(dim=1).mean()),
                    'prediction_gripper_change_m':float((pred[:,9]-native[:,9]).abs().mean())}
        results.append({'steps':entry['steps'],'run':str(run),'conditions':condition_results})
        del policy,pre,post
        torch.cuda.empty_cache()
    output={'status':'passed','scope':'validation_input_shuffle_diagnostic',
        'permutation_seed':314159,'samples':1022,'results':results,'test_used':False,
        'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'limitation':'shuffling breaks natural image/state pairing; measures sensitivity, not causal task competence'}
    (ROOT/'artifacts/image-dependence.json').write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps(output,indent=2))


if __name__=='__main__':
    main()
