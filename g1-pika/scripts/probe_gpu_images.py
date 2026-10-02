"""Snapshot-only GPU inference. Assumed width, no robot/serial/transport output."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from contextlib import redirect_stdout


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--images',type=Path,required=True)
    parser.add_argument('--policy-bundle',type=Path,help='Pinned bundle manifest; default ROOT/config/policy-bundle.json')
    width_group=parser.add_mutually_exclusive_group(required=True)
    width_group.add_argument('--diagnostic-width',type=float)
    width_group.add_argument('--packet-width',action='store_true')
    parser.add_argument('--stream',action='store_true')
    parser.add_argument('--frames',type=int,default=30,help='Bounded stream length, 1..903 (includes diagnostic tail)')
    parser.add_argument('--warmup-steps',type=int,default=0,help='Synthetic GPU warmup before ready; no commands')
    args=parser.parse_args()
    if not 1<=args.frames<=903: parser.error('frames must be 1..903')
    if not 0<=args.warmup_steps<=10: parser.error('warmup steps must be 0..10')
    if args.packet_width and not args.stream: parser.error('Packet width requires stream')
    if args.diagnostic_width is not None and not 0<=args.diagnostic_width<=.1: parser.error('Width must be 0..0.1 m')
    root=args.root.resolve(); folder=args.images.resolve()
    sys.path.insert(0,str(Path(__file__).resolve().parent))
    from policy_bundle import verify, read_json
    bundle_path=args.policy_bundle or root/'config/policy-bundle.json'
    bundle_report=verify(root,bundle_path)
    bundle=read_json(bundle_path)
    checkpoint=root/bundle['checkpoint']
    if sys.version_info[:3]!=(3,12,13): raise RuntimeError('Python 3.12.13 required')
    for line in (root/'requirements-gpu.lock').read_text().splitlines():
        if '==' in line and not line.startswith('#'):
            name,version=line.split('==')
            if importlib.metadata.version(name)!=version: raise RuntimeError('Dependency mismatch: '+name)
    source=root/'vendor/lerobot'
    commit=json.loads((root/'sources.lock.json').read_text())['lerobot']['commit']
    if subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()!=commit:
        raise RuntimeError('LeRobot commit mismatch')
    subprocess.run(['git','-C',str(source),'diff','--exit-code','HEAD'],check=True)
    os.environ.update(HF_HUB_OFFLINE='1',HF_DATASETS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1')
    def audit(event,values):
        if event in {'socket.connect','socket.bind','socket.sendto','socket.getaddrinfo'}:
            raise RuntimeError('Network forbidden inside inference process')
    sys.addaudithook(audit)
    sys.path[:0]=[str(source/'src'),str(root/'scripts')]
    import numpy as np
    import torch
    from PIL import Image
    from train_rgb_smoke import rgb_input
    from gripper_codec import decode_action
    from lerobot.policies.act.configuration_act import ACTConfig
    from lerobot.policies.act.modeling_act import ACTPolicy
    from lerobot.policies.factory import make_pre_post_processors
    if not torch.cuda.is_available(): raise RuntimeError('CUDA required')
    torch.set_num_threads(4); torch.manual_seed(42)
    codec=json.loads((checkpoint/'action_codec.json').read_text())
    if sha(root/'scripts/gripper_codec.py')!=codec['codec_script_sha256']:
        raise RuntimeError('Codec checksum mismatch')
    cfg=ACTConfig.from_pretrained(str(checkpoint),local_files_only=True)
    cfg.device='cuda'; cfg.pretrained_backbone_weights=None
    if cfg.chunk_size!=1 or cfg.n_action_steps!=1: raise RuntimeError('Expected h1 ACT')
    with redirect_stdout(sys.stderr):
        policy=ACTPolicy.from_pretrained(str(checkpoint),config=cfg,local_files_only=True,strict=True).eval()
    pre,post=make_pre_post_processors(cfg,pretrained_path=str(checkpoint),
        preprocessor_overrides={'device_processor':{'device':'cuda'}},
        postprocessor_overrides={'device_processor':{'device':'cuda'}})
    state=torch.tensor([0,0,0,1,0,0,0,1,0,args.diagnostic_width or 0.],dtype=torch.float32)
    if args.stream:
        import base64
        import io
        if args.warmup_steps:
            dummy={'observation.state':state}
            encoded=io.BytesIO()
            Image.fromarray(np.zeros((480,640,3),dtype=np.uint8)).save(encoded,format='JPEG')
            for key in ('pikaDepthCamera','pikaFisheyeCamera'):
                with Image.open(io.BytesIO(encoded.getvalue())) as image:
                    pixels=np.asarray(image.convert('RGB')).copy()
                dummy['observation.images.'+key]=torch.from_numpy(pixels).permute(2,0,1)
            with torch.inference_mode():
                for _ in range(args.warmup_steps):
                    policy.reset(); post(policy.select_action(pre(rgb_input(dummy))))
                torch.cuda.synchronize(); policy.reset()
        print(json.dumps({'ready':True,'model_sha256':sha(checkpoint/'model.safetensors'),
                          'policy_bundle':bundle_report,
                          'lerobot_commit':commit,'assumed_width_m':args.diagnostic_width,
                          'hardware_ready':False,'synthetic_warmup_steps':args.warmup_steps}),flush=True)
        records=[]
        for line in sys.stdin:
            if len(line)>2000000: raise ValueError('Oversized image packet')
            packet=json.loads(line)
            if packet.get('stop'): break
            if type(packet.get('seq')) is not int or packet['seq']!=len(records) or len(records)>=args.frames:
                raise ValueError('Invalid image sequence')
            if args.packet_width:
                g=packet['gripper']
                width=float(g['width_m'])
                if not np.isfinite(width) or not 0<=width<=.1 or not 0<=g['read_age_s']<=.25:
                    raise ValueError('Invalid gripper width/age')
                if g['width_source']!='encoder_with_legacy_linkage_geometry':
                    raise ValueError('Unexpected width source')
                state[9]=width
            item={'observation.state':state}
            for key,name in [('pikaDepthCamera','realsense_rgb'),('pikaFisheyeCamera','fisheye')]:
                blob=base64.b64decode(packet['images'][name]['jpeg'],validate=True)
                with Image.open(io.BytesIO(blob)) as image:
                    if image.size!=(640,480): raise ValueError('Invalid image size')
                    array=np.asarray(image.convert('RGB')).copy()
                item['observation.images.'+key]=torch.from_numpy(array).permute(2,0,1)
            with torch.inference_mode():
                policy.reset(); torch.cuda.synchronize(); start=time.perf_counter()
                raw=post(policy.select_action(pre(rgb_input(item)))).reshape(10).cpu()
                action=decode_action(raw,state,codec['mode']); torch.cuda.synchronize()
            if not torch.isfinite(action).all(): raise ValueError('Nonfinite action')
            record={'seq':packet['seq'],'action':action.tolist(),
                    'inference_ms':(time.perf_counter()-start)*1000,
                    'width_source':'encoder_with_legacy_linkage_geometry' if args.packet_width else 'assumed_not_measured',
                    'observation_width_m':float(state[9]),'assumed_width_m':args.diagnostic_width,
                    'legacy_gripper_range_error':packet['gripper']['legacy_range_error'] if args.packet_width else None,
                    'robot_commands_sent':False}
            records.append(record); print(json.dumps(record,allow_nan=False),flush=True)
        (folder/'stream-inference.json').write_text(json.dumps(records,indent=2)+'\n')
        if len(records)!=args.frames: raise RuntimeError('Incomplete stream')
        return
    item={'observation.state':state}; hashes={}
    for key,name in [('pikaDepthCamera','realsense_rgb'),('pikaFisheyeCamera','fisheye')]:
        path=folder/(name+'.png'); hashes[name]=sha(path)
        with Image.open(path) as image:
            array=np.asarray(image.convert('RGB')).copy()
        item['observation.images.'+key]=torch.from_numpy(array).permute(2,0,1)
    latencies=[]
    with torch.inference_mode():
        for index in range(25):
            policy.reset(); torch.cuda.synchronize(); start=time.perf_counter()
            raw=post(policy.select_action(pre(rgb_input(item)))).reshape(10).cpu()
            action=decode_action(raw,state,codec['mode'])
            torch.cuda.synchronize()
            if index>=5: latencies.append((time.perf_counter()-start)*1000)
    if action.shape!=(10,) or not torch.isfinite(action).all(): raise RuntimeError('Invalid inference output')
    report={'passed':True,'scope':'saved_real_images_with_assumed_width_gpu_inference_only',
        'robot_commands_sent':False,'hardware_ready':False,'camera_closed_loop':False,
        'gripper_width_source':'assumed_for_diagnostics_not_measured',
        'assumed_gripper_width_m':args.diagnostic_width,'action':action.tolist(),
        'predicted_width_within_sim_bound':bool(0<=action[9]<=.1),
        'codec':codec['mode'],'lerobot_commit':commit,'model_sha256':sha(checkpoint/'model.safetensors'),
        'policy_bundle':bundle_report,
        'image_sha256':hashes,'preprocessing_sha256':sha(root/'scripts/train_rgb_smoke.py'),
        'script_sha256':sha(Path(__file__)),'device':torch.cuda.get_device_name(),
        'inference_p95_ms':float(np.percentile(latencies,95)),
        'timing_scope':'same loaded image pair, resize + preprocessing + GPU inference + decoding; excludes capture/network',
        'warmup':5,'timed_repeats':20,
        'limitations':['Sequential snapshots, not synchronized','No live G1 state or measured gripper width',
                       'No action quality or hardware safety validation']}
    target=folder/'gpu-inference.json'
    if target.exists(): raise RuntimeError('Refusing to overwrite existing report')
    target.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__': main()
