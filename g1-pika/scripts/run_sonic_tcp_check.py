"""Saved actions -> IK -> SONIC GPU file diagnostic in one command, no G1."""
import argparse
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--service-check', action='store_true')
    args = parser.parse_args()
    source = Path(__file__).resolve().parent
    parent = source.parent/'artifacts/sonic-tcp'
    parent.mkdir(parents=True, exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix='run-', dir=parent))/'prepared.json'
    subprocess.run([sys.executable, '-I', str(source/'prepare_sonic_tcp_pipeline.py'),
                    '--input', str(args.input.resolve()), '--output', str(output),
                    '--urdf', str(source.parent/'artifacts/models/g1_pika_closed.urdf')], check=True, timeout=120)
    return subprocess.run([sys.executable, '-I', str(source/'run_sonic_replay.py'),
                           '--prepared', str(output)] +
                           (['--config',str(args.config.resolve())] if args.config else []) +
                           (['--service-check'] if args.service_check else []), timeout=240).returncode


if __name__ == '__main__': raise SystemExit(main())
