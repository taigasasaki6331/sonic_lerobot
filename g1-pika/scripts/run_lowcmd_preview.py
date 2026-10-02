"""Preview an existing verified lifecycle journal as pinned native LowCmd memory."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parent))
from record_body_lifecycle import verify_saved
from sonic_startup_ablation import ROOT, sha, save
from sonic_process import strict_message
from lowcmd_preview import binary, preview, PINNED


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True,help='Existing body-lifecycle record directory')
    args=parser.parse_args(); integrity=verify_saved(args.run)
    rows=[strict_message(line) for line in (args.run/'commands.jsonl').read_bytes().splitlines()]
    with binary() as executable: results=preview(rows,fixture_machine_id=0,executable=executable)
    parent=ROOT/'artifacts/lowcmd-preview'; parent.mkdir(parents=True,exist_ok=True)
    local=Path(tempfile.mkdtemp(prefix='run-',dir=parent))
    with (local/'native-memory-preview.jsonl').open('x') as file:
        for result in results: file.write(json.dumps(result,allow_nan=False,separators=(',',':'))+'\n')
    report=dict(scope='pinned_Unitree_native_memory_and_CRC_preview_NOT_DDS_CDR_or_robot_control',
        record_count=len(results),source_lifecycle_report_sha256=sha(args.run/'report.json'),
        source_command_journal_sha256=sha(args.run/'commands.jsonl'),input_integrity=integrity,
        pinned_sdk_source_sha256=PINNED,source_code_sha256={name:sha(Path(__file__).with_name(name))
            for name in ('run_lowcmd_preview.py','lowcmd_preview.py','lowcmd_preview.cpp')},
        packet_size_bytes=1004,controlled_motor_slots=29,unused_disabled_motor_slots=6,
        crc_independently_verified=True,mode_machine_source='fixture_zero_NOT_detected_robot_id',
        packet_memory_file_sha256=sha(local/'native-memory-preview.jsonl'),
        hardware_ready=False,robot_commands_sent=False,g1_connected=False,
        limitations=['Data classes only: no DDS serializer/publisher or MotionSwitcher',
            'Native memory preview is not a DDS wire-format file', 'No G1 aarch64 ABI or firmware validation',
            'Motor mode=1 and quoted upstream gains are preview fields, not motion approval or certified safe gains',
            'Physical stop, ownership and support remain unvalidated'])
    save(local/'report.json',report); print(json.dumps(report,indent=2)); print('Saved:',local)
    return 0


if __name__=='__main__': raise SystemExit(main())
