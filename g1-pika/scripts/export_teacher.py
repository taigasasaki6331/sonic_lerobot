"""Read one local LeRobot v3 episode; no videos, SDK or device access.

Exporter only: requires pyarrow==23.0.1 (available in this PC's system Python).
Simulation consumes the JSON snapshot and does not require pyarrow/LeRobot.
"""
import argparse
import hashlib
import json
from pathlib import Path

import pyarrow
import pyarrow.parquet as pq


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--episode", type=int, default=0)
    parser.add_argument("--rotation-layout", choices=("columns", "rows"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if pyarrow.__version__ != "23.0.1":
        raise RuntimeError("Exporter requires pyarrow==23.0.1")
    info_path = args.dataset / "meta/info.json"
    info = json.loads(info_path.read_text())
    names = info["features"]["action"]["names"]
    if len(names) == 1 and isinstance(names[0], list):
        names = names[0]
    if info["features"]["action"]["shape"] != [10] or not all(
        name.startswith("relative_trajectory.h1.pika.") for name in names
    ):
        raise ValueError("Expected single-arm h1 relative trajectory, 10D")
    rows, sources = [], []
    for path in sorted((args.dataset / "data").glob("chunk-*/*.parquet")):
        table = pq.read_table(path, columns=["episode_index", "frame_index", "timestamp", "action", "observation.state"],
                              filters=[("episode_index", "=", args.episode)])
        if table.num_rows:
            rows.extend(table.to_pylist())
            sources.append({"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    rows.sort(key=lambda r: r["frame_index"])
    if not rows or [r["frame_index"] for r in rows] != list(range(len(rows))):
        raise ValueError("Episode missing or frame indices not contiguous from zero")
    result = {
        "format": "g1-pika-teacher-v1", "episode": args.episode, "fps": info["fps"],
        "rotation_layout": args.rotation_layout, "action_reference": "local-relative-h1",
        "tracker_to_tcp_rotation": [[0, 0, 1], [0, -1, 0], [1, 0, 0]],
        "layout_note": "Explicit layout selected by exporter; source feature names alone are not reliable. Decoder checks numeric orthonormality.",
        "source_names": names, "source_files": sources,
        "info_sha256": hashlib.sha256(info_path.read_bytes()).hexdigest(),
        "exporter_pyarrow": pyarrow.__version__, "frames": rows,
    }
    # Validate before writing, using the same dependency-light decoder as replay.
    from teacher_trajectory import TeacherTrajectory
    from dataset_contract import inspect_episode
    TeacherTrajectory(result)
    result["dataset_contract"] = inspect_episode(rows, args.rotation_layout)
    if not result["dataset_contract"]["state_contract_passed"]:
        raise ValueError("Dataset state is not current-TCP-relative identity")
    for frame in rows:
        del frame["observation.state"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"Exported episode {args.episode}: {len(rows)} frames -> {args.output}")


if __name__ == "__main__":
    main()
