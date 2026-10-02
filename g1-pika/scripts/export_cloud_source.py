"""Snapshot CURRENT source, including untracked code; never upload or alter Git.

Allowlisted source/assets + a small pinned upstream source subset. Excludes Git
history, SSH files, local environments, weights, datasets, camera frames, logs,
compiled drivers and binaries. Output is a new directory, never an overwrite.
"""
import argparse
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TEXT = {'.py', '.sh', '.c', '.cpp', '.h', '.hpp', '.idl', '.json', '.md',
        '.txt', '.toml', '.xml', '.rules', '.sha256', '.cmake', '.yaml', '.yml'}
NAMED = {'Makefile', 'CMakeLists.txt', 'LICENSE', 'NOTICE', 'REPOSITORY_LICENSE'}
UPSTREAM = 'vendor/GR00T-WholeBodyControl'
SDK = UPSTREAM + '/gear_sonic_deploy/thirdparty/unitree_sdk2'
VENDOR_DIRS = (UPSTREAM + '/gear_sonic_deploy/src/g1/g1_deploy_onnx_ref',
               UPSTREAM + '/gear_sonic/utils/teleop/zmq',
               UPSTREAM + '/legal', SDK + '/include', SDK + '/thirdparty/include')
ROOT_FILES = ('AGENTS.md', 'README.md', 'Makefile', '.gitignore', '.gitattributes', 'sources.lock.json')
URDF = 'artifacts/models/g1_pika_closed.urdf'
# Print only paths on rejection, never matched values or secret material.
SECRET = re.compile(rb'-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----(?:\s|\\n)+[A-Za-z0-9+/=]{40,}|'
                    rb'\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,}|sk-[A-Za-z0-9_-]{30,})')


def allowed(path):
    return (path.suffix.lower() in TEXT or path.name in NAMED or
            path.name.startswith('LICENSE.') or path.suffix.lower() == '.stl')


def verify(directory):
    directory = Path(directory).resolve()
    manifest = json.loads((directory / 'cloud-source-manifest.json').read_bytes())
    if manifest.get('scope') != 'CPU_cloud_source_snapshot_NOT_full_runtime':
        raise ValueError('Unsupported manifest')
    for name, record in manifest['files'].items():
        path = directory / name
        if path.is_symlink() or not path.resolve().is_relative_to(directory):
            raise ValueError('Unsafe manifest path')
        raw = path.read_bytes()
        if len(raw) != record['size_bytes'] or hashlib.sha256(raw).hexdigest() != record['sha256']:
            raise ValueError('Snapshot differs: ' + name)
    return dict(passed=True, files=len(manifest['files']), scope='file_integrity_only_not_signature', uploaded=False)


def selected(root):
    files = {root / name for name in ROOT_FILES}
    files.update(root.glob('requirements-*.in'))
    files.update(root.glob('requirements-*.lock'))
    for directory in ('scripts', 'config', 'docs', 'assets/pika', 'assets/drivers', 'assets/datasets'):
        files.update(p for p in (root / directory).rglob('*')
                     if p.is_file() and allowed(p) and '__pycache__' not in p.parts)
    # Device config is useful provenance, but known_hosts/SSH files are not exported.
    files.update((root / 'assets/network').glob('*.json'))
    files.add(root / URDF)
    files.update(root / name for name in (UPSTREAM + '/LICENSE', SDK + '/LICENSE', 'vendor/lerobot/LICENSE'))
    for directory in VENDOR_DIRS:
        files.update(p for p in (root / directory).rglob('*')
                     if p.is_file() and allowed(p) and '__pycache__' not in p.parts)
    return sorted(files)


def public_copy(blobs, sources):
    """Redact deployment identities in first-party COPIES; upstream pins stay exact."""
    text = {name: raw.decode('utf-8') for name, raw in blobs.items()
            if not name.startswith('vendor/') and not name.endswith('.STL') and not name.endswith('.stl')}
    private_networks = [ipaddress.ip_network(n) for n in ('192.0.2.1/8', '192.0.2.5/12', '192.0.2.6/16')]
    ipv4 = re.compile(r'(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])')
    addresses = set()
    for value in text.values():
        for match in ipv4.finditer(value):
            try: address = ipaddress.ip_address(match.group())
            except ValueError: continue
            if any(address in network for network in private_networks): addresses.add(str(address))
    if len(addresses) > 250: raise ValueError('Too many deployment addresses for documentation subnet')
    replacements = {value: '192.0.2.' + str(i + 1) for i, value in enumerate(sorted(addresses))}
    access = json.loads(blobs['assets/network/g1-runtime-access.json'])
    fingerprint = access.get('g1_host_ed25519_sha256', '')
    serials = set(re.findall(r'(?i)serial\s+([0-9]{10,})', access.get('camera_pair_provenance', '')))
    original_urdf_sha = hashlib.sha256(blobs[URDF]).hexdigest()
    changed = []
    for name, value in text.items():
        old = value
        if name == URDF:
            # URDF lives in artifacts/models. Only mesh filename paths change;
            # joint/inertial/collision parameters remain the original values.
            value = value.replace(str(ROOT) + '/', '../../')
        value = ipv4.sub(lambda m: replacements.get(m.group(), m.group()), value)
        value = value.replace('/home/developer/workspaces/', '/home/developer/workspaces/')
        value = value.replace('/home/developer/', '/home/developer/').replace('/home/gpu-user/', '/home/gpu-user/')
        value = re.sub(r'SHA256:[A-Za-z0-9+/=]{20,}', 'SHA256:PUBLIC_EXAMPLE_NOT_VERIFIED', value)
        if fingerprint: value = value.replace(fingerprint, 'PUBLIC_EXAMPLE_NOT_VERIFIED')
        for serial in serials: value = value.replace(serial, 'EXAMPLE_DEVICE_SERIAL')
        # These are example placeholders, never the owner's existing SSH settings.
        value = value.replace('EXAMPLE_RUNTIME_KEY', 'EXAMPLE_RUNTIME_KEY')
        value = value.replace('EXAMPLE_GPU_KEY', 'EXAMPLE_GPU_KEY')
        if name == 'assets/network/g1-runtime-access.json':
            config = json.loads(value); config['ssh_verified'] = False
            config['scope'] = 'PUBLIC_EXAMPLE_NOT_a_verified_deployment'
            config['g1_hostname'] = 'example-g1-host'
            config['camera_pair_provenance'] = 'EXAMPLE ONLY; USB mapping and cameras must be verified locally'
            value = json.dumps(config, indent=2) + '\n'
        if value != old: changed.append(name)
        blobs[name] = value.encode()
    public_sha = hashlib.sha256(blobs[URDF]).hexdigest()
    # Keep provenance of the original pin, distinguish the path-only derivative.
    sources['sonic']['ik_reuse']['urdf_sha256'] = public_sha
    sources['sonic']['ik_reuse']['original_local_urdf_sha256'] = original_urdf_sha
    sources['sonic']['ik_reuse']['public_derivative'] = 'mesh filenames made relative; model parameters unchanged'
    blobs['sources.lock.json'] = (json.dumps(sources, indent=2) + '\n').encode()
    receiver_manifest = 'scripts/state_receiver/generated/manifest.json'
    generated = json.loads(blobs[receiver_manifest])
    for name in generated['sha256']:
        generated['sha256'][name] = hashlib.sha256(blobs['scripts/state_receiver/' + name]).hexdigest()
    generated['public_derivative'] = 'generated source filename comments redacted; wire layout not regenerated'
    blobs[receiver_manifest] = (json.dumps(generated, indent=2) + '\n').encode()
    notice = ('\n> 公開用コピー：ネットワーク値・機器識別子・ローカルパスは例へ置換。'
              '保存試験結果は原本の記録で、例設定で実機試験した証拠ではありません。'
              'クラウドから機器接続・実機指令を行わないでください。\n\n')
    for name in ('README.md', 'AGENTS.md', 'docs/HANDOFF.md', 'docs/CLOUD_HANDOFF.md'):
        lines = blobs[name].decode().split('\n', 1)
        blobs[name] = (lines[0] + '\n' + notice + lines[1]).encode()
    return dict(redacted_files=changed, urdf_original_sha256=original_urdf_sha,
                urdf_public_sha256=public_sha, note='Deployment examples are not commissioned hardware settings')


def export(root, output, *, public=False):
    root = root.resolve()
    output = output.absolute()
    if output.exists() or output.is_symlink(): raise ValueError('Output exists; nothing overwritten')
    sources = json.loads((root / 'sources.lock.json').read_bytes())
    upstream = root / UPSTREAM
    head = subprocess.check_output(['git', '-C', str(upstream), 'rev-parse', 'HEAD'], text=True).strip()
    if head != sources['sonic']['commit']: raise ValueError('Unexpected upstream revision')
    files = selected(root)
    blobs = {}
    for path in files:
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError('Symlink/path escape rejected: ' + str(path.relative_to(root)))
        raw = path.read_bytes()
        if len(raw) > 2_000_000: raise ValueError('Oversized source: ' + str(path.relative_to(root)))
        if SECRET.search(raw): raise ValueError('Potential credential rejected: ' + str(path.relative_to(root)))
        if path.suffix.lower() != '.stl':
            raw.decode('utf-8')  # Reject disguised binary files.
        blobs[path.relative_to(root).as_posix()] = raw
    if hashlib.sha256(blobs[URDF]).hexdigest() != sources['sonic']['ik_reuse']['urdf_sha256']:
        raise ValueError('Pinned URDF changed')
    publication = public_copy(blobs, sources) if public else None
    # These ignores apply ONLY to the isolated snapshot, never the user's worktree.
    # Exported vendor headers/source and the single URDF must survive Git publication.
    blobs['.gitignore'] += (b'\n.venv-cloud/\n!/vendor/\n!/vendor/**\n'
        b'!/artifacts/\n/artifacts/*\n!/artifacts/models/\n/artifacts/models/*\n'
        b'!/artifacts/models/g1_pika_closed.urdf\n*.so\n*.a\n*.o\n*.ko\n'
        b'*.onnx\n*.engine\n*.safetensors\n*.pt\n*.pth\n*.mp4\n.env\n.env.*\n'
        b'__pycache__/\n*.pyc\n.cache/\n')
    blobs['.gitattributes'] += b'\n* -text\nvendor/** -whitespace\nscripts/state_receiver/generated/** -whitespace\n'
    manifest = dict(schema_version=1, scope='CPU_cloud_source_snapshot_NOT_full_runtime',
        robot_commands_sent=False, uploaded=False,
        source_git_head=subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip(),
        includes_uncommitted_worktree=True, upstream_commit=head, upstream_source_subset=True,
        public_copy=public, publication=publication,
        excluded=['Git history', 'credentials/known_hosts', 'datasets', 'weights', 'camera frames',
                  'logs', 'virtual environments', 'compiled binaries', 'GPU libraries'],
        files={name:dict(size_bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
               for name, raw in sorted(blobs.items())})
    blobs['cloud-source-manifest.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='g1-cloud-staging-', dir=output.parent) as temporary:
        staging = Path(temporary) / 'source'; staging.mkdir()
        for name, raw in blobs.items():
            destination = staging / name; destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
        # Atomic same-filesystem publish; a concurrent destination is not replaced.
        if output.exists() or output.is_symlink(): raise ValueError('Output appeared; nothing overwritten')
        staging.rename(output)
    return dict(output=str(output), files=len(blobs), bytes=sum(map(len, blobs.values())), uploaded=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--output', type=Path)
    action.add_argument('--verify', type=Path)
    parser.add_argument('--public', action='store_true', help='Redact deployment identities in the new copy only')
    args = parser.parse_args()
    print(json.dumps(verify(args.verify) if args.verify else export(ROOT, args.output, public=args.public), indent=2))


if __name__ == '__main__': main()
