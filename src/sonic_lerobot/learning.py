"""Prepare expanded pi0/pi05 projections before training; never resize at inference."""
import argparse
import json
from pathlib import Path
from .schema import SCHEMA_ID, SCHEMA, ACTION_DIM, STATE_DIM


def read_schema(checkpoint):
    path = Path(checkpoint)/"sonic_schema.json"
    if not path.exists():
        if Path(checkpoint).is_dir():
            raise FileNotFoundError(path)
        from huggingface_hub import hf_hub_download
        path = Path(hf_hub_download(checkpoint, "sonic_schema.json"))
    return json.loads(path.read_text(encoding="utf-8"))


def expand_linear(layer, inputs=None, outputs=None):
    import torch
    n_in, n_out = inputs or layer.in_features, outputs or layer.out_features
    if n_in < layer.in_features or n_out < layer.out_features:
        raise ValueError("Projection shrinking is not supported")
    new = torch.nn.Linear(n_in, n_out, bias=layer.bias is not None,
                          device=layer.weight.device, dtype=layer.weight.dtype)
    with torch.no_grad():
        new.weight.zero_()
        new.weight[:layer.out_features,:layer.in_features].copy_(layer.weight)
        if layer.bias is not None:
            new.bias.zero_()
            new.bias[:layer.out_features].copy_(layer.bias)
    return new


def save_processors(cfg, stats, output, factory=None):
    if factory is None:
        from lerobot.policies.factory import make_pre_post_processors
        factory = make_pre_post_processors
    pre, post = factory(cfg, pretrained_path=None, dataset_stats=stats)
    pre.save_pretrained(output, config_filename="policy_preprocessor.json")
    post.save_pretrained(output, config_filename="policy_postprocessor.json")


def main():
    from lerobot.configs.policies import PreTrainedConfig
    from lerobot.policies.factory import get_policy_class
    from lerobot.configs.types import FeatureType, PolicyFeature
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base", required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--dataset-root", type=Path, required=True)
    p.add_argument("--dataset-repo-id", required=True)
    p.add_argument("--image-height", type=int, default=480)
    p.add_argument("--image-width", type=int, default=640)
    args = p.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    if read_schema(str(args.dataset_root))["schema_id"] != SCHEMA_ID:
        raise ValueError("Dataset schema mismatch")
    from lerobot.datasets.dataset_metadata import LeRobotDatasetMetadata
    meta = LeRobotDatasetMetadata(args.dataset_repo_id, root=args.dataset_root)
    cfg = PreTrainedConfig.from_pretrained(args.base)
    if cfg.type not in ("pi0", "pi05"):
        raise ValueError("Expected pi0/pi05")
    model = get_policy_class(cfg.type).from_pretrained(args.base, config=cfg)
    core = model.model
    core.action_in_proj = expand_linear(core.action_in_proj, inputs=64)
    core.action_out_proj = expand_linear(core.action_out_proj, outputs=64)
    if cfg.type == "pi0":
        core.state_proj = expand_linear(core.state_proj, inputs=96)
    elif getattr(core, "proprio_history_proj", None) is not None:
        core.proprio_history_proj = expand_linear(core.proprio_history_proj, inputs=96)
    cfg.max_action_dim, cfg.max_state_dim = 64, 96
    cfg.input_features = {
        "observation.state": PolicyFeature(type=FeatureType.STATE, shape=(STATE_DIM,)),
        "observation.images.ego": PolicyFeature(type=FeatureType.VISUAL, shape=(3,args.image_height,args.image_width)),
    }
    cfg.output_features = {"action":PolicyFeature(type=FeatureType.ACTION,shape=(ACTION_DIM,))}
    cfg.pretrained_path = str(args.output)
    cfg.use_relative_actions = False  # State and action joint orders differ: absolute contract.
    model.save_pretrained(args.output)
    save_processors(cfg, meta.stats, args.output)
    (args.output/"sonic_schema.json").write_text(json.dumps({"schema_id":SCHEMA_ID,"schema":SCHEMA},indent=2),encoding="utf-8")
    print("Prepared weights and dataset processors. Fine-tuning required; not a deployable checkpoint.")
