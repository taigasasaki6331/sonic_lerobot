"""30 live image pairs -> GPU inference -> log only, via two SSH connections."""
import base64
import argparse
import hashlib
import json
import os
from pathlib import Path
import select
import subprocess
import shlex
import shutil
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
GPU_ROOT='/home/gpu-user/g1-pika-training'
DIRECT=False
ACCESS=None
HOSTS={'g1':('unitree@192.0.2.7','/home/developer/.ssh/g1_pika_g1_ed25519'),
       'gpu':('galleria@192.0.2.9','/home/developer/.ssh/EXAMPLE_GPU_KEY')}


def options(which):
    if DIRECT and which=='g1':
        if ACCESS is None: raise ValueError('Direct mode requires --access-config')
        return (['-i',ACCESS['gpu_ssh_identity'],
                 '-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
                 '-o','UserKnownHostsFile='+ACCESS['gpu_known_hosts'],
                 '-o','GlobalKnownHostsFile=/dev/null','-o','ConnectTimeout=5',
                 '-o','ServerAliveInterval=5','-o','ServerAliveCountMax=2'],
                ACCESS['g1_host'])
    host,key=HOSTS[which]
    return ['-i',key,'-o','IdentitiesOnly=yes','-o','BatchMode=yes',
            '-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=5',
            '-o','ServerAliveInterval=5','-o','ServerAliveCountMax=2'],host


def ssh(which,command):
    opts,host=options(which); return ['ssh',*opts,host,command]


class Channel:
    def __init__(self,which,command,log):
        self.process=subprocess.Popen(shlex.split(command) if which=='local_gpu' else ssh(which,command),stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=log,bufsize=0)
        self.buffer=b''
        os.set_blocking(self.process.stdin.fileno(),False)
    def send(self,value):
        data=(json.dumps(value,allow_nan=False)+'\n').encode(); end=time.monotonic()+10
        while data:
            wait=end-time.monotonic()
            if wait<=0 or not select.select([],[self.process.stdin],[],wait)[1]:
                raise TimeoutError('SSH send timeout')
            try: count=os.write(self.process.stdin.fileno(),data)
            except BlockingIOError: continue
            if count<=0: raise RuntimeError('SSH write failed')
            data=data[count:]
    def read(self,timeout=10):
        end=time.monotonic()+timeout
        while b'\n' not in self.buffer:
            wait=end-time.monotonic()
            if wait<=0 or not select.select([self.process.stdout],[],[],wait)[0]:
                raise TimeoutError('SSH reply timeout')
            chunk=os.read(self.process.stdout.fileno(),65536)
            if not chunk: raise RuntimeError('SSH peer exited; see stderr log')
            self.buffer+=chunk
            if len(self.buffer)>2000000: raise ValueError('Oversized reply')
        line,self.buffer=self.buffer.split(b'\n',1)
        value=json.loads(line)
        if not isinstance(value,dict): raise ValueError('Expected object')
        return value
    def finish(self):
        self.send({'stop':True}); self.process.stdin.close()
        code=self.process.wait(timeout=10)
        if code: raise RuntimeError('Remote process exit '+str(code))
    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try: self.process.wait(timeout=3)
            except subprocess.TimeoutExpired: self.process.kill(); self.process.wait()
        for stream in (self.process.stdin,self.process.stdout):
            if not stream.closed: stream.close()


def main():
    global ROOT,DIRECT,ACCESS
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--direct-on-gpu',action='store_true')
    parser.add_argument('--state-reader',help='G1 path to read-only DDS executable')
    parser.add_argument('--zmq',action='store_true')
    parser.add_argument('--access-config',type=Path)
    parser.add_argument('--report-copy',type=Path)
    parser.add_argument('--gripper-state',action='store_true')
    parser.add_argument('--archive-sonic-inputs',action='store_true',help='Keep all image pairs and actual ten-frame body histories')
    args=parser.parse_args()
    if args.zmq and (not args.direct_on_gpu or not args.state_reader):
        parser.error('ZMQ test requires --direct-on-gpu and --state-reader')
    if args.gripper_state and not args.zmq: parser.error('Gripper integration requires ZMQ')
    if args.archive_sonic_inputs and not args.state_reader: parser.error('Archive requires state reader')
    DIRECT=args.direct_on_gpu
    if DIRECT:
        if not args.access_config: parser.error('Direct mode requires --access-config')
        ACCESS=json.loads(args.access_config.read_text())
    source_dir=Path(__file__).resolve().parent
    bundle_path=source_dir/'policy-bundle.json'
    if not bundle_path.is_file(): bundle_path=source_dir.parent/'config/policy-bundle.json'
    if not bundle_path.is_file(): raise ValueError('Pinned policy bundle manifest missing')
    if DIRECT: ROOT=Path(GPU_ROOT)
    base=ROOT/'artifacts/live-shadow'; base.mkdir(parents=True,exist_ok=True)
    out=Path(tempfile.mkdtemp(prefix='run-',dir=base)); channels=[]; logs=[]
    report={'passed':False,'scope':'continuous_right_images_to_GPU_diagnostic_no_actuation',
            'robot_commands_sent':False,'hardware_ready':False,'camera_closed_loop':False,
            'width_source':'assumed_0.04m_not_measured','transport':'G1 -> development PC -> galleria over SSH/Wi-Fi',
            'frames':[],'output':str(out)}
    try:
        if args.gripper_state:
            report['width_source']='encoder_with_legacy_linkage_geometry_not_calibrated'
        if DIRECT:
            report['transport']='G1 -> galleria over wired SSH; no development-PC image relay'
            route=subprocess.check_output(['ip','route','get','192.0.2.11'],text=True,timeout=5)
            report['route']=route.strip()
            if 'dev enp2s0' not in route or 'src 192.0.2.12' not in route:
                raise RuntimeError('Expected verified wired route; refusing fallback')
        paths={}
        for which,template,script in [('g1','/tmp/g1-pika-stream-XXXXXX','g1_camera_stream.py'),
                ('gpu',GPU_ROOT+'/artifacts/live-shadow-XXXXXX','probe_gpu_images.py')]:
            if DIRECT and which=='gpu':
                path=tempfile.mkdtemp(prefix='live-shadow-',dir=ROOT/'artifacts')
                shutil.copy2(source_dir/script,Path(path)/script)
                shutil.copy2(source_dir/'policy_bundle.py',Path(path)/'policy_bundle.py')
                shutil.copy2(bundle_path,Path(path)/'policy-bundle.json')
                paths[which]=path
                continue
            path=subprocess.check_output(ssh(which,'mktemp -d '+template),text=True,timeout=10).strip()
            if not path.startswith(template[:-6]) or any(c.isspace() for c in path):
                raise RuntimeError('Invalid remote directory')
            paths[which]=path; opts,host=options(which)
            files=[str(source_dir/script)]
            if which=='gpu': files += [str(source_dir/'policy_bundle.py'),str(bundle_path)]
            if args.zmq and which=='g1': files.append(str(source_dir/'zmq_transport.py'))
            if args.archive_sonic_inputs and which=='g1': files.append(str(source_dir/'state_history.py'))
            if args.gripper_state and which=='g1':
                files += [str(source_dir/name) for name in ('gripper_observation.py','pika_gripper.py',
                    'LICENSE','LICENSE.pika_geometry','pyserial-3.5-py2.py3-none-any.whl')]
            subprocess.run(['scp',*opts,*files,host+':'+path+'/'],check=True,timeout=15)
        report['remote_directories']=paths
        log=(out/'gpu.stderr.log').open('wb'); logs.append(log)
        width_arg='--packet-width' if args.gripper_state else '--diagnostic-width 0.04'
        gpu=Channel('local_gpu' if DIRECT else 'gpu',f'timeout 150s {GPU_ROOT}/.venv-gpu/bin/python -I {paths["gpu"]}/probe_gpu_images.py --root {GPU_ROOT} --policy-bundle {paths["gpu"]}/policy-bundle.json --images {paths["gpu"]} {width_arg} --stream',log)
        channels.append(gpu); report['gpu']=gpu.read(timeout=90)
        if report['gpu'].get('ready') is not True: raise ValueError('GPU not ready')
        print('GPU ready; starting G1 cameras',flush=True)
        log=(out/'g1.stderr.log').open('wb'); logs.append(log)
        state_arg=' --state-reader '+shlex.quote(args.state_reader) if args.state_reader else ''
        if DIRECT and ACCESS.get('right_fisheye_device'):
            state_arg+=' --fisheye-device '+shlex.quote(ACCESS['right_fisheye_device'])
            state_arg+=' --realsense-device '+shlex.quote(ACCESS['right_realsense_device'])
        if args.zmq: state_arg+=' --zmq'
        if args.gripper_state: state_arg+=' --gripper-state'
        if args.archive_sonic_inputs: state_arg+=' --state-history'
        report['g1_state_requested']=bool(args.state_reader)
        if DIRECT: report['access_config']=ACCESS
        env=('env G1_STATE_INTERFACE='+shlex.quote(ACCESS['g1_interface'])+' ') if DIRECT else ''
        g1=Channel('g1',env+f'timeout 90s python3 -I {paths["g1"]}/g1_camera_stream.py'+state_arg,log)
        channels.append(g1); report['g1']=g1.read(timeout=15)
        if report['g1'].get('ready') is not True: raise ValueError('Cameras not ready')
        g1_control=g1
        if args.zmq:
            import sys
            sys.path.insert(0,str(source_dir))
            from zmq_transport import ZmqChannel
            g1=ZmqChannel('tcp://192.0.2.11:6158')
            channels.append(g1)
            report['transport']='G1 DDS state + cameras -> wired ZMQ -> GPU inference -> local log; SSH startup only'
            report['gpu_libzmq']=g1.version()
        previous={}
        for seq in range(30):
            start=time.monotonic(); g1.send({'seq':seq}); packet=g1.read()
            if packet.get('seq')!=seq: raise ValueError('Camera sequence mismatch')
            if args.state_reader:
                state=packet['g1_state']
                if len(state['q'])!=35 or len(state['dq'])!=35 or packet['image_state_receive_skew_s']>.1:
                    raise ValueError('State/image alignment failed')
            for role,image in packet['images'].items():
                if image['frame_counter']<=previous.get(role,0): raise ValueError('Repeated camera frame')
                if not 0<=image['read_age_s']<=.5: raise ValueError('Stale camera read')
                previous[role]=image['frame_counter']
            gpu.send(packet); response=gpu.read()
            if response.get('seq')!=seq: raise ValueError('GPU sequence mismatch')
            response['round_trip_ms']=(time.monotonic()-start)*1000
            for role,image in packet['images'].items():
                blob=base64.b64decode(image.pop('jpeg'),validate=True)
                image['sha256']=hashlib.sha256(blob).hexdigest()
                if args.archive_sonic_inputs or seq in (0,29): (out/f'{seq:02d}-{role}.jpg').write_bytes(blob)
            response['capture']=packet; report['frames'].append(response)
            if (seq+1)%10==0: print(f'{seq+1}/30 live pairs inferred',flush=True)
            time.sleep(max(0,.2-(time.monotonic()-start)))
        g1.finish(); gpu.finish()
        if args.zmq and g1_control.process.wait(timeout=10)!=0:
            raise RuntimeError('G1 server exit failed')
        report['passed']=True
        report['all_image_pairs_archived']=args.archive_sonic_inputs
        report['actual_body_history_per_image_pair']=10 if args.archive_sonic_inputs else 0
        report['round_trip_p95_ms']=sorted(r['round_trip_ms'] for r in report['frames'])[28]
        report['inference_p95_ms']=sorted(r['inference_ms'] for r in report['frames'])[28]
    except Exception as exc:
        report['error']=str(exc)
    finally:
        for channel in channels: channel.close()
        for log in logs: log.close()
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        if args.report_copy: args.report_copy.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='frames'},indent=2))
    print('Recorded frames:',len(report['frames']))
    return 0 if report['passed'] else 1


if __name__=='__main__': raise SystemExit(main())
