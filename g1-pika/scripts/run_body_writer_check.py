"""Local native writer regression evidence; never links or calls Unitree SDK."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parent))
from check_body_writer import compile_and_run


def main():
    source=Path(__file__).resolve().parent
    parent=source.parent/'artifacts/body-writer'; parent.mkdir(exist_ok=True)
    run=Path(tempfile.mkdtemp(prefix='run-',dir=parent))
    report=dict(passed=False,robot_commands_sent=False,physical_stop_confirmed=False,
        scope='native_500Hz_design_FAKE_IO_not_real_time_or_hardware_validation',
        g1_accessed=False,sdk_linked_or_started=False)
    try:
        report['fake_result']=compile_and_run(run/'fake-writer-check')
        report['passed']=True
    except Exception as exc:
        report['error']=type(exc).__name__+': '+str(exc)
    report['source_sha256']={name:hashlib.sha256((source/name).read_bytes()).hexdigest()
        for name in ('body_writer.hpp','body_io_adapter.hpp','check_body_writer.cpp','check_body_writer.py')}
    (run/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2)); print('Saved evidence: '+str(run))
    return 0 if report['passed'] else 1


if __name__=='__main__': raise SystemExit(main())
