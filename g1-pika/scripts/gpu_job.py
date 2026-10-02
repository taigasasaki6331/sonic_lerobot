"""Detached supervisor for explicitly scoped GPU smoke jobs (no robot commands)."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def write_status(directory, data):
    temporary = directory/'status.json.tmp'
    temporary.write_text(json.dumps(data,indent=2)+'\n')
    os.replace(temporary,directory/'status.json')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['start','status','supervise'])
    parser.add_argument('--kind',choices=['resume-check','smoke','full-rgb','learning-curve','gripper-residual'],default='resume-check')
    parser.add_argument('--steps',type=int,default=100)
    parser.add_argument('--job',type=Path)
    args = parser.parse_args()
    base = ROOT/'artifacts/jobs'
    if args.mode == 'start':
        if not 1 <= args.steps <= 1000:
            parser.error('steps must be 1..1000')
        base.mkdir(parents=True,exist_ok=True)
        directory = Path(tempfile.mkdtemp(prefix='job-',dir=base))
        command = [sys.executable,'-I',str(ROOT/'scripts/check_gpu_resume.py')]
        if args.kind == 'smoke':
            command = [sys.executable,'-I',str(ROOT/'scripts/train_gpu_smoke.py'),'--steps',str(args.steps)]
        elif args.kind == 'full-rgb':
            command = [sys.executable,'-I',str(ROOT/'scripts/run_full_rgb_baseline.py'),'--steps',str(args.steps)]
        elif args.kind == 'learning-curve':
            command = [sys.executable,'-I',str(ROOT/'scripts/run_learning_curve.py')]
        elif args.kind == 'gripper-residual':
            command = [sys.executable,'-I',str(ROOT/'scripts/run_gripper_residual.py')]
        (directory/'request.json').write_text(json.dumps({'command':command,'kind':args.kind})+'\n')
        write_status(directory,{'state':'starting','job':str(directory)})
        with (directory/'job.log').open('xb') as log:
            process = subprocess.Popen([sys.executable,'-I',str(Path(__file__).resolve()),
                'supervise','--job',str(directory)],stdin=subprocess.DEVNULL,
                stdout=log,stderr=subprocess.STDOUT,start_new_session=True,close_fds=True)
        print(json.dumps({'job':str(directory),'supervisor_pid':process.pid}))
        return
    if args.job is None or not args.job.resolve().is_relative_to(base.resolve()):
        parser.error('job must be under artifacts/jobs')
    directory = args.job.resolve(strict=True)
    if args.mode == 'status':
        print((directory/'status.json').read_text())
        print('\n'.join((directory/'job.log').read_text(errors='replace').splitlines()[-15:]))
        return
    request = json.loads((directory/'request.json').read_text())
    state = {'state':'running','job':str(directory),'supervisor_pid':os.getpid(),
             'started_unix':time.time(),'kind':request['kind']}
    write_status(directory,state)
    try:
        with (base/'training.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            result = subprocess.run(request['command'],check=False)
        state.update(state='passed' if result.returncode==0 else 'failed',exit_code=result.returncode)
    except Exception as exc:
        state.update(state='failed',error=str(exc))
    state['ended_unix'] = time.time()
    write_status(directory,state)


if __name__ == '__main__':
    main()
