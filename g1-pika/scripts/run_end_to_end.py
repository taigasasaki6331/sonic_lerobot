"""One-command simulated end-to-end acceptance run; no training or hardware."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]


def main():
    base=ROOT/'artifacts/end-to-end'; base.mkdir(parents=True,exist_ok=True)
    out=Path(tempfile.mkdtemp(prefix='run-',dir=base))
    summary={'scope':'recorded_observations_full_episode_to_simulated_WBC',
             'hardware_ready':False,'task_success_validated':False,
             'robot_commands_sent':False,'output':str(out),'checks':[]}
    manifest=json.loads((ROOT/'assets/datasets/valid49-split.json').read_text())
    frames=next(row['frames'] for row in manifest['selection'] if row['episode']==39)
    python=str(ROOT/'.venv/bin/python')
    tests=[('action','scripts/check_policy_action.py'),
           ('bridge','scripts/check_policy_bridge.py'),
           ('async','scripts/check_async_policy.py')]
    for name,script in tests:
        print(f'Checking {name}',flush=True)
        with (out/f'{name}.log').open('w') as log:
            run=subprocess.run([python,'-I',script],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=30)
        summary['checks'].append({'name':name,'passed':run.returncode==0})
    base_cmd=[python,'-I','scripts/sim_balance.py','--controller','wbc','--pika',
              '--policy-run','artifacts/full-rgb-residual/run-xg1fn3b_',
              '--policy-async','--policy-episode','39']
    for name,fault,count,seconds in [('full_episode','none',frames,60),('response_loss','silence',30,12)]:
        print(f'Running {name}: {count} frames, {seconds} simulation seconds',flush=True)
        case=out/name
        cmd=base_cmd+['--policy-frames',str(count),'--seconds',str(seconds),
                      '--policy-fault',fault,'--report-dir',str(case)]
        with (out/f'{name}.log').open('w') as log:
            try:
                run=subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=180)
                code=run.returncode
            except subprocess.TimeoutExpired:
                summary['checks'].append({'name':name,'passed':False,'error':'Run exceeded 180s'})
                continue
        filename='policy-sim-async' if fault=='none' else 'policy-sim-silence-async'
        try:
            report=json.loads((case/f'{filename}-latest.json').read_text())
            events=json.loads((case/f'{filename}-events.json').read_text())
            bridge=report['policy_bridge']
            sequence=[event['seq'] for event in events]
            if fault=='none':
                ok=(code==0 and report['passed'] and len(events)==frames
                    and sequence==list(range(frames)) and bridge['latched_stop_reason'] is None)
            else:
                ok=(code==1 and not report['passed'] and sequence==list(range(5))
                    and 'deadline' in (bridge['latched_stop_reason'] or '')
                    and report['sim_seconds']>=seconds-1e-6
                    and report['pelvis_height_min_m']>=.45 and report['tilt_max_rad']<=.8
                    and report['xy_displacement_max_m']<=.25 and report['mujoco_warning_count']==0)
            summary['checks'].append({'name':name,'passed':bool(ok),'exit_code':code,
                'accepted_actions':len(events),'stop_reason':bridge['latched_stop_reason'],
                'wbc_compute_p95_ms':report['whole_body_control_p95_ms'],
                'bridge_callback_p95_ms':bridge['callback_p95_ms'],'report':str(case/f'{filename}-latest.json')})
        except (OSError,ValueError,KeyError) as exc:
            summary['checks'].append({'name':name,'passed':False,'exit_code':code,'error':str(exc)})
    summary['passed']=all(check['passed'] for check in summary['checks'])
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2),flush=True)
    return 0 if summary['passed'] else 1


if __name__=='__main__': raise SystemExit(main())
