"""Read-only checkpoint/dataset lineage and depth normalization audit."""
import hashlib
from io import BytesIO
import json
import os
import sys
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
from PIL import Image
from safetensors.numpy import load_file

ROOT = Path(__file__).resolve().parents[1]
DATA = Path('/home/developer/workspaces/pika_ws2/datasets')
MODEL = Path('/home/developer/workspaces/pika_ws2/models/zero_relative_50ep_act_h1_v2/pretrained_model')
KEY = 'observation.depths.pikaDepthCamera'


def main():
    stats_path = MODEL / 'policy_preprocessor_step_3_normalizer_processor.safetensors'
    stats = load_file(stats_path)
    candidates = []
    for path in sorted(DATA.glob('*/meta/stats.json')):
        source = json.loads(path.read_text())
        checks = {}
        for feature in ('action', 'observation.state'):
            for stat in ('mean', 'std', 'min', 'max', 'count'):
                key = feature + '.' + stat
                candidate = np.asarray(source[feature][stat], dtype=np.float32)
                checks[key] = bool(np.array_equal(candidate, stats[key]))
        candidates.append({'dataset': path.parent.parent.name,
                           'all_checked_stats_equal_float32': all(checks.values()), 'checks': checks})
    names = ['data_2608261323_g1_zero_relative_h1_final_50ep',
             'data_2608261323_valid49_g1_zero_relative_h1_final_v3']
    datasets, episodes = [], []
    for name in names:
        root = DATA / name
        path = root / 'data/chunk-000/file-000.parquet'
        rows = pq.read_table(path, filters=[('episode_index', '=', 0)],
                             columns=['frame_index', 'observation.state', 'action', KEY]).to_pylist()
        episodes.append(rows)
        image = Image.open(BytesIO(rows[0][KEY]['bytes']))
        native = np.asarray(image, dtype=np.float32)[None]
        rgb = np.asarray(image.convert('RGB'), dtype=np.float32).transpose(2, 0, 1) / 255
        mean, std = stats[KEY + '.mean'], stats[KEY + '.std']
        normalized = (native - mean) / (std + 1e-8)
        info = json.loads((root / 'meta/info.json').read_text())
        datasets.append({'dataset': name, 'depth_metadata': info['features'][KEY],
            'parquet_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'first_depth_encoded_sha256': hashlib.sha256(rows[0][KEY]['bytes']).hexdigest(),
            'first_depth_mode': image.mode, 'native_shape': list(native.shape),
            'native_quantiles': np.quantile(native, [0, .5, .9, .99, 1]).tolist(),
            'normalized_shape': list(normalized.shape),
            'normalized_abs_max': float(np.abs(normalized).max()),
            'probe_pil_rgb_normalized_abs_max': float(np.abs((rgb-mean)/(std+1e-8)).max()),
            'depth_semantics': 'metadata_missing_is_depth_map_and_depth_unit; native_units_not_verified'})
    a, b = episodes
    paired = len(a) == len(b)
    comparison = {}
    for key in ['frame_index', 'action', 'observation.state', KEY]:
        comparison[key] = paired and all(x[key] == y[key] for x, y in zip(a, b))
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['HF_DATASETS_OFFLINE'] = '1'
    os.environ['HF_HOME'] = str(ROOT / '.cache/policy/hf')
    def audit(event, args):
        if event in {'socket.connect', 'socket.bind', 'socket.sendto', 'socket.getaddrinfo'}:
            raise RuntimeError('Network forbidden during input audit')
    sys.addaudithook(audit)
    sys.path.insert(0, str(ROOT / 'vendor/lerobot/src'))
    import torch
    from lerobot.datasets.lerobot_dataset import LeRobotDataset
    current = LeRobotDataset('data', root=DATA/names[1], episodes=[0], return_uint8=True, video_backend='pyav')
    training_flag = LeRobotDataset('data', root=DATA/names[1], episodes=[0], return_uint8=False, video_backend='pyav')
    older = LeRobotDataset('data', root=DATA/names[0], episodes=[0], return_uint8=False, video_backend='pyav')
    reader_checks = []
    for index in (0, 127, 253):
        x, y, z = current[index], training_flag[index], older[index]
        checks = {}
        for key in ['observation.images.pikaDepthCamera', 'observation.images.pikaFisheyeCamera', KEY]:
            value = x[key].float()/255 if x[key].dtype == torch.uint8 else x[key]
            checks[key] = {'uint8_flag_after_conversion_equal': bool(torch.equal(value, y[key])),
                           'older_50ep_value_equal': bool(torch.equal(y[key], z[key]))}
        reader_checks.append({'frame_index': index, 'checks': checks})
    result = {'scope': 'input_contract_audit_not_training_provenance_proof',
        'normalizer_sha256': hashlib.sha256(stats_path.read_bytes()).hexdigest(),
        'checkpoint_depth_mean': stats[KEY+'.mean'].tolist(),
        'checkpoint_depth_std': stats[KEY+'.std'].tolist(),
        'checkpoint_depth_recorded_max': stats[KEY+'.max'].tolist(),
        'candidate_statistics': candidates, 'depth_inputs': datasets,
        'episode0_exact_comparison': comparison,
        'reader_checks': reader_checks,
        'training_code_revision_known': False,
        'pil_rgb_probe_is_verified_training_transform': False,
        'conclusion': 'Native depth and checkpoint image statistics are inconsistent; do not deploy or silently rescale.'}
    output = ROOT / 'artifacts/policy-input-audit.json'
    output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='candidate_statistics'}, indent=2))
    print('Matching stats:', [c['dataset'] for c in candidates if c['all_checked_stats_equal_float32']])


if __name__ == '__main__':
    main()
