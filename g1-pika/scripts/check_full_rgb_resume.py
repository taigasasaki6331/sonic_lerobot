"""Verify the 1000-step full-data baseline by replaying its latter 500 steps."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    import torch
    from safetensors.torch import load_file
    original = json.loads((ROOT/'artifacts/full-rgb-baseline-latest.json').read_text())
    if original['steps']!=1000 or original['resumed_from_step']!=0:
        raise RuntimeError('Expected fresh 1000-step reference run')
    reference = Path(original['run'])
    subprocess.run([sys.executable,'-I',str(ROOT/'scripts/train_gpu_smoke.py'),'--full-data',
        '--resume',str(reference/'resume-step-000500.pt'),'--steps','1000',
        '--checkpoint-every','500'],check=True)
    resumed = json.loads((ROOT/'artifacts/full-rgb-baseline-latest.json').read_text())
    resumed_path = Path(resumed['run'])
    def exact(a,b):
        if isinstance(a,torch.Tensor):
            return isinstance(b,torch.Tensor) and torch.equal(a,b)
        if isinstance(a,dict):
            return a.keys()==b.keys() and all(exact(a[k],b[k]) for k in a)
        if isinstance(a,(list,tuple)):
            return len(a)==len(b) and all(exact(x,y) for x,y in zip(a,b))
        return a==b
    if original['losses']!=resumed['losses']:
        raise AssertionError('Losses differ on full-data resume')
    for name in ['predictions.safetensors','pretrained_model/model.safetensors']:
        if not exact(load_file(reference/name),load_file(resumed_path/name)):
            raise AssertionError(f'Resume differs: {name}')
    a = torch.load(reference/'resume-step-001000.pt',map_location='cpu',weights_only=True)
    b = torch.load(resumed_path/'resume-step-001000.pt',map_location='cpu',weights_only=True)
    if not exact(a,b):
        raise AssertionError('Model/optimizer/sampler/RNG checkpoint differs')
    report = {'status':'passed','scope':'full_data_1000_vs_500_plus_500',
        'reference_run':str(reference),'resumed_run':str(resumed_path),
        'all_losses_weights_predictions_optimizer_sampler_rng_exact':True,
        'training_unique_samples_seen':resumed['unique_training_samples_seen'],
        'test_used':False,'hardware_ready':False}
    (ROOT/'artifacts/full-rgb-resume-check.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
