"""Offline recorded-observation ACT evaluation. No robot API or WBC commands."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import hashlib
import importlib.metadata

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--episode", type=int, default=0)
    parser.add_argument("--steps", type=int, default=32, help="Evenly sampled frames across the episode")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/policy-eval-latest.json")
    parser.add_argument("--depth-probe", choices=("native", "pil-rgb"), default="native",
                        help="pil-rgb is a diagnostic hypothesis, NOT verified training preprocessing")
    args = parser.parse_args()
    if args.steps <= 0:
        parser.error("--steps must be positive")
    if sys.version_info[:3] != (3, 12, 13):
        raise RuntimeError("Expected the validated Python 3.12.13 policy environment")
    for line in (ROOT / "requirements-policy.lock").read_text().splitlines():
        if "==" in line and not line.startswith("#"):
            name, expected = line.split("==")
            if importlib.metadata.version(name) != expected:
                raise RuntimeError(f"Dependency differs from policy lock: {name}")
    for key, value in {"HF_HUB_OFFLINE": "1", "HF_DATASETS_OFFLINE": "1",
                       "HF_HUB_DISABLE_TELEMETRY": "1", "HF_HOME": str(ROOT / ".cache/policy/hf"),
                       "TORCH_HOME": str(ROOT / ".cache/policy/torch"),
                       "XDG_CACHE_HOME": str(ROOT / ".cache/policy")}.items():
        os.environ[key] = value
    # Network guard in addition to offline flags and the filesystem sandbox.
    def audit(event, arguments):
        if event in {"socket.connect", "socket.bind", "socket.sendto", "socket.getaddrinfo"}:
            raise RuntimeError(f"Network forbidden during offline evaluation: {event}")
    sys.addaudithook(audit)
    from check_policy import check
    manifest = check(args.policy, args.dataset)
    if not manifest["static_contract_passed"]:
        raise ValueError(manifest["blockers"])
    upstream = ROOT / "vendor/lerobot"
    commit = json.loads((ROOT / "sources.lock.json").read_text())["lerobot"]["commit"]
    if subprocess.check_output(["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True).strip() != commit:
        raise RuntimeError("Wrong LeRobot revision")
    subprocess.run(["git", "-C", str(upstream), "diff", "--exit-code", "HEAD"], check=True)
    # Use exactly the verified source, not an editable install elsewhere.
    sys.path.insert(0, str(upstream / "src"))
    import numpy as np
    import torch
    from PIL import Image
    from lerobot.policies.act.configuration_act import ACTConfig
    from lerobot.policies.act.modeling_act import ACTPolicy
    from lerobot.policies.factory import make_pre_post_processors
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    torch.set_num_threads(4)
    torch.manual_seed(0)
    training = json.loads((args.policy / "train_config.json").read_text())
    depth_unit = training["dataset"].get("depth_output_unit", "mm")
    cfg = ACTConfig.from_pretrained(str(args.policy), local_files_only=True)
    cfg.device = "cpu"
    cfg.pretrained_backbone_weights = None
    cfg.use_amp = False
    policy = ACTPolicy.from_pretrained(str(args.policy), config=cfg, local_files_only=True, strict=True)
    policy.eval()
    pre, post = make_pre_post_processors(cfg, pretrained_path=str(args.policy),
        preprocessor_overrides={"device_processor": {"device": "cpu"}},
        postprocessor_overrides={"device_processor": {"device": "cpu"}})
    dataset = LeRobotDataset("data", root=args.dataset, episodes=[args.episode],
                             return_uint8=True, video_backend="pyav", depth_output_unit=depth_unit)
    indices = np.unique(np.linspace(0, len(dataset) - 1, min(args.steps, len(dataset)), dtype=int))
    samples, latencies, inputs = [], [], {}
    policy.reset()
    with torch.inference_mode():
        for index in indices:
            item = dataset[int(index)]
            observation = {}
            for key in cfg.input_features:
                value = item[key]
                # Only RGB uint8 gets /255. Depth retains training physical units.
                if key.startswith("observation.images.") and value.dtype == torch.uint8:
                    value = value.float() / 255.0
                if key.startswith("observation.depths.") and args.depth_probe == "pil-rgb":
                    raw = value.cpu().numpy()
                    if raw.shape != (1, 480, 640) or (raw < 0).any() or (raw > 65535).any() or not np.equal(raw, np.floor(raw)).all():
                        raise ValueError("PIL probe requires unmodified uint16-valued single-channel depth")
                    rgb = np.asarray(Image.fromarray(raw[0].astype(np.uint16)).convert("RGB")).copy()
                    value = torch.from_numpy(rgb).permute(2, 0, 1).float() / 255.0
                if not torch.isfinite(value).all():
                    raise ValueError(f"Nonfinite observation: {key}")
                observation[key] = value
                inputs.setdefault(key, {"shape": list(value.shape), "dtype": str(value.dtype),
                                        "first_min": float(value.min()), "first_max": float(value.max())})
            if "task" in item:
                observation["task"] = item["task"]
            started = time.perf_counter()
            prediction = post(policy.select_action(pre(observation))).reshape(-1).cpu().numpy()
            latencies.append((time.perf_counter() - started) * 1000)
            if prediction.shape != (10,) or not np.isfinite(prediction).all():
                raise ValueError("Invalid policy action")
            samples.append({"frame_index": int(item["frame_index"]),
                            "timestamp": float(item["timestamp"]),
                            "action": prediction.tolist(), "teacher_action": item["action"].tolist(),
                            "current_gripper": float(item["observation.state"][-1])})
            if len(samples) % 8 == 0:
                print(f"Evaluated {len(samples)}/{len(indices)} frames", flush=True)
    predictions = np.array([s["action"] for s in samples])
    teacher = np.array([s["teacher_action"] for s in samples])
    baseline = np.zeros_like(teacher)
    baseline[:, [3, 7]] = 1
    baseline[:, 9] = [s["current_gripper"] for s in samples]
    error = np.abs(predictions - teacher)
    base_error = np.abs(baseline - teacher)
    def rotations(values):
        a, b = values[:, 3:6].copy(), values[:, 6:9].copy()
        na = np.linalg.norm(a, axis=1, keepdims=True)
        if (na < 1e-8).any():
            raise ValueError("Degenerate policy rotation column")
        a /= na
        b -= a * np.sum(a * b, axis=1, keepdims=True)
        nb = np.linalg.norm(b, axis=1, keepdims=True)
        if (nb < 1e-8).any():
            raise ValueError("Degenerate policy rotation columns")
        b /= nb
        return np.stack([a, b, np.cross(a, b)], axis=2)
    predicted_rotations, teacher_rotations = rotations(predictions), rotations(teacher)
    relative = np.swapaxes(predicted_rotations, 1, 2) @ teacher_rotations
    angles = np.arccos(np.clip((np.trace(relative, axis1=1, axis2=2) - 1) / 2, -1, 1))
    base_angles = np.arccos(np.clip((np.trace(teacher_rotations, axis1=1, axis2=2) - 1) / 2, -1, 1))
    result = {
        "status": "offline_inference_completed", "task_success_evaluated": False,
        "closed_loop": False, "wbc_connected": False, "hardware_communication": False,
        "network_guard_enabled": True, "lerobot_commit": commit, "device": "cpu",
        "requirements_sha256": hashlib.sha256((ROOT / "requirements-policy.lock").read_bytes()).hexdigest(),
        "episode": args.episode, "samples": len(samples), "episode_frames": len(dataset),
        "sampling": "evenly_spaced_recorded_observations", "depth_unit": depth_unit,
        "depth_probe": args.depth_probe,
        "depth_units_verified": False,
        "training_depth_transform_verified": False,
        "normalization": "checkpoint_pre_and_post_processors", "input_summary": inputs,
        "rotation_error_mean_rad": float(angles.mean()),
        "rotation_error_max_rad": float(angles.max()),
        "no_motion_rotation_error_mean_rad": float(base_angles.mean()),
        "rotation_metric": "column-layout_Gram_Schmidt_projection_for_metrics_only",
        "negative_gripper_predictions": int(np.sum(predictions[:, 9] < 0)),
        "ready_for_hardware": False,
        "deployment_notes": ["No closed-loop validation or calibrated output limits",
                             "Gripper is not actuated; raw predictions are not clipped",
                             "CPU throughput must be assessed separately from simulation speed"],
        "mae_per_dimension": error.mean(axis=0).tolist(),
        "no_motion_mae_per_dimension": base_error.mean(axis=0).tolist(),
        "translation_l2_mean_m": float(np.linalg.norm(predictions[:, :3] - teacher[:, :3], axis=1).mean()),
        "no_motion_translation_l2_mean_m": float(np.linalg.norm(teacher[:, :3], axis=1).mean()),
        "gripper_mae_m": float(error[:, 9].mean()),
        "inference_pipeline_p95_ms": float(np.percentile(latencies, 95)),
        "predicted_translation_norm_max_m": float(np.linalg.norm(predictions[:, :3], axis=1).max()),
        "predicted_gripper_min_max_m": [float(predictions[:, 9].min()), float(predictions[:, 9].max())],
        "checkpoint_manifest": manifest, "predictions": samples,
    }
    output = args.output
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k not in ("predictions", "checkpoint_manifest", "input_summary")}, indent=2))
    print(f"Report: {output}")


if __name__ == "__main__":
    main()
