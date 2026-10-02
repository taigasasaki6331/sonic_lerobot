"""Isolated LeRobot CPU inference on recorded observations; JSON lines over local pipes."""
import argparse
from contextlib import redirect_stdout
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--episode',type=int,default=39)
    parser.add_argument('--frames',type=int,default=90)
    args=parser.parse_args()
    if args.episode not in range(39,44) or not 1<=args.frames<=300:
        parser.error('Use validation episode 39..43 and 1..300 frames')
    from train_rgb_smoke import runtime,rgb_input,DATASET
    from gripper_codec import decode_action
    with redirect_stdout(sys.stderr):
        commit=runtime()
        import torch
        from lerobot.policies.act.configuration_act import ACTConfig
        from lerobot.policies.act.modeling_act import ACTPolicy
        from lerobot.policies.factory import make_pre_post_processors
        from lerobot.datasets.lerobot_dataset import LeRobotDataset
        torch.set_num_threads(4)
        torch.manual_seed(42)
        checkpoint=args.run/'pretrained_model'
        codec=json.loads((checkpoint/'action_codec.json').read_text())
        if hashlib.sha256((ROOT/'scripts/gripper_codec.py').read_bytes()).hexdigest()!=codec['codec_script_sha256']:
            raise ValueError('Codec implementation differs from checkpoint')
        cfg=ACTConfig.from_pretrained(str(checkpoint),local_files_only=True)
        if cfg.chunk_size!=1 or cfg.n_action_steps!=1:
            raise ValueError('Only h1 single-action policy supported')
        cfg.device='cpu'; cfg.pretrained_backbone_weights=None
        policy=ACTPolicy.from_pretrained(str(checkpoint),config=cfg,local_files_only=True,strict=True).eval()
        pre,post=make_pre_post_processors(cfg,pretrained_path=str(checkpoint),
            preprocessor_overrides={'device_processor':{'device':'cpu'}},
            postprocessor_overrides={'device_processor':{'device':'cpu'}})
        ds=LeRobotDataset('data',root=DATASET,episodes=[args.episode],return_uint8=True,video_backend='pyav')
        if args.frames>len(ds) or ds.fps!=30:
            raise ValueError('Episode length/fps differs')
    print(json.dumps({'ready':True,'fps':30,'frames':args.frames,'episode':args.episode,
        'run':str(args.run),'codec':codec['mode'],'lerobot_commit':commit,
        'model_sha256':hashlib.sha256((checkpoint/'model.safetensors').read_bytes()).hexdigest(),
        'observation_source':'recorded_RGB_and_recorded_state_not_simulated_camera',
        'device':'cpu','hardware_communication':False}),flush=True)
    expected=0
    for line in sys.stdin:
        request=json.loads(line)
        if request.get('stop'): break
        seq=request['seq']
        if type(seq)!=int or seq!=expected or seq>=args.frames:
            raise ValueError('Unexpected request sequence')
        start=time.perf_counter()
        with redirect_stdout(sys.stderr),torch.inference_mode():
            item=ds[seq]
            if int(item['frame_index'])!=seq or int(item['episode_index'])!=args.episode:
                raise ValueError('Recorded frame mismatch')
            policy.reset()
            raw=post(policy.select_action(pre(rgb_input(item)))).reshape(10).cpu()
            action=decode_action(raw,item['observation.state'].cpu(),codec['mode'])
        print(json.dumps({'seq':seq,'timestamp':float(item['timestamp']),
            'action':action.tolist(),'recorded_gripper_m':float(item['observation.state'][9]),
            'inference_and_decode_ms':(time.perf_counter()-start)*1000},allow_nan=False),flush=True)
        expected+=1


if __name__=='__main__':
    main()
