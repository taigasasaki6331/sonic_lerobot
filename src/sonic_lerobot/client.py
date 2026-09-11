import uuid
import zmq
from .schema import SCHEMA_ID


class RobotClient:
    """One owner; arm explicitly after a timeout. Use only in its creating thread."""
    def __init__(self, endpoint="tcp://127.0.0.1:5560", timeout_ms=1000):
        self.ctx = zmq.Context()
        self.endpoint, self.timeout_ms = endpoint, timeout_ms
        self.owner, self.session = uuid.uuid4().hex, None
        self.epoch, self.sequence = 0, 0
        self._connect()

    def _connect(self):
        self.socket = self.ctx.socket(zmq.REQ)
        self.socket.setsockopt(zmq.LINGER, 0)
        self.socket.setsockopt(zmq.SNDTIMEO, self.timeout_ms)
        self.socket.setsockopt(zmq.RCVTIMEO, self.timeout_ms)
        self.socket.connect(self.endpoint)

    def request(self, op, **data):
        try:
            self.socket.send_json(dict(schema=SCHEMA_ID, op=op, owner=self.owner,
                session=self.session, epoch=self.epoch, **data))
            response = self.socket.recv_json()
        except zmq.Again as exc:
            self.socket.close(0)
            self._connect()
            raise TimeoutError("Gateway unavailable; no automatic re-arm") from exc
        if not response["ok"]:
            raise ValueError(response["error"])
        return response

    def arm(self):
        result = self.request("arm")
        self.epoch, self.session, self.sequence = result["epoch"], result["session"], 0

    def get_observation(self):
        return self.request("state")

    def send_action(self, action, observation):
        self.sequence += 1
        return self.request("action", action=action.vector().tolist(),
                            ticket=observation["ticket"], sequence=self.sequence)

    def hold(self):
        return self.request("hold")

    def close(self):
        self.socket.close(0)
        self.ctx.term()
