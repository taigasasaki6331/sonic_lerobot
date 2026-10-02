"""GPU-only rejection tests against actual persistent SONIC child, no robot IO."""
import argparse
import copy
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from sonic_process import SonicProcess


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for field in ('binary','encoder','decoder','input','report'):
        parser.add_argument('--'+field,type=Path,required=True)
    args=parser.parse_args()
    if args.report.exists(): raise ValueError('Report exists')
    row=json.loads(args.input.read_text())['frames'][0]
    cases=[]
    for fault in ('shape','duplicate','width'):
        with args.report.with_suffix('.'+fault+'.log').open('w') as log:
            worker=SonicProcess(args.binary,args.encoder,args.decoder,log)
            error=None
            try:
                candidate=copy.deepcopy(row)
                if fault=='shape': candidate['encoder']=[0.]
                if fault=='width': candidate['gripper_width_m']=-.01
                if fault=='duplicate':
                    worker.infer(candidate)
                    worker.send(dict(op='infer',seq=0,row=candidate)); worker.read()
                else: worker.infer(candidate)
            except (ValueError,RuntimeError,OSError) as exc:
                error=type(exc).__name__+': '+str(exc)
            finally:
                try: worker.process.wait(timeout=3)
                finally: worker.close()
            cases.append(dict(fault=fault,rejected=error is not None,exit_code=worker.process.returncode,error=error))
    report=dict(passed=all(c['rejected'] and c['exit_code']==1 for c in cases),
                scope='real_SONIC_child_invalid_request_rejection',robot_commands_sent=False,cases=cases)
    args.report.write_text(json.dumps(report,indent=2)+'\n'); print(json.dumps(report,indent=2))
    return 0 if report['passed'] else 1


if __name__=='__main__': raise SystemExit(main())
