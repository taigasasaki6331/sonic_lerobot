"""Single-flight worker-owned ZMQ socket; control loop never waits on network."""
import json
import hashlib
from pathlib import Path
import queue
import threading
import time
from zmq_transport import ZmqChannel


class ZmqPolicyClient:
    def __init__(self, endpoint, session, observations, frames, body_provider):
        self.session = session
        self.body_provider = body_provider
        self.packets = [json.loads((Path(observations) / f'{i:04d}.json').read_text()) for i in range(frames)]
        self.requests = queue.Queue(maxsize=1)
        self.responses = queue.Queue(maxsize=1)
        self.closed = False
        self.sent = []
        self.thread = threading.Thread(target=self.work, args=(endpoint,), daemon=True)
        self.thread.start()
        try:
            self.metadata = self.responses.get(timeout=10)
            if isinstance(self.metadata, BaseException): raise self.metadata
            if (self.metadata.get('ready') is not True or self.metadata.get('frames') != frames
                    or self.metadata.get('fps') != 30 or self.metadata.get('session') != session):
                raise ValueError('Network handshake mismatch')
            root = Path(__file__).resolve().parents[1]
            expected_commit = json.loads((root / 'sources.lock.json').read_text())['lerobot']['commit']
            model = root / 'artifacts/full-rgb-residual/run-xg1fn3b_/pretrained_model/model.safetensors'
            if (self.metadata.get('lerobot_commit') != expected_commit
                    or self.metadata.get('model_sha256') != hashlib.sha256(model.read_bytes()).hexdigest()):
                raise ValueError('Remote policy provenance mismatch')
            self.metadata['sent_body_records'] = self.sent
            self.metadata['network_transport'] = 'ZMQ_request_reply_worker_owned_socket'
        except BaseException:
            self.close()
            raise

    def work(self, endpoint):
        channel = None
        try:
            channel = ZmqChannel(endpoint, timeout_ms=1500)
            channel.send({'op': 'hello', 'session': self.session})
            self.responses.put(channel.read(), timeout=2)
            while True:
                packet = self.requests.get()
                if packet is None:
                    channel.send({'op': 'stop', 'session': self.session})
                    response = channel.read()
                    if response != {'stopped': True, 'session': self.session}:
                        raise ValueError('Invalid shutdown acknowledgement')
                    break
                channel.send(packet)
                response = channel.read()
                if response.get('session') != self.session or response.get('seq') != packet['seq']:
                    raise ValueError('Stale session/sequence response')
                self.responses.put(response, timeout=2)
        except (OSError, ValueError, queue.Full) as exc:
            try: self.responses.put_nowait(exc)
            except queue.Full: pass
        finally:
            if channel: channel.close()

    def begin(self, seq):
        if self.closed or not self.thread.is_alive(): raise RuntimeError('Network session closed')
        packet = dict(self.packets[seq])
        packet.update(session=self.session, body=self.body_provider())
        if packet['body'] is None: raise ValueError('No current simulated body state')
        try: self.requests.put_nowait(packet)
        except queue.Full: raise RuntimeError('Outstanding network request')
        self.sent.append({'seq': seq, 'body_time': packet['body']['time'],
                          'body_sha256': hashlib.sha256(json.dumps(packet['body'], sort_keys=True).encode()).hexdigest()})

    def poll(self):
        try: result = self.responses.get_nowait()
        except queue.Empty: return None
        if isinstance(result, BaseException): raise result
        return result

    def close(self):
        if self.closed: return
        self.closed = True
        try: self.requests.put_nowait(None)
        except queue.Full: pass
        self.thread.join(timeout=4)
        if self.thread.is_alive(): raise RuntimeError('Network worker did not stop')
