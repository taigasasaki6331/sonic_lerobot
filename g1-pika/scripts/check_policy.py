"""Static local checkpoint preflight. Never imports LeRobot or loads a policy."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def check(policy, dataset):
    codec_path=policy/'action_codec.json'
    if codec_path.exists():
        codec=json.loads(codec_path.read_text())
        if codec.get('mode')!='absolute_width' or codec.get('requires_custom_action_decode',False):
            raise ValueError('Custom action codec requires its dedicated decoder; legacy adapter refuses this checkpoint')
    config = json.loads((policy / "config.json").read_text())
    info = json.loads((dataset / "meta/info.json").read_text())
    training = json.loads((policy / "train_config.json").read_text())
    blockers = []
    if config.get("type") != "act":
        blockers.append("This initial adapter supports ACT only")
    if config.get("chunk_size") != 1 or config.get("n_action_steps") != 1:
        blockers.append("Initial h1 adapter requires chunk_size=n_action_steps=1; does not rewrite checkpoints")
    if config.get("output_features", {}).get("action", {}).get("shape") != [10]:
        blockers.append("Expected 10D action")
    for key, feature in config.get("input_features", {}).items():
        if info["features"].get(key, {}).get("shape") != feature["shape"]:
            blockers.append(f"Missing or mismatched dataset feature: {key}")
    files = {"config.json", "train_config.json", "model.safetensors",
             "policy_preprocessor.json", "policy_postprocessor.json"}
    if codec_path.exists():
        files.add('action_codec.json')
    processors = {}
    for name in ("policy_preprocessor.json", "policy_postprocessor.json"):
        processor = json.loads((policy / name).read_text())
        processors[name] = processor
        for step in processor["steps"]:
            if "state_file" in step:
                filename = step["state_file"]
                if Path(filename).name != filename:
                    raise ValueError("Processor state file must be checkpoint-local")
                files.add(filename)
    snapshots = []
    for name in sorted(files):
        path = policy / name
        if not path.is_file():
            blockers.append(f"Missing checkpoint file: {name}")
            continue
        entry = {"name": name, "size_bytes": path.stat().st_size, "sha256": digest(path)}
        if name.endswith(".safetensors"):
            with path.open("rb") as stream:
                header_length = struct.unpack("<Q", stream.read(8))[0]
                if header_length > min(100_000_000, path.stat().st_size - 8):
                    raise ValueError(f"Invalid safetensors header size: {name}")
                header = json.loads(stream.read(header_length))
            tensors = {k: v for k, v in header.items() if k != "__metadata__"}
            entry["tensor_count"] = len(tensors)
            for tensor in tensors.values():
                start, end = tensor["data_offsets"]
                if not 0 <= start <= end <= path.stat().st_size - header_length - 8:
                    raise ValueError(f"Invalid tensor extent: {name}")
        snapshots.append(entry)
    return {
        "scope": "static_checkpoint_contract_only",
        "static_contract_passed": not blockers, "blockers": blockers,
        "inference_executed": False, "hardware_communication": False,
        "policy_path": str(policy.resolve()), "dataset_path": str(dataset.resolve()),
        "training_dataset": training.get("dataset", {}).get("root"),
        "training_dataset_identity_verified": False,
        "action_semantics_and_rotation_layout_verified": False,
        "policy_type": config.get("type"), "chunk_size": config.get("chunk_size"),
        "n_action_steps": config.get("n_action_steps"),
        "input_features": config.get("input_features"),
        "dataset_info_sha256": digest(dataset / "meta/info.json"),
        "checkpoint_files": snapshots,
        "required_runtime_overrides": ["CPU policy and preprocessor", "offline Hub", "no backbone downloads"],
        "notes": ["Shape match is not semantic or training-data equivalence",
                  "Safetensors header/bounds and hashes checked; weights not loaded",
                  "Use checkpoint normalizer and unnormalizer, not current-dataset statistics"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    args = parser.parse_args()
    result = check(args.policy, args.dataset)
    output = ROOT / "artifacts" / f"policy-check-{args.policy.parent.name}.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k not in ("checkpoint_files", "input_features")}, indent=2))
    print(f"Report: {output}")
    return 0 if result["static_contract_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
