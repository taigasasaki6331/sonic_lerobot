"""PICO planner-reference input. Never interpret SMPL v3 joint_pos as full joints."""
import argparse
import importlib
import math
import time
import zmq
from .protocol import unpack
from .schema import Action, finite_vector
from .client import RobotClient


def from_planner(raw):
    version, fields = unpack(raw, "planner")
    if version != 1 or "upper_body_position" not in fields:
        raise ValueError("PICO planner stream must include a retargeted upper_body_position[17]")
    upper = finite_vector(fields["upper_body_position"].reshape(-1), 17)
    facing = finite_vector(fields["facing"].reshape(-1), 3)
    movement = finite_vector(fields["movement"].reshape(-1), 3)
    yaw = math.atan2(facing[1], facing[0])
    speed = float(fields["speed"].item())
    magnitude = math.hypot(*movement[:2])
    if magnitude > 1e-6 and speed < 0:
        raise ValueError("Explicit speed required for nonzero motion")
    speed = max(0, speed)
    mx, my = movement[:2]/magnitude*speed if magnitude > 1e-6 else (0,0)
    vx, vy = math.cos(yaw)*mx+math.sin(yaw)*my, -math.sin(yaw)*mx+math.cos(yaw)*my
    return Action(tuple(upper), vx, vy, 0, float(fields["height"].item()), int(fields["mode"].item())), yaw


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", default="tcp://127.0.0.1:5558")
    p.add_argument("--endpoint", default="tcp://127.0.0.1:5560")
    p.add_argument("--retarget", help="module:function(raw_bytes)->(Action, heading_radians); required for SMPL pose")
    args = p.parse_args()
    converter = from_planner
    if args.retarget:
        module, name = args.retarget.split(":",1)
        converter = getattr(importlib.import_module(module),name)
    ctx = zmq.Context()
    socket = ctx.socket(zmq.SUB)
    socket.setsockopt(zmq.SUBSCRIBE,b"pose" if args.retarget else b"planner")
    socket.setsockopt(zmq.CONFLATE,1)
    socket.connect(args.source)
    robot = RobotClient(args.endpoint)
    try:
        input("Retargeted PICO references ready. Enter to arm: ")
        robot.arm()
        last_yaw, last_time = None, None
        while True:
            if not socket.poll(250):
                raise TimeoutError("PICO stream lost")
            action, yaw = converter(socket.recv())
            now = time.monotonic()
            yaw_rate = 0 if last_time is None else math.atan2(math.sin(yaw-last_yaw),math.cos(yaw-last_yaw))/(now-last_time)
            last_yaw, last_time = yaw, now
            if action.mode != 1:
                yaw_rate = 0.0
            action = Action(action.upper, action.vx, action.vy, yaw_rate, action.height, action.mode)
            robot.send_action(action, robot.get_observation())
    finally:
        try:
            robot.hold()
        except (ValueError, TimeoutError):
            pass
        robot.close()
        socket.close(0)
        ctx.term()
