"""Portable G1 record-runtime launcher. Read-only DDS in, native memory out.

Package includes sources/profile, not an architecture-portable binary. Builds in
a NEW output directory. Does not load SDK clients or publish any command type.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parent))
from local_body_service import endpoint_filter


def terminate(process):
    if process is not None and process.poll() is None:
        process.terminate()
        try: process.wait(timeout=2)
        except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=2)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-only',action='store_true')
    parser.add_argument('--interface'); parser.add_argument('--endpoint'); parser.add_argument('--peer-ip')
    parser.add_argument('--receiver',type=Path,help='Explicit existing read-only receive_state binary, or compile bundled source')
    parser.add_argument('--seconds',type=int,choices=range(1,61),default=30)
    parser.add_argument('--output',type=Path,help='NEW output directory (default /tmp/g1-pika-body-runtime-*)')
    args=parser.parse_args(); source=Path(__file__).resolve().parent
    manifest=json.loads((source.parent/'manifest.json').read_bytes())
    if manifest.get('scope')!='record_only_runtime_package' or manifest.get('robot_commands_sent') is not False:
        parser.error('Record-only package manifest required')
    for name,digest in manifest['files'].items():
        path=(source/name).resolve()
        if not path.is_relative_to(source) or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            parser.error('Package file changed: '+name)
    if not args.build_only:
        if not args.interface or not args.endpoint or not args.peer_ip: parser.error('Explicit interface/endpoint/peer-ip required')
        endpoint_filter(args.endpoint,args.peer_ip)
        if args.interface not in os.listdir('/sys/class/net'): parser.error('Unknown local network interface')
    if args.output:
        output=args.output.resolve(); output.mkdir(parents=True,exist_ok=False)
    else: output=Path(tempfile.mkdtemp(prefix='g1-pika-body-runtime-'))
    library=output/'body-runtime.so'
    subprocess.run(['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-pthread','-shared','-fPIC',
        '-I'+str(source),str(source/'body_runtime.cpp'),'-o',str(library)],check=True,timeout=30)
    build_report=dict(scope='record_only_runtime_host_build',machine=os.uname().machine,
        source_manifest_sha256=hashlib.sha256((source.parent/'manifest.json').read_bytes()).hexdigest(),
        library_sha256=hashlib.sha256(library.read_bytes()).hexdigest(),hardware_transport_linked=False,
        robot_commands_sent=False,output=str(output))
    (output/'build-report.json').write_text(json.dumps(build_report,indent=2)+'\n')
    print(json.dumps(build_report),flush=True)
    if args.build_only: return 0
    receiver_path=args.receiver.resolve() if args.receiver else output/'receive_state'
    if not args.receiver:
        headers=Path('/usr/local/include'); libs=Path('/usr/local/lib')
        version=headers/'dds/version.h'
        if not version.exists() or '#define DDS_VERSION "0.10.2"' not in version.read_text():
            parser.error('Need pinned CycloneDDS 0.10.2 headers/libs, or explicit --receiver')
        receiver_source=source/'state_receiver'
        subprocess.run(['gcc','-O2','-Wall','-Wextra','-I'+str(headers),'-I'+str(receiver_source/'generated'),
            str(receiver_source/'receive_state.c'),str(receiver_source/'generated/State.c'),
            '-L'+str(libs),'-Wl,-rpath,'+str(libs),'-lddsc','-lm','-o',str(receiver_path)],check=True,timeout=30)
    receiver=service=None
    def interrupt(signum,frame): raise KeyboardInterrupt('Local record launcher interrupted')
    signal.signal(signal.SIGTERM,interrupt)
    try:
        receiver=subprocess.Popen([str(receiver_path),'--stream','--verify-crc'],stdout=subprocess.PIPE,
            env=dict(os.environ,G1_STATE_INTERFACE=args.interface))
        service=subprocess.Popen([sys.executable,'-I',str(source/'local_body_service.py'),
            '--endpoint',args.endpoint,'--peer-ip',args.peer_ip,'--profile',str(source/'profile.json'),
            '--config',str(source/'body-lifecycle.json'),'--native-runtime',str(library),'--require-crc',
            '--seconds',str(args.seconds),'--report',str(output/'service-report.json')],stdin=receiver.stdout,
            env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1'))
        receiver.stdout.close(); return service.wait()
    finally:
        # Process cleanup is NOT a physical stop. This backend is memory only.
        terminate(service); terminate(receiver)


if __name__=='__main__': sys.exit(main())
