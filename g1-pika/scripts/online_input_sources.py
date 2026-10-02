"""Explicitly authorized input-only deployment; never invoked by offline checks.

Runs on GPU PC. Builds the project's receive-only C subscriber, starts
bounded camera/gripper readers and an independent body-history ZMQ service.
Serial open can reset the MCU. No actuator driver commands are sent.
"""
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
from sonic_process import JsonProcess


REMOTE_CLEANUP = r'''
import json,os,re,signal,sys,time
from pathlib import Path
root=sys.argv[1]
if not re.fullmatch(r'/tmp/g1-pika-online-[A-Za-z0-9_]{6,12}',root): raise ValueError('Cleanup scope')
targets={root+'/receive_state',root+'/g1_camera_stream.py',root+'/body_history_service.py',
         root+'/body-runtime-package/runtime/local_body_service.py'}
def matching():
    found=[]
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit(): continue
        try:
            if entry.stat().st_uid!=os.getuid(): continue
            args=(entry/'cmdline').read_bytes().decode().split('\0')
            if args[0] in targets or (len(args)>2 and args[1]=='-I' and args[2] in targets):
                found.append(int(entry.name))
        except (FileNotFoundError,ProcessLookupError,PermissionError): pass
    return found
terminated=matching()
for pid in terminated:
    try: os.kill(pid,signal.SIGTERM)
    except ProcessLookupError: pass
deadline=time.monotonic()+3
while matching() and time.monotonic()<deadline: time.sleep(.05)
remaining=matching()
print(json.dumps(dict(confirmed=not remaining,terminated_input_pids=terminated,remaining_input_pids=remaining)))
sys.exit(bool(remaining))
'''


class InputSources:
    def __init__(self, source, access, online, logs, audit=None,body_runtime_package=None,body_runtime_report=None):
        self.children=[]; self.directory=None; self.ssh=None; self.cleanup=None; self.audit=audit
        self.runtime_build=None; self.runtime_report=body_runtime_report; self.runtime_report_recovered=False
        self.runtime_scp=None
        source=Path(source)
        if access['g1_host']!='unitree@192.0.2.11': raise ValueError('Unexpected G1 source host')
        if access['gpu_wired_ip']!='192.0.2.12': raise ValueError('Unexpected wired source IP')
        route=subprocess.check_output(['ip','route','get','192.0.2.11'],text=True,timeout=5)
        if 'dev '+access['gpu_interface'] not in route or 'src '+access['gpu_wired_ip'] not in route:
            raise ValueError('Verified wired route required; no fallback')
        opts=['-i',access['gpu_ssh_identity'],'-o','IdentitiesOnly=yes','-o','BatchMode=yes',
              '-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+access['gpu_known_hosts'],
              '-o','GlobalKnownHostsFile=/dev/null','-o','ConnectTimeout=5',
              '-o','ServerAliveInterval=5','-o','ServerAliveCountMax=2']
        ssh=['ssh',*opts,access['g1_host']]
        self.ssh=ssh
        receiver=source/'state_receiver'
        manifest=json.loads((receiver/'generated/manifest.json').read_text())
        for name,digest in manifest['sha256'].items():
            if hashlib.sha256((receiver/name).read_bytes()).hexdigest()!=digest: raise ValueError('DDS generated source hash')
        if audit is not None: audit['g1_connection_attempted']=True
        target=subprocess.check_output(ssh+['mktemp -d /tmp/g1-pika-online-XXXXXX'],text=True,timeout=10).strip()
        if not target.startswith('/tmp/g1-pika-online-') or any(ch.isspace() for ch in target): raise ValueError('Invalid remote temporary directory')
        self.directory=target
        if audit is not None: audit['source_directory']=target
        names=['g1_camera_stream.py','state_history.py','zmq_transport.py','gripper_observation.py',
               'pika_gripper.py','LICENSE','LICENSE.pika_geometry','pyserial-3.5-py2.py3-none-any.whl',
               'body_history_service.py','body_history_transport.py','sonic_process.py']
        subprocess.run(['scp',*opts,'-r',str(receiver),*[str(source/name) for name in names],
                        access['g1_host']+':'+target+'/'],check=True,timeout=30)
        code=target+'/state_receiver'
        compile_command="grep -q '#define DDS_VERSION \"0.10.2\"' /usr/local/include/dds/version.h && "+shlex.join([
            'gcc','-O2','-Wall','-Wextra','-I/usr/local/include','-I'+code+'/generated',code+'/receive_state.c',
            code+'/generated/State.c','-L/usr/local/lib','-Wl,-rpath,/usr/local/lib','-lddsc','-lm','-o',target+'/receive_state'])
        subprocess.run(ssh+[compile_command],check=True,timeout=30)
        env=['env','G1_STATE_INTERFACE='+access['g1_interface'],'OPENBLAS_NUM_THREADS=1','OMP_NUM_THREADS=1','MKL_NUM_THREADS=1']
        try:
            if body_runtime_package is not None:
                package=Path(body_runtime_package)
                # Immutable source package and same-host native build. Never
                # copy/load the tiger x86 .so as if it were an aarch64 binary.
                subprocess.run(ssh+['mkdir '+shlex.quote(target+'/body-runtime-package')],check=True,timeout=10)
                subprocess.run(['scp',*opts,'-r',str(package/'runtime'),str(package/'manifest.json'),
                    access['g1_host']+':'+target+'/body-runtime-package/'],check=True,timeout=30)
                runtime=target+'/body-runtime-package/runtime'; binary_root=target+'/body-runtime-build'
                built=json.loads(subprocess.check_output(ssh+[shlex.join(['python3','-I',runtime+'/launch_body_runtime.py',
                    '--build-only','--output',binary_root])],text=True,timeout=45))
                if (built.get('machine')!='aarch64' or built.get('hardware_transport_linked') is not False
                        or built.get('robot_commands_sent') is not False): raise ValueError('G1 record runtime build contract')
                self.runtime_build=built
                if body_runtime_report is not None:
                    self.runtime_scp=['scp',*opts,access['g1_host']+':'+target+'/body-runtime-report.json',str(body_runtime_report)]
                runtime_command=shlex.join([target+'/receive_state','--stream','--verify-crc'])+' | '+shlex.join([
                    'python3','-I',runtime+'/local_body_service.py','--endpoint','tcp://192.0.2.11:6077',
                    '--peer-ip',access['gpu_wired_ip'],'--profile',runtime+'/profile.json','--config',runtime+'/body-lifecycle.json',
                    '--native-runtime',binary_root+'/body-runtime.so','--require-crc','--seconds','60',
                    '--report',target+'/body-runtime-report.json'])
                runtime_child=JsonProcess(ssh+[shlex.join(env+['timeout','--kill-after=3s','90s','bash','-c',runtime_command])],
                    logs('g1-body-runtime'),startup_timeout=15)
                self.children.append(runtime_child)
                if runtime_child.ready!=dict(ready=True,scope='local_body_boundary_record_only',robot_commands_sent=False):
                    raise ValueError('Body runtime record handshake')
                if audit is not None: audit['body_runtime_build']=built
            body_command=shlex.join([target+'/receive_state','--stream'])+' | '+shlex.join([
                'python3','-I',target+'/body_history_service.py','--endpoint',online['body_endpoint'],
                '--peer-ip',access['gpu_wired_ip'],'--max-frames',str(online['seconds']*50),'--seconds','60'])
            body=JsonProcess(ssh+[shlex.join(env+['timeout','--kill-after=3s','90s','bash','-c',body_command])],logs('g1-body'),startup_timeout=15)
            self.children.append(body)
            if body.ready!=dict(ready=True,scope='body_history_input_only',robot_commands_sent=False): raise ValueError('Body source handshake')
            camera_args=env+['timeout','--kill-after=3s','90s','python3','-I',target+'/g1_camera_stream.py',
                '--state-reader',target+'/receive_state','--state-history','--zmq','--gripper-state',
                '--max-frames',str(online['seconds']*30+3),'--fisheye-device',access['right_fisheye_device'],
                '--realsense-device',access['right_realsense_device']]
            camera=JsonProcess(ssh+[shlex.join(camera_args)],logs('g1-camera'),startup_timeout=15)
            self.children.append(camera)
            if camera.ready.get('scope')!='right_live_images_no_robot_commands': raise ValueError('Camera source handshake')
        except BaseException:
            self.close(); raise

    def wait(self):
        codes=[child.process.wait(timeout=5) for child in self.children]
        if any(codes): raise RuntimeError('Input source exit codes: '+str(codes))
        return codes

    def close(self):
        for child in self.children: child.close()
        if self.directory and self.ssh and self.cleanup is None:
            try:
                result=subprocess.run(self.ssh+[shlex.join(['python3','-c',REMOTE_CLEANUP,self.directory])],
                                      capture_output=True,text=True,timeout=10)
                self.cleanup=json.loads(result.stdout)
                if result.returncode: self.cleanup['confirmed']=False
            except Exception as exc:
                self.cleanup=dict(confirmed=False,error=type(exc).__name__+': '+str(exc))
            if self.audit is not None: self.audit['source_cleanup']=self.cleanup
        if self.runtime_scp and not self.runtime_report_recovered:
            try:
                recovered=subprocess.run(self.runtime_scp,capture_output=True,timeout=10)
                self.runtime_report_recovered=recovered.returncode==0
            except subprocess.TimeoutExpired: self.runtime_report_recovered=False
