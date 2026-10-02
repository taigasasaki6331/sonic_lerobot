"""Bounded artifact recovery; validate tar entries, never trust archive paths."""
import hashlib
from pathlib import Path
import shlex
import subprocess
import tarfile


def extract_outputs(archive,target):
    root=Path(target).resolve(); root.mkdir(parents=True,exist_ok=True)
    with tarfile.open(archive,'r:gz') as source:
        members=source.getmembers()
        if len(members)>10000 or sum(m.size for m in members)>2_000_000_000: raise ValueError('Artifact archive exceeds bounds')
        seen=set()
        # Validate the entire member list before writing any member.
        for member in members:
            path=Path(member.name)
            if path.is_absolute() or '..' in path.parts or not (member.isfile() or member.isdir()):
                raise ValueError('Unsafe artifact archive member')
            destination=root/path
            if not destination.resolve().is_relative_to(root) or destination.is_symlink(): raise ValueError('Artifact escapes destination')
            if member.size>100_000_000 or str(path) in seen: raise ValueError('Duplicate or oversized artifact member')
            seen.add(str(path))
        for member in members:
            destination=root/member.name
            if member.isdir(): destination.mkdir(parents=True,exist_ok=True); continue
            destination.parent.mkdir(parents=True,exist_ok=True)
            with source.extractfile(member) as file: blob=file.read()
            if destination.exists():
                if hashlib.sha256(destination.read_bytes()).digest()!=hashlib.sha256(blob).digest():
                    raise ValueError('Recovered artifact differs from existing file: '+member.name)
            else:
                with destination.open('xb') as file: file.write(blob)


def recover(ssh,options,gpu,remote,local):
    local=Path(local); archive=local/'outputs.tar.gz'
    try:
        command=shlex.join(['tar','-czf',remote+'/outputs.tar.gz','-C',remote+'/outputs','.'])
        with (local/'recovery.log').open('w') as log:
            packed=subprocess.run([*ssh,command],stdout=log,stderr=subprocess.STDOUT,timeout=30)
            if packed.returncode: return packed.returncode
            copied=subprocess.run(['scp',*options,gpu+':'+remote+'/outputs.tar.gz',str(archive)],
                                  stdout=log,stderr=subprocess.STDOUT,timeout=30)
            if copied.returncode: return copied.returncode
        extract_outputs(archive,local/'outputs')
        return 0
    except subprocess.TimeoutExpired: return 124
    except (ValueError,OSError,tarfile.TarError) as exc:
        with (local/'recovery.log').open('a') as log: log.write(type(exc).__name__+': '+str(exc)+'\n')
        return 1
