"""G1 aarch64 BUILD ONLY: SDK objects compiled, fake transport test executed.

No SDK executable linked/started; no participant/publisher/client instantiated.
Does not supply a hardware launcher or choose/validate a physical stop strategy.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))

FILES=('body_io_adapter.hpp','unitree_body_transport.hpp','unitree_body_transport.cpp','check_body_io_adapter.cpp')
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--on-gpu',action='store_true')
    args=parser.parse_args(); source=Path(__file__).resolve().parent
    from run_state_shadow import GPU,GPU_ROOT,GPU_OPTS,directory,run
    if not args.on_gpu:
        from check_body_io_adapter import TRANSPORT_PINNED
        from lowcmd_preview import SDK,INCLUDE,PINNED
        for name,digest in {**PINNED,**TRANSPORT_PINNED}.items():
            if sha(INCLUDE/name)!=digest: raise ValueError('Pinned SDK source changed: '+name)
        dest=directory(['ssh',*GPU_OPTS,GPU],GPU_ROOT+'/artifacts/body-io-build-')
        run(['scp',*GPU_OPTS,*[str(source/f) for f in FILES],str(source/'probe_body_io_build.py'),
            str(source/'run_state_shadow.py'),str(source.parent/'assets/network/g1-runtime-access.json'),
            str(SDK/'LICENSE'),GPU+':'+dest+'/'])
        run(['scp',*GPU_OPTS,'-r',str(SDK/'include'),GPU+':'+dest+'/sdk-include'])
        run(['scp',*GPU_OPTS,'-r',str(SDK/'thirdparty/include'),GPU+':'+dest+'/thirdparty-include'])
        result=subprocess.run(['ssh',*GPU_OPTS,GPU,'python3 -I '+shlex.quote(dest+'/probe_body_io_build.py')+' --on-gpu'],timeout=110)
        parent=source.parent/'artifacts/body-io-build'; parent.mkdir(exist_ok=True)
        run(['scp',*GPU_OPTS,'-r',GPU+':'+dest,str(parent)+'/'])
        print('Local build evidence: '+str(parent/Path(dest).name)); return result.returncode
    access=json.loads((source/'g1-runtime-access.json').read_bytes())
    opts=['-i',access['gpu_ssh_identity'],'-o','IdentitiesOnly=yes','-o','BatchMode=yes',
        '-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+access['gpu_known_hosts'],
        '-o','GlobalKnownHostsFile=/dev/null','-o','ConnectTimeout=5']
    ssh=['ssh',*opts,access['g1_host']]; dest=directory(ssh,'/tmp/g1-pika-body-io-build-')
    run(['scp',*opts,'-r',*[str(source/f) for f in FILES],str(source/'sdk-include'),
        str(source/'thirdparty-include'),str(source/'LICENSE'),access['g1_host']+':'+dest+'/'])
    output=source/'outputs'; output.mkdir(); report={}; logs=[]
    try:
        architecture=subprocess.check_output(ssh+['uname -m'],text=True,timeout=10).strip()
        if architecture!='aarch64': raise ValueError('Expected G1 aarch64')
        commands=[f'g++ -std=c++17 -O2 -Wall -Wextra -Werror {dest}/check_body_io_adapter.cpp -o {dest}/fake-check',
            f'{dest}/fake-check']
        for gate in (0,1):
            commands.append(f'g++ -std=c++17 -O2 -Wall -Wextra -DG1_PIKA_ENABLE_BODY_IO={gate} '
                f'-I{dest}/sdk-include -I{dest}/thirdparty-include -I{dest}/thirdparty-include/ddscxx '
                f'-c {dest}/unitree_body_transport.cpp -o {dest}/transport-build-{gate}.o')
        results=[]
        for command in commands:
            result=subprocess.run(ssh+[command],capture_output=True,timeout=35)
            logs.append(dict(command=command,returncode=result.returncode,stdout=result.stdout.decode(),stderr=result.stderr.decode()))
            results.append(result)
            if result.returncode: raise RuntimeError('G1 build-only check failed')
        fake=json.loads(results[1].stdout)
        if fake!=dict(fake_transport_checks=19,robot_commands_sent=False,physical_stop_confirmed=False):
            raise ValueError('Unexpected fake-only result')
        report=dict(passed=True,g1_architecture=architecture,fake_transport_checks=19,
            scope='SDK_binding_compile_and_fake_adapter_ONLY_NOT_hardware_control',
            compile_gate_values_tested=[0,1],sdk_objects_linked_or_executed=False,
            body_hardware_launcher_provided=False,robot_commands_sent=False,physical_stop_confirmed=False)
    except Exception as exc: report=dict(passed=False,error=type(exc).__name__+': '+str(exc),robot_commands_sent=False)
    report.update(g1_directory=dest,source_sha256={name:sha(source/name) for name in FILES})
    (output/'build-log.json').write_text(json.dumps(logs,indent=2)+'\n')
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2)); return 0 if report['passed'] else 1


if __name__=='__main__': raise SystemExit(main())
