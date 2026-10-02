"""Predeclared 3000-step residual-width comparison against absolute-width ACT."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]


def main():
    base=ROOT/'artifacts/gripper-residual'
    base.mkdir(parents=True,exist_ok=True)
    directory=Path(tempfile.mkdtemp(prefix='comparison-',dir=base))
    plan={'steps':3000,'seed':42,'change':'internal width target = future width - measured current width',
          'external_action':'unchanged 10D local h1, columns rotation, future absolute width',
          'test_used':False,'no_clipping':True}
    (directory/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    subprocess.run([sys.executable,'-I',str(ROOT/'scripts/train_gpu_smoke.py'),
        '--full-data','--gripper-residual','--steps','3000','--checkpoint-every','1000'],check=True)
    subprocess.run([sys.executable,'-I',str(ROOT/'scripts/check_full_rgb_run.py'),'--residual'],check=True)
    report=json.loads((ROOT/'artifacts/full-rgb-residual-latest.json').read_text())
    audit=json.loads((ROOT/'artifacts/full-rgb-residual-audit-latest.json').read_text())
    previous=json.loads((ROOT/'artifacts/learning-curve-latest.json').read_text())
    reference=next(r for r in previous['results'] if r['steps']==3000)
    reference_report=json.loads((Path(reference['run'])/'report.json').read_text())
    for key in ['samples_sha256','seed','steps','batch_size','evaluation_indices']:
        if report[key]!=reference_report[key]:
            raise RuntimeError(f'Comparison mismatch: {key}')
    v=report['metrics']['validation']
    gates={
        'position_better_than_hold':v['translation_l2_mean_m']<v['no_motion_translation_l2_mean_m'],
        'moving_position_better_than_hold':audit['moving_translation_error_m']<audit['moving_no_motion_error_m'],
        'rotation_better_than_hold':audit['rotation_error_mean_rad']<audit['no_motion_rotation_error_mean_rad'],
        'gripper_better_than_hold':v['gripper_mae_m']<v['hold_gripper_mae_m'],
        'no_negative_width':v['negative_gripper_predictions']==0,
        'no_degenerate_rotation':audit['invalid_rotation_predictions']==0}
    result={'status':'completed','plan':plan,'run':report['run'],
        'absolute_width_reference':reference,'residual_validation':v,'residual_audit':audit,
        'diagnostic_gates':gates,'all_diagnostic_gates_passed':all(gates.values()),
        'training_seconds':report['training_seconds'],'cached_inference_p95_ms':report['cached_inference_p95_ms'],
        'hardware_ready':False,'test_used':False,'comparison':str(directory),
        'warning':'Native ACT/postprocessor output is residual width: mandatory action_codec.json decoding.'}
    (directory/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    (ROOT/'artifacts/gripper-residual-latest.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
