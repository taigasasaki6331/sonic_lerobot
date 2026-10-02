"""GPU model load/inference smoke only, synthetic inputs, no controller or DDS."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models', type=Path, required=True)
    parser.add_argument('--trt', type=Path, default=Path('/home/gpu-user/TensorRT-192.0.2.3'))
    args = parser.parse_args()
    manifest = json.loads((args.models/'download-manifest.json').read_text())
    dest = Path(tempfile.mkdtemp(prefix='smoke-',dir=args.models))
    report = dict(passed=False, scope='synthetic_input_tensorrt_smoke_not_control_validation',
                  robot_commands_sent=False, checkpoint_revision=manifest['revision'], results=[])
    for kind in ('encoder','decoder'):
        rel = 'low_latency/model_'+kind+'.onnx'
        model = args.models/rel
        if hashlib.sha256(model.read_bytes()).hexdigest() != manifest['files'][rel]['sha256']:
            raise ValueError('Model hash mismatch')
        output = dest/(kind+'-output.json')
        cmd = [str(args.trt/'bin/trtexec'), '--onnx='+str(model),
               '--saveEngine='+str(dest/(kind+'.engine')), '--warmUp=100', '--duration=1',
               '--iterations=3', '--exportOutput='+str(output)]
        with (dest/(kind+'.log')).open('w') as log:
            completed = subprocess.run(cmd, stdout=log,stderr=subprocess.STDOUT,timeout=600)
        result = dict(model=kind,returncode=completed.returncode)
        if completed.returncode == 0 and output.exists():
            tensors = json.loads(output.read_text())
            values = [v for tensor in tensors for v in tensor['values']]
            result['finite_outputs'] = bool(values) and all(math.isfinite(v) for v in values)
            result['output_elements'] = len(values)
        report['results'].append(result)
    report['passed'] = all(r['returncode']==0 and r.get('finite_outputs',False) for r in report['results'])
    (dest/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2)); print('Artifacts:',dest)
    return 0 if report['passed'] else 1


if __name__=='__main__': raise SystemExit(main())
