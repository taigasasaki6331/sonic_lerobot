"""Strict input-only online configuration; no hardware output switch."""
from pathlib import Path
import re
from sonic_process import strict_message


def load_online(path):
    config=strict_message(Path(path).read_text())
    if set(config)!={'schema_version','mode','hardware_output_enabled','seconds','camera_endpoint','body_endpoint','act_model_sha256'}:
        raise ValueError('Unexpected online configuration fields')
    if type(config['schema_version']) is not int or config['schema_version']!=1: raise ValueError('Online schema')
    if config['mode']!='record_only' or config['hardware_output_enabled'] is not False: raise ValueError('Record-only required')
    if type(config['seconds']) is not int or not 1<=config['seconds']<=30: raise ValueError('Duration 1..30 seconds required')
    if config['camera_endpoint']!='tcp://192.0.2.11:6158' or config['body_endpoint']!='tcp://192.0.2.11:6159':
        raise ValueError('Online source endpoints must match the fixed G1 isolated-link deployment')
    if not re.fullmatch('[0-9a-f]{64}',config['act_model_sha256']): raise ValueError('Checkpoint SHA256 required')
    return config
