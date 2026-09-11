"""PI0/PI05 inference on GPU PC, independent from gateway's 50 Hz loop."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import time
import numpy as np
from .camera import load_provider, validate_frame
from .client import RobotClient
from .schema import Action, ACTION_DIM, STATE_DIM, SCHEMA_ID


def prediction_action(vector):
    """Decode small regression noise; keep gateway validation strict for every producer."""
    from dataclasses import replace
    action = Action.from_vector(vector)
    if abs(action.height + 1) <= 0.02:
        action = replace(action, height=-1.0)
    if action.mode != 1 and max(abs(action.vx), abs(action.vy), abs(action.yaw_rate)) <= 0.01:
        action = replace(action, vx=0.0, vy=0.0, yaw_rate=0.0)
    return action


def check_inference_age(now, submitted, max_age):
    if not 0 <= now-submitted <= max_age:
        raise TimeoutError("Inference observation expired; holding")


class PolicyRunner:
    def __init__(self, checkpoint, device="cuda", task=""):
        import torch
        from lerobot.configs.policies import PreTrainedConfig
        from lerobot.policies.factory import get_policy_class, make_pre_post_processors
        from .learning import read_schema
        if read_schema(checkpoint)["schema_id"] != SCHEMA_ID:
            raise ValueError("Checkpoint was not trained with this action/state contract")
        config = PreTrainedConfig.from_pretrained(checkpoint)
        if config.type not in ("pi0", "pi05"):
            raise ValueError("Only pi0 and pi05 supported")
        if config.output_features["action"].shape != (ACTION_DIM,) or config.input_features["observation.state"].shape != (STATE_DIM,):
            raise ValueError("Checkpoint feature dimensions disagree with schema")
        self.policy = get_policy_class(config.type).from_pretrained(checkpoint, config=config).to(device).eval()
        self.pre, self.post = make_pre_post_processors(config, pretrained_path=checkpoint,
            preprocessor_overrides={"device_processor": {"device": device}})
        self.torch, self.task = torch, task

    def predict(self, state, image):
        t = self.torch
        batch = {"observation.state": t.tensor(state, dtype=t.float32).unsqueeze(0),
                 "observation.images.ego": t.from_numpy(image.copy()).permute(2, 0, 1).float().unsqueeze(0)/255,
                 "task": [self.task]}
        with t.inference_mode():
            chunk = self.policy.predict_action_chunk(self.pre(batch))
            # Postprocess per timestep: processors expect [B,D], not necessarily [B,T,D].
            actions = t.stack([self.post(chunk[:, i]) for i in range(chunk.shape[1])], dim=1)
        result = actions[0].cpu().numpy()
        if result.ndim != 2 or result.shape[1] != ACTION_DIM or not np.isfinite(result).all():
            raise ValueError("Invalid predicted chunk")
        return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--checkpoint", required=True)
    p.add_argument("--camera", required=True, help="module:factory; object exposes read()/close()")
    p.add_argument("--endpoint", default="tcp://127.0.0.1:5560")
    p.add_argument("--device", default="cuda")
    p.add_argument("--task", required=True)
    p.add_argument("--fps", type=int, default=30, help="Must match dataset training fps")
    p.add_argument("--max-inference-age", type=float, default=0.4)
    args = p.parse_args()
    if args.fps <= 0 or not 0 < args.max_inference_age < 0.5:
        p.error("fps must be positive; max-inference-age must be in (0,0.5)")
    policy = PolicyRunner(args.checkpoint, args.device, args.task)
    camera, robot = load_provider(args.camera), RobotClient(args.endpoint)
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        # Compile/warm up BEFORE arming. Discard warmup output and memory.
        obs = robot.get_observation()
        pool.submit(policy.predict, obs["state"], validate_frame(camera.read())).result()
        policy.policy.reset()
        input("C++ control ready and operator present. Enter to arm inference: ")
        robot.arm()
        future, chunk = None, None
        chunk_start, submitted = 0.0, 0.0
        while True:
            tick = time.monotonic()
            obs = robot.get_observation()
            tick = time.monotonic()
            if not obs["armed"] or obs["epoch"] != robot.epoch:
                raise RuntimeError("Gateway entered HOLD; restart to explicitly re-arm")
            if future is not None and future.done():
                chunk = future.result()
                chunk_start = submitted
                future = None
                if tick-submitted > args.max_inference_age:
                    raise TimeoutError("Inference result too old; holding")
            if future is not None:
                check_inference_age(tick, submitted, args.max_inference_age)
            index = int((tick-chunk_start)*args.fps)
            if future is None and (chunk is None or index >= len(chunk)//2 or
                                   tick-chunk_start >= args.max_inference_age/2):
                image = validate_frame(camera.read())
                submitted = tick  # Includes camera acquisition and worker queue delay.
                future = pool.submit(policy.predict, obs["state"], image)
            if chunk is not None:
                check_inference_age(time.monotonic(), chunk_start, args.max_inference_age)
                if index >= len(chunk):
                    raise TimeoutError("Action chunk exhausted; holding instead of repeating forever")
                robot.send_action(prediction_action(chunk[index]), obs)
            time.sleep(max(0, 1/args.fps-(time.monotonic()-tick)))
    finally:
        try:
            robot.hold()
        except (ValueError, TimeoutError):
            pass
        robot.close()
        camera.close()
        pool.shutdown(wait=True, cancel_futures=True)
