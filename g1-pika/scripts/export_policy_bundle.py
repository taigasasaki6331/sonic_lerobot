"""Export a verified diagnostic ACT bundle, never SSH keys/datasets/other logs.

Not an environment installer or hardware launcher. Redistribution permission
must be checked by the sharing party; a hash is not a license grant.
"""
import argparse
import gzip
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parent))
from policy_bundle import read_json, verify, contained, sha

EXTRAS = ('scripts/policy_bundle.py', 'scripts/probe_gpu_images.py',
          'sources.lock.json', 'vendor/lerobot/LICENSE')
NOTICE = """# Diagnostic ACT bundle

This archive contains the existing diagnostic candidate, NOT an accepted task
policy, robot control environment or hardware launcher. No datasets or SSH
credentials are included. Check redistribution rights before sharing.

After extracting into a NEW directory, run from that directory:

    python3 -I scripts/policy_bundle.py verify

Python >=3.10 is sufficient for the file-only check. GPU inference also requires
Python 3.12.13, requirements-gpu.lock, CUDA-compatible PyTorch, and the pinned
LeRobot checkout at vendor/lerobot (see sources.lock.json; source not bundled).
The included LeRobot LICENSE is a source-license reference, not a license grant
for the training data/model. Full IK/SONIC/G1 setup is in the project README.

Keep config/policy-bundle.json as a unit with ALL seven checkpoint files. Load
the saved pre/postprocessors and decode the width residual using the measured
width after inverse normalization. Both camera inputs are RGB, not depth.
No action clipping or claim of gripper calibration/task quality is provided.

bundle-export.json records every packaged input's size/hash. These are integrity
records, NOT digital signatures. Model quality and physical stop/robot control
remain separately unverified. This export does not consume the held-out test set.
"""


def export(root, manifest, output):
    root = Path(root).resolve()
    output = Path(output)
    if not str(output).endswith('.tar.gz'): raise ValueError('Output must end in .tar.gz')
    if output.exists() or output.is_symlink(): raise FileExistsError('Refusing to overwrite: ' + str(output))
    if not output.parent.is_dir(): raise ValueError('Output parent must already exist')
    verification = verify(root, manifest)
    data = read_json(manifest)
    names = sorted(set([data['checkpoint'] + '/' + name for name in data['files']]
                       + list(data['runtime_files']) + list(EXTRAS)))
    # Copy a strict allowlist, never a recursive repository/artifacts snapshot.
    with tempfile.TemporaryDirectory(prefix='g1-pika-bundle-', dir=output.parent) as directory:
        stage = Path(directory) / 'stage'
        stage.mkdir()
        for name in names:
            source = contained(root, name)
            if not source.is_file(): raise ValueError('Export input missing: ' + name)
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        target = stage / 'config/policy-bundle.json'
        target.parent.mkdir(parents=True)
        shutil.copyfile(manifest, target)
        # Catch changes during the copy and verify the copy, not just originals.
        staged = verify(stage, target)
        if staged != verification: raise ValueError('Bundle changed during export')
        payload = names + ['config/policy-bundle.json']
        records = {name: {'size_bytes': (stage / name).stat().st_size,
                          'sha256': sha(stage / name)} for name in payload}
        metadata = {'schema_version': 1, 'scope': 'diagnostic_policy_bundle_only',
                    'hardware_ready': False, 'robot_commands_sent': False,
                    'contains_raw_dataset': False, 'contains_ssh_credentials': False,
                    'policy_verification': verification, 'files': records}
        generated = {'README.md': NOTICE.encode(),
                     'bundle-export.json': (json.dumps(metadata, indent=2, sort_keys=True) + '\n').encode()}
        archive = Path(directory) / 'bundle.tar.gz'
        with archive.open('xb') as stream, gzip.GzipFile(fileobj=stream, filename='', mode='wb', mtime=0) as zipped:
            with tarfile.open(fileobj=zipped, mode='w', format=tarfile.PAX_FORMAT) as tar:
                for name in sorted(payload + list(generated)):
                    blob = generated[name] if name in generated else (stage / name).read_bytes()
                    info = tarfile.TarInfo(name)
                    info.size = len(blob)
                    info.mode = 0o644
                    info.mtime = 0
                    tar.addfile(info, io.BytesIO(blob))
        archive_hash = sha(archive)
        # Atomic no-clobber publication on the same filesystem, even with a race.
        os.link(archive, output)
    return {'passed': True, 'scope': 'verified_diagnostic_policy_export_only',
            'hardware_ready': False, 'robot_commands_sent': False,
            'output': str(output.resolve()), 'archive_sha256': archive_hash,
            'archive_size_bytes': output.stat().st_size, 'packaged_files': len(payload) + len(generated),
            'model_sha256': verification['model_sha256']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export(args.root, args.manifest or args.root / 'config/policy-bundle.json', args.output), indent=2))


if __name__ == '__main__': main()
