"""Record applied gateway references with robot state and timestamped RGB images."""
import argparse
import json
from pathlib import Path
import time
import numpy as np
import zmq
from .camera import load_provider, validate_frame
from .schema import SCHEMA, SCHEMA_ID


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True, help="New episode directory")
    p.add_argument("--camera", required=True)
    p.add_argument("--task", required=True)
    p.add_argument("--telemetry", default="tcp://127.0.0.1:5561")
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--seconds", type=float, default=60)
    args = p.parse_args()
    if args.fps <= 0 or args.seconds <= 0:
        p.error("fps and seconds must be positive")
    args.output.mkdir(parents=True, exist_ok=False)
    camera = load_provider(args.camera)
    ctx = zmq.Context()
    socket = ctx.socket(zmq.SUB)
    socket.setsockopt(zmq.SUBSCRIBE, b"")
    socket.setsockopt(zmq.CONFLATE, 1)
    socket.connect(args.telemetry)
    metadata = dict(schema_id=SCHEMA_ID, schema=SCHEMA, fps=args.fps, task=args.task,
                    source="pico_g1", complete=False, result="unspecified")
    meta_path = args.output / "episode.json"
    meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    rows, states, actions, images = [], [], [], []
    start = time.monotonic()
    session, last_tick = None, -1
    try:
        while time.monotonic()-start < args.seconds:
            tick = time.monotonic()
            if not socket.poll(250):
                raise TimeoutError("No fresh gateway telemetry")
            event = socket.recv_json()
            received = time.monotonic()
            if event["schema"] != SCHEMA_ID or not event["armed"] or event["state_age"] > 0.25:
                raise ValueError("Not recording HOLD or stale state")
            if session is None:
                session = event["session"]
            if event["session"] != session or event["tick"] <= last_tick:
                raise ValueError("Gateway restarted or telemetry replayed")
            last_tick = event["tick"]
            sample = camera.read()
            image = validate_frame(sample)
            if abs(sample["monotonic"]-received) > 0.1:
                raise ValueError("Camera/telemetry receive alignment exceeds 100ms")
            images.append(image.copy())
            states.append(event["state"])
            actions.append(event["action"])
            rows.append({**event, "receive_monotonic": received, "camera_monotonic": sample["monotonic"]})
            time.sleep(max(0, 1/args.fps-(time.monotonic()-tick)))
        metadata["complete"] = True
    except KeyboardInterrupt:
        metadata["complete"] = True
    finally:
        socket.close(0)
        ctx.term()
        camera.close()
        if rows:
            np.savez_compressed(args.output/"frames.npz", state=np.asarray(states, dtype=np.float32),
                                action=np.asarray(actions, dtype=np.float32), rgb=np.asarray(images))
            (args.output/"timing.jsonl").write_text("\n".join(json.dumps(r) for r in rows)+"\n", encoding="utf-8")
        metadata["frames"] = len(rows)
        meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    if rows:
        result = input("Episode result [success/failure/discard]: ").strip()
        if result not in ("success", "failure", "discard"):
            raise ValueError("Episode remains unspecified; set result before export")
        metadata["result"] = result
        meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
