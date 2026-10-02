"""Local read-only inventory; never starts a controller, camera, SSH or DDS."""
import argparse
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess


def trt_version(header):
    definitions = dict(re.findall(r'^\s*#define\s+(\w+)\s+(\w+)\b', header, re.M))
    values = {}
    for key in ('MAJOR', 'MINOR', 'PATCH', 'BUILD'):
        value = definitions.get('NV_TENSORRT_' + key, '')
        seen = set()
        while value in definitions and value not in seen:
            seen.add(value)
            value = definitions[value]
        if not value.isdecimal():
            return None
        values[key] = value
    return '.'.join(values.values())


def inspect(root):
    vendor = root / 'vendor/GR00T-WholeBodyControl'
    lock = json.loads((root / 'sources.lock.json').read_text())['wbc']
    result = subprocess.run(['git', '-C', str(vendor), 'rev-parse', 'HEAD'],
                            capture_output=True, text=True, timeout=5)
    headers = [Path('/usr/include/x86_64-linux-gnu/NvInferVersion.h'),
               Path('/usr/include/aarch64-linux-gnu/NvInferVersion.h')]
    if os.environ.get('TENSORRT_ROOT'):
        headers.insert(0, Path(os.environ['TENSORRT_ROOT']) / 'include/NvInferVersion.h')
    versions = [{"header": str(p), "version": trt_version(p.read_text())}
                for p in headers if p.is_file()]
    source_paths = ['gear_sonic/utils/teleop/zmq/zmq_planner_sender.py',
                    'gear_sonic_deploy/CMakeLists.txt', 'gear_sonic_deploy/src']
    return dict(scope='local_read_only_inventory_not_readiness',
                robot_commands_sent=False, network_connections_opened=False,
                machine=platform.machine(), hostname=platform.node(),
                upstream_commit=result.stdout.strip() if result.returncode == 0 else None,
                upstream_commit_matches=result.returncode == 0 and result.stdout.strip() == lock['commit'],
                sonic_sources={p: (vendor/p).exists() for p in source_paths},
                tools={p: shutil.which(p) for p in ['git', 'cmake', 'g++', 'nvcc', 'nvidia-smi', 'just']},
                tensorrt_headers=versions,
                cuda_nvcc_candidates=[str(p) for p in Path('/usr/local').glob('cuda*/bin/nvcc') if p.is_file()],
                offline_python_exists=(root/'.venv/bin/python').is_file(),
                limitations=['No GPU inference, model availability, binary build or hardware readiness checked.',
                             'TensorRT header presence does not verify runtime libraries.',
                             'SONIC reference adapter and full environment are not yet complete.'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(inspect(args.root), indent=2))
