"""One-shot G1 receive_state scheduling trial; no persistent privilege grant.

Run manually with sudo after authorization. Only newly started, hash-matched
unitree-owned receive_state --stream processes qualify. Never starts a robot
program or changes a system scheduler setting. Restores living tasks on exit.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import signal
import socket
import time

EXPECTED_SHA='7196b097f972c08d4aa545f920ee67bdf521aca4d7117645332e6224376fc134'


def identity(pid,uid,earliest_tick):
    proc=Path('/proc')/str(pid)
    try:
        if proc.stat().st_uid!=uid: return None
        exe=os.readlink(proc/'exe')
        if not re.fullmatch(r'/tmp/g1-pika-online-[A-Za-z0-9]{6}/receive_state',exe): return None
        if (proc/'cmdline').read_bytes().split(b'\0')!=[exe.encode(),b'--stream',b'']: return None
        fields=(proc/'stat').read_text().rsplit(')',1)[1].split()
        start=int(fields[19])
        if start<earliest_tick: return None
        if hashlib.sha256((proc/'exe').read_bytes()).hexdigest()!=EXPECTED_SHA: return None
        return (pid,start,exe)
    except (FileNotFoundError,ProcessLookupError,PermissionError): return None


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-temporary-priority',action='store_true')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not args.allow_temporary_priority: parser.error('Explicit temporary priority permission required')
    if os.geteuid()!=0 or socket.gethostname()!='unitree-g1-nx': parser.error('Run with sudo on the verified G1 PC only')
    runtime=int(Path('/proc/sys/kernel/sched_rt_runtime_us').read_text())
    period=int(Path('/proc/sys/kernel/sched_rt_period_us').read_text())
    if not 0<runtime<period: parser.error('Existing RT CPU quota must be enabled; it will not be changed')
    uid=pwd.getpwnam('unitree').pw_uid
    earliest=int(float(Path('/proc/uptime').read_text().split()[0])*os.sysconf('SC_CLK_TCK'))
    # Reserve the report before changing any process; never overwrite a log.
    output=args.output.open('x')
    tracked={}; events=[]; restored=[]; errors=[]; stop=False
    def interrupted(signum,frame):
        nonlocal stop
        stop=True
    signal.signal(signal.SIGINT,interrupted); signal.signal(signal.SIGTERM,interrupted)
    started=time.monotonic()
    print('READY: receive_state only, RR priority 1, 90-second limit, automatic restoration',flush=True)
    try:
        while not stop and time.monotonic()-started<90:
            for path in Path('/proc').iterdir():
                if not path.name.isdigit(): continue
                pid=int(path.name)
                if pid in tracked or len(tracked)>=2: continue
                found=identity(pid,uid,earliest)
                if found is None: continue
                tasks=list((path/'task').iterdir())
                # This program is normally TS/0; refuse an already customized
                # receiver instead of guessing what should be restored.
                if any(os.sched_getscheduler(int(t.name))!=os.SCHED_OTHER or
                       os.sched_getparam(int(t.name)).sched_priority!=0 for t in tasks):
                    raise RuntimeError('Receiver already has custom thread priorities')
                if identity(pid,uid,earliest)!=found: continue
                tracked[pid]=found
                os.sched_setscheduler(pid,os.SCHED_RR,os.sched_param(1))
                events.append(dict(pid=pid,start_tick=found[1],executable=found[2],policy='RR',priority=1,
                                   observed_policy=os.sched_getscheduler(pid),observed_priority=os.sched_getparam(pid).sched_priority))
                print('Applied receive-only RR/1 to PID '+str(pid),flush=True)
            if len(tracked)==2 and all(identity(pid,uid,earliest)!=found for pid,found in tracked.items()): break
            time.sleep(.05)
    except Exception as exc: errors.append(type(exc).__name__+': '+str(exc))
    finally:
        for pid,found in tracked.items():
            if identity(pid,uid,earliest)!=found:
                restored.append(dict(pid=pid,status='process_exited')); continue
            try:
                # Also restore RR/1 threads inherited after the main-thread
                # change. No other process or scheduling class is touched.
                for task in (Path('/proc')/str(pid)/'task').iterdir():
                    tid=int(task.name)
                    try:
                        if os.sched_getscheduler(tid)==os.SCHED_RR and os.sched_getparam(tid).sched_priority==1:
                            os.sched_setscheduler(tid,os.SCHED_OTHER,os.sched_param(0))
                    except ProcessLookupError: pass
                restored.append(dict(pid=pid,status='normal_scheduling_restored'))
            except Exception as exc: errors.append('restore '+str(pid)+': '+str(exc))
        report=dict(scope='bounded_receive_only_priority_trial',robot_commands_sent=False,
                    receiver_sha256=EXPECTED_SHA,events=events,restored=restored,errors=errors,
                    elapsed_s=time.monotonic()-started,persistent_settings_changed=False,
                    completed=len(events)==2 and not errors)
        json.dump(report,output,indent=2); output.write('\n'); output.close()
        print(json.dumps(report),flush=True)
    return 0 if report['completed'] else 1


if __name__=='__main__': raise SystemExit(main())
