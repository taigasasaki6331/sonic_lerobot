"""Simulation-only synchronous 30 Hz recorded-observation policy bridge."""
import json
import os
from pathlib import Path
import select
import subprocess
import time
import numpy as np
from policy_action import policy_target

ROOT=Path(__file__).resolve().parents[1]


class PipePolicy:
    def __init__(self,run,episode,frames,timeout=10.):
        self.timeout=timeout
        self.buffer=b''
        self.process=subprocess.Popen([str(ROOT/'.venv-policy/bin/python'),'-I',
            str(ROOT/'scripts/policy_replay_worker.py'),'--run',str(run),
            '--episode',str(episode),'--frames',str(frames)],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
        try:
            self.metadata=self.read(60.)
            if self.metadata.get('ready') is not True or self.metadata.get('fps')!=30 or self.metadata.get('frames')!=frames:
                raise ValueError('Invalid worker handshake')
        except BaseException:
            self.close()
            raise

    def read(self,timeout):
        deadline=time.monotonic()+timeout
        while b'\n' not in self.buffer:
            remaining=deadline-time.monotonic()
            if remaining<=0 or not select.select([self.process.stdout],[],[],remaining)[0]:
                raise TimeoutError('Policy worker timeout')
            chunk=os.read(self.process.stdout.fileno(),4096)
            if not chunk: raise RuntimeError('Policy worker exited')
            self.buffer+=chunk
            if len(self.buffer)>65536: raise ValueError('Oversized policy message')
        line,self.buffer=self.buffer.split(b'\n',1)
        result=json.loads(line)
        if not isinstance(result,dict): raise ValueError('Policy message must be an object')
        return result

    def query(self,seq):
        self.process.stdin.write((json.dumps({'seq':seq})+'\n').encode())
        self.process.stdin.flush()
        return self.read(self.timeout)

    def begin(self,seq):
        # One outstanding, tiny request only. Never wait for pipe space.
        os.set_blocking(self.process.stdin.fileno(),False)
        payload=(json.dumps({'seq':seq})+'\n').encode()
        if os.write(self.process.stdin.fileno(),payload)!=len(payload):
            raise RuntimeError('Incomplete policy request')

    def poll(self):
        os.set_blocking(self.process.stdout.fileno(),False)
        if b'\n' not in self.buffer:
            try: chunk=os.read(self.process.stdout.fileno(),4096)
            except BlockingIOError: return None
            if not chunk: raise RuntimeError('Policy worker exited')
            self.buffer+=chunk
            if len(self.buffer)>65536: raise ValueError('Oversized policy message')
        if b'\n' not in self.buffer: return None
        line,self.buffer=self.buffer.split(b'\n',1)
        result=json.loads(line)
        if not isinstance(result,dict): raise ValueError('Policy message must be an object')
        return result

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try: self.process.wait(timeout=2.)
            except subprocess.TimeoutExpired:
                self.process.kill(); self.process.wait(timeout=2.)
        self.process.stdin.close(); self.process.stdout.close()


class ReplayBridge:
    def __init__(self,client,frames=90,fault='none',reference_mode='integrated'):
        if reference_mode not in ('integrated','measured'): raise ValueError('Unknown reference mode')
        self.client=client; self.frames=frames; self.fault=fault
        self.reference_mode=reference_mode
        self.last_seq=-1; self.last_time=-1.; self.last_target=None
        self.stop_reason=None; self.events=[]; self.request_ms=[]
        self.max_workspace_m=.15; self.settle=2.

    def target(self,now,origin,measured):
        if self.last_target is None: self.last_target=origin.copy()
        if self.stop_reason: return self.last_target.copy()
        if not np.isfinite(now) or now<self.last_time:
            self.stop_reason='non_monotonic_sim_time'; return self.last_target.copy()
        self.last_time=now
        if now<self.settle: return self.last_target.copy()
        seq=int((now-self.settle)*30+1e-7)
        if seq>=self.frames or seq==self.last_seq: return self.last_target.copy()
        try:
            if seq!=self.last_seq+1: raise ValueError('Skipped simulation action slot')
            start=time.monotonic()
            response=self.client.query(seq)
            self.request_ms.append((time.monotonic()-start)*1000)
            if seq==5 and self.fault=='stale': response['seq']=seq-1
            if seq==5 and self.fault=='invalid': response['action'][9]=-1.
            if response.get('seq')!=seq: raise ValueError('Duplicate/stale policy sequence')
            stamp=response.get('timestamp',float('nan'))
            if not np.isfinite(stamp) or abs(stamp-seq/30)>1e-5:
                raise ValueError('Stale/misaligned recorded timestamp')
            target,width=policy_target(response['action'],measured,
                action_reference='local-relative-h1',rotation_layout='columns')
            if self.reference_mode=='integrated':
                # Keep a servo reference: zero increments must HOLD the target,
                # not feed persistent tracking offsets back into the next target.
                # Express each increment in the current measured TCP axes first.
                if np.linalg.norm(measured[:3,3]-self.last_target[:3,3])>.05:
                    raise ValueError('Reference tracking error exceeded 5cm')
                increment=target[:3,3]-measured[:3,3]
                delta_rotation=target[:3,:3]@measured[:3,:3].T
                target=self.last_target.copy()
                target[:3,3]+=increment
                target[:3,:3]=delta_rotation@self.last_target[:3,:3]
            if np.linalg.norm(target[:3,3]-origin[:3,3])>self.max_workspace_m:
                raise ValueError('Simulation TCP workspace exceeded')
            self.last_seq=seq; self.last_target=target
            self.events.append({'seq':seq,'sim_time':float(now),'action':response['action'],
                'measured_tcp':measured.tolist(),'target_tcp':target.tolist(),'gripper_width_metadata_m':width})
        except (ValueError,TypeError,KeyError,RuntimeError,TimeoutError,OSError) as exc:
            self.stop_reason=f'{type(exc).__name__}: {exc}'
        return self.last_target.copy()

    def metrics(self):
        return {'policy_bridge':{'observation_source':'recorded_RGB_and_state',
            'camera_closed_loop':False,'live_inference':True,'lerobot_hz_sim_time':30,
            'accepted_actions':len(self.events),'requested_frames':self.frames,
            'all_frames_consumed':len(self.events)==self.frames,'latched_stop_reason':self.stop_reason,
            'stop_behavior':'hold_last_accepted_TCP_target_while_simulated_WBC_balances',
            'gripper_actuated':False,'sequence_applied_once':True,
            'request_wall_p95_ms':float(np.percentile(self.request_ms,95)) if self.request_ms else None,
            'synchronous_simulation_only':True,'real_time_deadline_verified':False,
            'reference_mode':self.reference_mode,
            'reference_semantics':'integrate increments in measured TCP axes; zero action holds reference' if self.reference_mode=='integrated' else 'reset each target to measured TCP plus increment',
            'worker':self.client.metadata,'fault_injection':self.fault}}

    def __enter__(self): return self
    def __exit__(self,*args): self.client.close()
