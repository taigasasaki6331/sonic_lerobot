"""Export checked raw episodes through the pinned LeRobotDataset writer."""
import argparse
import json
from pathlib import Path
import numpy as np
from .schema import ACTION_DIM, STATE_DIM, ACTION_NAMES, STATE_NAMES, SCHEMA_ID, SCHEMA


def load_episode(path):
    meta = json.loads((path/"episode.json").read_text(encoding="utf-8"))
    if meta["schema_id"] != SCHEMA_ID or not meta["complete"] or meta["result"] not in ("success", "failure"):
        raise ValueError(f"Unapproved/incomplete/schema-mismatched episode: {path}")
    data = np.load(path/"frames.npz", allow_pickle=False)
    times = [json.loads(x)["receive_monotonic"] for x in (path/"timing.jsonl").read_text().splitlines()]
    if len(times) < 2 or len(times) != len(data["state"]):
        raise ValueError("Not enough aligned frames")
    gaps = np.diff(times)
    # Avoid silently treating missing/delayed samples as uniform time.
    if np.any(gaps <= 0) or np.max(gaps) > 1.75/meta["fps"]:
        raise ValueError("Episode timing has gaps; inspect before training")
    if data["state"].shape[1:] != (STATE_DIM,) or data["action"].shape[1:] != (ACTION_DIM,):
        raise ValueError("Wrong feature dimensions")
    if not np.isfinite(data["state"]).all() or not np.isfinite(data["action"]).all():
        raise ValueError("Non-finite data")
    # Uniform sample clock using nearest frames; retain exact raw times separately.
    grid = np.arange(times[0], times[-1], 1/meta["fps"])
    t = np.asarray(times)
    right = np.searchsorted(t, grid).clip(1, len(t)-1)
    index = np.where(grid-t[right-1] <= t[right]-grid, right-1, right)
    return meta, {k:data[k][index] for k in ("state", "action", "rgb")}


def main():
    from lerobot.datasets.lerobot_dataset import LeRobotDataset
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--episodes", nargs="+", type=Path, required=True)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--repo-id", required=True)
    args = p.parse_args()
    episodes = [load_episode(path) for path in args.episodes]
    meta, first = episodes[0]
    shape = first["rgb"].shape[1:]
    if any(m["fps"] != meta["fps"] or d["rgb"].shape[1:] != shape for m,d in episodes):
        raise ValueError("Camera shapes/fps must match")
    dataset = LeRobotDataset.create(repo_id=args.repo_id, root=args.root, fps=meta["fps"],
        robot_type="sonic_g1_planner", use_videos=True, features={
            "observation.state": {"dtype":"float32", "shape":(STATE_DIM,), "names":list(STATE_NAMES)},
            "action": {"dtype":"float32", "shape":(ACTION_DIM,), "names":list(ACTION_NAMES)},
            "observation.images.ego": {"dtype":"video", "shape":shape, "names":["height","width","channels"]},
        })
    try:
        for meta, data in episodes:
            for state, action, image in zip(data["state"], data["action"], data["rgb"]):
                dataset.add_frame({"observation.state":state, "action":action,
                                   "observation.images.ego":image, "task":meta["task"]})
            dataset.save_episode()
    finally:
        dataset.finalize()
    (args.root/"sonic_schema.json").write_text(json.dumps({"schema_id":SCHEMA_ID,"schema":SCHEMA},indent=2),encoding="utf-8")
