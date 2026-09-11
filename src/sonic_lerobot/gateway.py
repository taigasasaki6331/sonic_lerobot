"""Run beside C++ deployment; GPU network loss does not stop planner publishing."""
import argparse
import json
import logging
import time
import uuid
import msgpack
import zmq
from .protocol import planner_message
from .schema import Action, SCHEMA_ID, planner_fields, state_vector
from .safety import Supervisor


class Gateway:
    def __init__(self, rpc="tcp://127.0.0.1:5560", planner="tcp://127.0.0.1:5556",
                 state="tcp://127.0.0.1:5557", telemetry="tcp://127.0.0.1:5561"):
        self.ctx = zmq.Context()
        self.rpc, self.pub, self.sub, self.events = [self.ctx.socket(t) for t in (zmq.REP, zmq.PUB, zmq.SUB, zmq.PUB)]
        for s in (self.rpc, self.pub, self.sub, self.events):
            s.setsockopt(zmq.LINGER, 0)
            s.setsockopt(zmq.MAXMSGSIZE, 1_000_000)
        self.rpc.bind(rpc)
        self.pub.bind(planner)
        self.events.bind(telemetry)
        self.sub.setsockopt(zmq.SUBSCRIBE, b"g1_debug")
        self.sub.setsockopt(zmq.CONFLATE, 1)
        self.sub.connect(state)
        self.supervisor = Supervisor()
        self.session = uuid.uuid4().hex
        self.tickets = {}
        self.state_seq = 0
        self.tick_seq = 0
        self.owner = None
        self.latest_event = None

    def handle(self, req, now):
        s = self.supervisor
        if not isinstance(req, dict):
            raise ValueError("RPC request must be an object")
        if req.get("schema") != SCHEMA_ID:
            raise ValueError("Schema mismatch")
        op = req.get("op")
        if op == "state":
            if s.raw is None or now-s.state_time > s.state_timeout:
                raise ValueError("No fresh state")
            ticket = uuid.uuid4().hex
            self.tickets = {k:v for k,v in self.tickets.items() if now-v < s.timeout}
            if len(self.tickets) >= 100:
                raise ValueError("Too many unconsumed observation tickets")
            self.tickets[ticket] = now
            return dict(state=state_vector(s.raw, s.applied).tolist(), ticket=ticket,
                        state_seq=self.state_seq, state_age=now-s.state_time,
                        epoch=s.epoch, armed=s.armed, session=self.session, reason=s.reason)
        if op == "arm":
            owner = req.get("owner")
            if not isinstance(owner, str) or not owner:
                raise ValueError("Owner required")
            if s.armed and self.owner != owner:
                raise ValueError("Another producer owns the gateway")
            epoch = s.arm(now)
            self.owner = owner
            self.tickets.clear()
            return dict(epoch=epoch, session=self.session)
        if req.get("owner") != self.owner or req.get("session") != self.session:
            raise ValueError("Wrong owner/session")
        if op == "hold":
            s.trip("operator_hold")
            return {}
        if op == "action":
            ticket = req.get("ticket")
            issued = self.tickets.pop(ticket, -float("inf"))
            if now-issued > s.timeout:
                raise ValueError("Observation ticket expired; recompute from fresh state")
            s.accept(Action.from_vector(req["action"]), req["epoch"], req["sequence"], now)
            return dict(accepted=True)
        raise ValueError("Unknown operation")

    def step(self, now, dt):
        if self.sub.poll(0):
            try:
                raw = msgpack.unpackb(self.sub.recv()[len(b"g1_debug"):], raw=False)
                self.supervisor.update_state(raw, now)
                self.state_seq += 1
            except (ValueError, KeyError, TypeError, msgpack.UnpackException):
                logging.exception("Rejected invalid state")
        # Process at most one request per tick: clients cannot starve the control publisher.
        if self.rpc.poll(0):
            try:
                response = {"ok": True, **self.handle(self.rpc.recv_json(), now)}
            except (ValueError, KeyError, TypeError, OverflowError) as exc:
                response = {"ok": False, "error": str(exc)}
            self.rpc.send_json(response)
        previous = self.supervisor.applied
        action = self.supervisor.tick(now, dt)
        if action is not None:
            fields = planner_fields(action, self.supervisor.yaw)
            self.pub.send(planner_message(**fields))
            self.tick_seq += 1
            event = dict(schema=SCHEMA_ID, session=self.session, tick=self.tick_seq,
                monotonic=now, wall_time=time.time(), state_seq=self.state_seq,
                state_age=now-self.supervisor.state_time,
                state=state_vector(self.supervisor.raw, previous).tolist(),
                requested_action=self.supervisor.target.vector().tolist(), action=action.vector().tolist(),
                armed=self.supervisor.armed, reason=self.supervisor.reason)
            self.latest_event = event
            self.events.send_json(event)

    def run(self):
        last = time.monotonic()
        try:
            while True:
                now = time.monotonic()
                self.step(now, now-last)
                last = now
                time.sleep(max(0, 0.02-(time.monotonic()-now)))
        finally:
            self.close()

    def close(self):
        for socket in (self.rpc, self.pub, self.sub, self.events):
            socket.close(0)
        self.ctx.term()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name, default in (("rpc", "tcp://127.0.0.1:5560"), ("planner", "tcp://127.0.0.1:5556"),
                          ("state", "tcp://127.0.0.1:5557"), ("telemetry", "tcp://127.0.0.1:5561")):
        p.add_argument(f"--{name}", default=default)
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO)
    Gateway(**vars(args)).run()
