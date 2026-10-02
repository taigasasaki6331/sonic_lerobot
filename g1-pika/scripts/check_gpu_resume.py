"""Compare uninterrupted CUDA training with stop/save/restart training."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    import torch
    from safetensors.torch import load_file
    trainer = ROOT/'scripts/train_gpu_smoke.py'
    def train(steps, resume=None):
        command = [sys.executable,'-I',str(trainer),'--steps',str(steps),'--checkpoint-every','10']
        if resume:
            command += ['--resume',str(resume)]
        subprocess.run(command,check=True)
        return json.loads((ROOT/'artifacts/gpu-smoke-latest.json').read_text())
    full = train(20)
    partial = train(10)
    checkpoint = Path(partial['run'])/'resume-step-000010.pt'
    resumed = train(20,checkpoint)
    if full['losses'] != resumed['losses'] or partial['losses'] != full['losses'][:10]:
        raise AssertionError('Resume losses differ')
    def exact(left,right):
        if isinstance(left,torch.Tensor):
            return isinstance(right,torch.Tensor) and torch.equal(left,right)
        if isinstance(left,dict):
            return left.keys() == right.keys() and all(exact(left[k],right[k]) for k in left)
        if isinstance(left,(tuple,list)):
            return len(left) == len(right) and all(exact(a,b) for a,b in zip(left,right))
        return left == right
    for name in ['predictions.safetensors','pretrained_model/model.safetensors']:
        if not exact(load_file(Path(full['run'])/name),load_file(Path(resumed['run'])/name)):
            raise AssertionError(f'Resume differs: {name}')
    for key in ['model','optimizer','cpu_rng','cuda_rng','step','identity',
                'permutation','cursor','seen','examples_drawn']:
        left = torch.load(Path(full['run'])/'resume-step-000020.pt',map_location='cpu',weights_only=True)
        right = torch.load(Path(resumed['run'])/'resume-step-000020.pt',map_location='cpu',weights_only=True)
        if not exact(left[key],right[key]):
            raise AssertionError(f'Resume state differs: {key}')
    report = {'status':'passed','scope':'20_steps_vs_10_then_new_process_resume_to_20',
        'losses_model_predictions_optimizer_cpu_cuda_rng_exact':True,
        'full_run':full['run'],'partial_run':partial['run'],'resumed_run':resumed['run'],
        'trainer_sha256':hashlib.sha256(trainer.read_bytes()).hexdigest(),
        'hardware_ready':False,'unexpected_crash_tested':False}
    (ROOT/'artifacts/gpu-resume-check.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
