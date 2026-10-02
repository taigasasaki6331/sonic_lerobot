"""Strict development configuration. Hardware output cannot be enabled here."""
import json
import math
from pathlib import Path
import re

DEFAULT = Path(__file__).resolve().parents[1]/'config/development.json'
FIELDS = {'schema_version', 'mode', 'hardware_output_enabled', 'gpu_host', 'ssh_identity',
          'gpu_root', 'ik_deployment', 'sonic_build', 'sonic_models', 'cuda_root', 'tensorrt_root', 'diagnostic_deadlines'}


def validate(config):
    if set(config) != FIELDS or type(config['schema_version']) is not int or config['schema_version'] != 1:
        raise ValueError('Unknown configuration schema or fields')
    if config['mode'] != 'record_only' or config['hardware_output_enabled'] is not False:
        raise ValueError('Only record_only with hardware output disabled is supported')
    if not re.fullmatch(r'[a-zA-Z0-9_.-]+@[a-zA-Z0-9][a-zA-Z0-9.-]*', config['gpu_host']):
        raise ValueError('Invalid GPU SSH host')
    for key in ('ssh_identity','gpu_root','ik_deployment','sonic_build','sonic_models','cuda_root','tensorrt_root'):
        value = config[key]
        if not isinstance(value, str) or not value.startswith('/') or any(c in value for c in ('\n','\r','\x00')):
            raise ValueError('Expected absolute path: '+key)
        if '..' in Path(value).parts or value == '/': raise ValueError('Unsafe path: '+key)
    limits = config['diagnostic_deadlines']
    if set(limits) != {'max_source_age_s','max_roundtrip_s','max_tick_gap_s'}:
        raise ValueError('Unexpected deadline fields')
    for value in limits.values():
        if type(value) not in (float,int) or not math.isfinite(value) or not 0 < value <= 5:
            raise ValueError('Invalid diagnostic deadline')
    return config


def load(path=DEFAULT):
    return validate(json.loads(Path(path).read_text()))


def ssh_options(config):
    return ['-i', config['ssh_identity'], '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes',
            '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=5',
            '-o', 'ServerAliveInterval=5', '-o', 'ServerAliveCountMax=2']
