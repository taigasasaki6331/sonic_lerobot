"""Compare pinned LowCmd native memory on x86_64 and G1/aarch64; NO DDS IO.

Compile data classes and CRC only, no topic traits/SDK clients/publisher. Input
is a verified saved abstract journal. Observed machine ID remains diagnostic;
neither ABI agreement nor CRC agreement authorizes or validates motor control.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parent))


def digest(data): return hashlib.sha256(data).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--on-gpu',action='store_true')
    parser.add_argument('--run',type=Path,default=Path(__file__).resolve().parents[1]/'artifacts/body-lifecycle/run-6arb9pnq')
    parser.add_argument('--state-report',type=Path,required=False,
        default=Path(__file__).resolve().parents[1]/'artifacts/local-body/local-body-nZZEwC/outputs/g1/service-report.json')
    args=parser.parse_args(); source=Path(__file__).resolve().parent
    from run_state_shadow import GPU,GPU_ROOT,GPU_OPTS,directory,run
    if args.on_gpu:
        access=json.loads((source/'g1-runtime-access.json').read_bytes())
        opts=['-i',access['gpu_ssh_identity'],'-o','IdentitiesOnly=yes','-o','BatchMode=yes',
            '-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+access['gpu_known_hosts'],
            '-o','GlobalKnownHostsFile=/dev/null','-o','ConnectTimeout=5']
        ssh=['ssh',*opts,access['g1_host']]; dest=directory(ssh,'/tmp/g1-pika-lowcmd-abi-')
        stage=source/'data-only'
        run(['scp',*opts,'-r',str(stage),access['g1_host']+':'+dest+'/'])
        architecture=subprocess.check_output(ssh+['uname -m'],text=True,timeout=10).strip()
        if architecture!='aarch64': raise ValueError('Expected G1 aarch64')
        run(ssh+[f'g++ -std=c++17 -O2 -Wall -Wextra -I{dest}/data-only '
            f'{dest}/data-only/lowcmd_preview.cpp -o {dest}/preview'])
        result=subprocess.run(ssh+[shlex.quote(dest+'/preview')],input=(stage/'input.txt').read_bytes(),
            capture_output=True,timeout=20)
        (source/'aarch64-memory.hex').write_bytes(result.stdout)
        (source/'aarch64.stderr').write_bytes(result.stderr)
        baseline=(stage/'x86_64-memory.hex').read_bytes()
        expected=json.loads((stage/'expected.json').read_bytes())
        report=dict(passed=result.returncode==0 and result.stdout==baseline,
            scope='native_LowCmd_ABI_CRC_data_only_NOT_DDS_wire_or_motor_control',
            g1_architecture=architecture,record_count=expected['record_count'],native_size_bytes=1004,
            mode_machine=expected['mode_machine'],mode_machine_source='saved_read_only_state_NOT_control_identity',
            source_state_report_sha256=expected['source_state_report_sha256'],
            source_lifecycle_report_sha256=expected['source_lifecycle_report_sha256'],
            x86_64_memory_sha256=digest(baseline),aarch64_memory_sha256=digest(result.stdout),
            native_memory_equal=result.stdout==baseline,independent_python_crc_verified=expected['python_crc_verified'],
            binary_exit_code=result.returncode,g1_directory=dest,
            pinned_sdk_source_sha256=expected['pinned_sdk_source_sha256'],
            hardware_ready=False,robot_commands_sent=False,physical_stop_validated=False,
            limitations=['Native object memory, not DDS/CDR delivery',
                'No G1 SDK clients/publishers/ownership/INIT/serial or firmware actuation',
                'Quoted motor mode and gains are preview fields, not approved physical settings'])
        (source/'report.json').write_text(json.dumps(report,indent=2)+'\n'); print(json.dumps(report,indent=2))
        return 0 if report['passed'] else 1
    from lowcmd_preview import binary,preview,PINNED,INCLUDE,SDK
    from record_body_lifecycle import verify_saved
    integrity=verify_saved(args.run)
    journal=[json.loads(line) for line in (args.run/'commands.jsonl').read_bytes().splitlines()]
    state=json.loads(args.state_report.read_bytes()); machine=state['monitor']['mode_machine']
    if (state['robot_commands_sent'] is not False or state['scope']!='record_only_local_monitor'
            or type(machine) is not int or not 0<=machine<=255): raise ValueError('Expected read-only state report')
    parent=source.parent/'artifacts/lowcmd-abi'; parent.mkdir(parents=True,exist_ok=True)
    staging=Path(tempfile.mkdtemp(prefix='stage-',dir=parent)); stage=staging/'data-only'; stage.mkdir()
    with binary() as executable:
        results=preview(journal,fixture_machine_id=machine,executable=executable)
        for name in ('LowCmd_data.hpp','MotorCmd_data.hpp'):
            (stage/name).write_bytes((executable.parent/name).read_bytes())
    # Export the exact pinned CRC header with SDK license; adapt include path
    # only so G1 compilation cannot import DDS registration or live clients.
    (stage/'crc.h').write_bytes((INCLUDE/'unitree/dds_wrapper/common/crc.h').read_bytes())
    (stage/'LICENSE.unitree').write_bytes((SDK/'LICENSE').read_bytes())
    code=(source/'lowcmd_preview.cpp').read_text().replace('"unitree/dds_wrapper/common/crc.h"','"crc.h"')
    (stage/'lowcmd_preview.cpp').write_text(code)
    (stage/'x86_64-memory.hex').write_text(''.join(r['native_memory_hex']+'\n' for r in results))
    lines=[' '.join(map(str,[machine,*[row[key][i] for i in range(29) for key in ('q','dq','tau','kp','kd')]])) for row in journal]
    (stage/'input.txt').write_text('\n'.join(lines)+'\n')
    (stage/'expected.json').write_text(json.dumps(dict(record_count=len(results),mode_machine=machine,
        source_state_report_sha256=digest(args.state_report.read_bytes()),
        source_lifecycle_report_sha256=digest((args.run/'report.json').read_bytes()),
        input_integrity=integrity,python_crc_verified=True,pinned_sdk_source_sha256=PINNED),indent=2)+'\n')
    dest=directory(['ssh',*GPU_OPTS,GPU],GPU_ROOT+'/artifacts/lowcmd-abi-')
    run(['scp',*GPU_OPTS,'-r',str(source/'probe_g1_lowcmd_abi.py'),str(source/'run_state_shadow.py'),
        str(stage),str(source.parent/'assets/network/g1-runtime-access.json'),GPU+':'+dest+'/'])
    result=subprocess.run(['ssh',*GPU_OPTS,GPU,'python3 -I '+shlex.quote(dest+'/probe_g1_lowcmd_abi.py')+' --on-gpu'],timeout=60)
    run(['scp',*GPU_OPTS,'-r',GPU+':'+dest,str(parent)+'/'])
    print('Local ABI evidence: '+str(parent/Path(dest).name))
    return result.returncode


if __name__=='__main__': raise SystemExit(main())
