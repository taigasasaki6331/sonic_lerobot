"""Freeze episode-disjoint valid49 split and explicit label exclusions; no training."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
from dataset_contract import inspect_episode
from dataset_manifest import inventory


def main():
    import pyarrow.parquet as pq
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,required=True)
    parser.add_argument('--file-manifest',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    if inventory(args.dataset) != json.loads(args.file_manifest.read_text())['files']:
        raise ValueError('Dataset differs from transfer manifest')
    info = json.loads((args.dataset/'meta/info.json').read_text())
    if (info['total_episodes'],info['total_frames'],info['fps']) != (49,10881,30):
        raise ValueError('Expected valid49 dataset')
    rows = pq.read_table(args.dataset/'data',columns=['episode_index','frame_index',
        'observation.state','action']).to_pylist()
    if len(rows) != 10881 or {r['episode_index'] for r in rows} != set(range(49)):
        raise ValueError('Unexpected data rows')
    split = {'train':list(range(39)),'validation':list(range(39,44)),'test':list(range(44,49))}
    selection = []
    for episode in range(49):
        values = sorted([r for r in rows if r['episode_index']==episode],key=lambda r:r['frame_index'])
        if [r['frame_index'] for r in values] != list(range(len(values))):
            raise ValueError('Noncontiguous frames')
        check = inspect_episode(values,'columns')
        if not check['state_contract_passed']:
            raise ValueError('Invalid current-TCP state contract')
        excluded = check['gripper_h1_mismatch_frames']
        selection.append({'episode':episode,'split':next(k for k,v in split.items() if episode in v),
            'frames':len(values),'selected':[i for i in range(len(values)) if i not in excluded],
            'excluded_gripper_mismatch':excluded})
    report = {'format':1,'purpose':'candidate_RGB_h1_training_split_not_task_validation',
        'file_manifest_sha256':hashlib.sha256(args.file_manifest.read_bytes()).hexdigest(),
        'rotation_layout':'columns','splits':split,'selection':selection,
        'counts':{name:sum(len(s['selected']) for s in selection if s['split']==name) for name in split},
        'excluded_count':sum(len(s['excluded_gripper_mismatch']) for s in selection),
        'exclusion_rule':'abs(action[t].width-state[min(t+1,last)].width)>1e-6; no label repair',
        'normalization_rule':'compute from train only; never validation/test',
        'test_policy':'do not use test episodes for model/step/hyperparameter selection',
        'session_disjointness_verified':False,
        'limitation':'episode-disjoint only; same task/session/near-duplicate leakage not ruled out'}
    with args.output.open('x') as stream:
        json.dump(report,stream,indent=2)
        stream.write('\n')
    print(json.dumps({k:v for k,v in report.items() if k!='selection'},indent=2))


if __name__ == '__main__':
    main()
