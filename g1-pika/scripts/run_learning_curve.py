"""Predeclared 3000/10000-step comparison on validation only; no test or hardware."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    base = ROOT/'artifacts/learning-curve'
    base.mkdir(parents=True,exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix='comparison-',dir=base))
    plan = {'steps':[3000,10000],'seed':42,'model':'unchanged small ACT RGB2 96x128',
        'selection_data':'validation episodes 39..43 only','test_used':False,
        'purpose':'test whether more optimization improves held-out errors; no automatic deployment'}
    (directory/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    results = []
    previous = None
    for steps in plan['steps']:
        command = [sys.executable,'-I',str(ROOT/'scripts/train_gpu_smoke.py'),
                   '--full-data','--steps',str(steps),'--checkpoint-every','1000']
        if previous:
            command += ['--resume',str(Path(previous['run'])/f'resume-step-{previous["steps"]:06d}.pt')]
        subprocess.run(command,check=True)
        report = json.loads((ROOT/'artifacts/full-rgb-baseline-latest.json').read_text())
        subprocess.run([sys.executable,'-I',str(ROOT/'scripts/check_full_rgb_run.py')],check=True)
        audit = json.loads((ROOT/'artifacts/full-rgb-audit-latest.json').read_text())
        if previous and report['losses'][:previous['steps']] != previous['losses']:
            raise AssertionError('Resume history differs')
        baseline_path = ROOT/'artifacts/full-rgb-baseline/run-79a2ge2g/report.json'
        baseline = json.loads(baseline_path.read_text())
        if report['losses'][:1000] != baseline['losses']:
            raise AssertionError('First 1000 updates differ from accepted baseline')
        v = report['metrics']['validation']
        gates = {
            'position_better_than_hold':v['translation_l2_mean_m'] < v['no_motion_translation_l2_mean_m'],
            'moving_position_better_than_hold':audit['moving_translation_error_m'] < audit['moving_no_motion_error_m'],
            'rotation_better_than_hold':audit['rotation_error_mean_rad'] < audit['no_motion_rotation_error_mean_rad'],
            'gripper_better_than_hold':v['gripper_mae_m'] < v['hold_gripper_mae_m'],
            'no_degenerate_rotation':audit['invalid_rotation_predictions']==0,
            'no_negative_gripper':v['negative_gripper_predictions']==0}
        results.append({'steps':steps,'run':report['run'],'validation':v,'audit':audit,
            'diagnostic_gates':gates,'all_diagnostic_gates_passed':all(gates.values()),
            'training_seconds_this_stage':report['training_seconds'],
            'cached_inference_p95_ms':report['cached_inference_p95_ms'],
            'first_1000_losses_equal_previous_baseline':True})
        previous = report
        summary = {'status':'completed' if steps==plan['steps'][-1] else 'running',
            'plan':plan,'results':results,'hardware_ready':False,'test_used':False,
            'limitation':'single seed and repeated validation; no statistical or task-success guarantee',
            'comparison':str(directory)}
        (directory/'results.json').write_text(json.dumps(summary,indent=2)+'\n')
        (ROOT/'artifacts/learning-curve-latest.json').write_text(json.dumps(summary,indent=2)+'\n')
        print(json.dumps(results[-1],indent=2),flush=True)


if __name__ == '__main__':
    main()
