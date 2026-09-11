import json
import time
import threading
import msgpack
import numpy as np
import pytest
import zmq
from sonic_lerobot.client import RobotClient
from sonic_lerobot.gateway import Gateway
from sonic_lerobot.schema import Action, SCHEMA_ID
from sonic_lerobot.protocol import unpack


def port():
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1",0))
        return s.getsockname()[1]


def test_real_zmq_roundtrip_and_watchdog():
    rpc,planner,state,telemetry=[f"tcp://127.0.0.1:{port()}" for _ in range(4)]
    stop=threading.Event()
    ready=threading.Event()
    errors=[]
    # All gateway ZMQ sockets are created and used on the same thread.
    def serve():
        g=None
        try:
            g=Gateway(rpc,planner,state,telemetry)
            ready.set()
            last=time.monotonic()
            while not stop.is_set():
                now=time.monotonic()
                g.step(now,now-last)
                last=now
                time.sleep(.01)
        except Exception as exc:
            errors.append(exc)
        finally:
            if g:g.close()
    thread=threading.Thread(target=serve)
    thread.start()
    assert ready.wait(2)
    ctx=zmq.Context()
    pub=ctx.socket(zmq.PUB);pub.bind(state)
    sub=ctx.socket(zmq.SUB);sub.setsockopt(zmq.SUBSCRIBE,b"planner");sub.setsockopt(zmq.CONFLATE,1);sub.connect(planner)
    client=RobotClient(rpc)
    raw={"body_q_measured":[0.]*29,"base_quat_measured":[1.,0.,0.,0.]}
    def feed(duration):
        end=time.monotonic()+duration
        while time.monotonic()<end:
            pub.send(b"g1_debug"+msgpack.packb(raw))
            time.sleep(.01)
    try:
        # PUB/SUB subscription establishment is asynchronous; wait for observed state.
        deadline=time.monotonic()+3
        while True:
            feed(.1)
            try:
                client.get_observation()
                break
            except ValueError:
                if time.monotonic()>deadline:
                    raise
        client.arm()
        obs=client.get_observation()
        assert len(obs["state"]) == 81
        client.send_action(Action(tuple([0.]*17),mode=5,height=.3),obs)
        feed(.1)
        assert sub.poll(500)
        _, f=unpack(sub.recv(),"planner")
        assert f["mode"].item()==5
        feed(.6) # state stays fresh; GPU action stream is lost
        _, f=unpack(sub.recv(),"planner")
        assert f["mode"].item()==5 and f["speed"].item()==0
        obs=client.get_observation()
        assert not obs["armed"] and obs["reason"]=="action_timeout"
        with pytest.raises(ValueError):
            client.send_action(Action(tuple([0.]*17)),obs)
        client.arm()
        assert client.get_observation()["armed"]
    finally:
        client.close();pub.close(0);sub.close(0);ctx.term()
        stop.set();thread.join(2)
    assert not thread.is_alive() and not errors


def test_ticket_and_ownership():
    endpoints=[f"tcp://127.0.0.1:{port()}" for _ in range(4)]
    g=Gateway(*endpoints)
    try:
        raw={"body_q_measured":[0.]*29,"base_quat_measured":[1.,0.,0.,0.]}
        g.supervisor.update_state(raw,0)
        req={"schema":SCHEMA_ID,"owner":"a"}
        arm=g.handle({**req,"op":"arm"},0)
        with pytest.raises(ValueError,match="Another producer"):
            g.handle({**req,"owner":"b","op":"arm"},0)
        obs=g.handle({**req,"op":"state"},0)
        g.supervisor.update_state(raw,1)
        with pytest.raises(ValueError,match="ticket expired"):
            g.handle({**req,**arm,"op":"action","ticket":obs["ticket"],"sequence":1,
                      "action":Action(tuple([0.]*17)).vector().tolist()},1)
    finally:
        g.close()
