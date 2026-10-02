"""Read-only audit of the local LeRobot dataset. No LeRobot/device imports."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path

import numpy as np
import pyarrow
import pyarrow.parquet as pq

from dataset_contract import inspect_episode

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = Path("/home/developer/workspaces/pika_ws2/datasets/data_2608261323_valid49_g1_zero_relative_h1_final_v3")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--rotation-layout", choices=("columns", "rows"), default="columns")
    args = parser.parse_args()
    if pyarrow.__version__ != "23.0.1":
        raise RuntimeError("Audit requires pyarrow==23.0.1 (this PC: system Python)")
    info_path = args.dataset / "meta/info.json"
    info = json.loads(info_path.read_text())
    names = info["features"]["action"]["names"]
    if len(names) == 1 and isinstance(names[0], list):
        names = names[0]
    if len(names) != 10 or not all(n.startswith("relative_trajectory.h1.pika.") for n in names):
        raise ValueError("Expected single-arm PIKA relative h1 dataset")
    episodes, sources = defaultdict(list), []
    for path in sorted((args.dataset / "data").glob("chunk-*/*.parquet")):
        table = pq.read_table(path, columns=["episode_index", "frame_index", "timestamp", "observation.state", "action"])
        for row in table.to_pylist():
            episodes[row["episode_index"]].append(row)
        sources.append({"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    reports = []
    for index, rows in sorted(episodes.items()):
        rows.sort(key=lambda row: row["frame_index"])
        if [r["frame_index"] for r in rows] != list(range(len(rows))):
            raise ValueError(f"Episode {index}: missing or duplicate frame indices")
        if not np.allclose([r["timestamp"] for r in rows], np.arange(len(rows)) / info["fps"], atol=1e-5):
            raise ValueError(f"Episode {index}: timestamp/fps mismatch")
        reports.append({"episode": index, "frames": len(rows), **inspect_episode(rows, args.rotation_layout)})
    frames = sum(r["frames"] for r in reports)
    if not reports or len(reports) != info["total_episodes"] or frames != info["total_frames"]:
        raise ValueError("Metadata episode/frame counts disagree")
    contract_passed = all(r["state_contract_passed"] for r in reports)
    report = {
        "scope": "relative_state_action_contract_not_task_quality",
        "pose_contract_passed": contract_passed,
        "dataset_fully_verified": False,
        "dataset": str(args.dataset), "episodes": len(reports), "frames": frames,
        "fps": info["fps"], "rotation_layout": args.rotation_layout,
        "gripper_h1_mismatch_count": sum(r["gripper_h1_mismatch_count"] for r in reports),
        "gripper_h1_residual_max_m": max(r["gripper_h1_residual_max_m"] for r in reports),
        "info_sha256": hashlib.sha256(info_path.read_bytes()).hexdigest(),
        "source_files": sources, "exporter_pyarrow": pyarrow.__version__, "episode_reports": reports,
    }
    output = ROOT / "artifacts/dataset-check-latest.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k not in ("source_files", "episode_reports")}, indent=2))
    print(f"Details: {output}")
    return 0 if contract_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
