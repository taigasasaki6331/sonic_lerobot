import importlib.util
import os
import math
from pathlib import Path
import numpy as np
import pytest
from sonic_lerobot.schema import *
from sonic_lerobot.protocol import planner_message, command_message, unpack
from sonic_lerobot.safety import Supervisor
from sonic_lerobot.pico import from_planner


def raw_state():
    return {"body_q_measured": [0.0]*29, "base_quat_measured": [1.,0.,0.,0.]}


def ready():
    s = Supervisor()
    s.update_state(raw_state(),0)
    s.arm(0)
    return s


def test_joint_order_and_schema():
    raw = {**raw_state(), "body_q_measured":list(range(29))}
    assert initial_action(raw).upper == tuple(UPPER_INDEX)
    assert ACTION_DIM == 48 and STATE_DIM == 81
    assert len(set(UPPER_NAMES)) == 17
    assert UPPER_NAMES[:5] == ("waist_yaw","waist_roll","waist_pitch","left_shoulder_pitch","right_shoulder_pitch")


@pytest.mark.parametrize("mode",range(27))
def test_action_roundtrip(mode):
    a = Action(tuple([0.2]*17), mode=mode)
    np.testing.assert_allclose(Action.from_vector(a.vector()).vector(), a.vector())


def test_mode_is_not_rounded_scalar_and_invalid_values_rejected():
    x = Action(tuple([0.]*17)).vector()
    x[21:] = 0.1
    with pytest.raises(ValueError,match="Ambiguous"):
        Action.from_vector(x)
    for bad in (np.nan, np.inf):
        x[0] = bad
        with pytest.raises(ValueError):
            Action.from_vector(x)


def test_heading_rotation_and_inverse_pico():
    a = Action(tuple([0.]*17), vx=0.2, vy=0.1, mode=1)
    f = planner_fields(a,math.pi/2)
    np.testing.assert_allclose(f["movement"][:2],[-1/math.sqrt(5),2/math.sqrt(5)],atol=1e-7)
    decoded, yaw = from_planner(planner_message(**f))
    assert yaw == pytest.approx(math.pi/2)
    assert decoded.vx == pytest.approx(a.vx)
    assert decoded.vy == pytest.approx(a.vy)


def test_wire_fields_and_truncation():
    raw = planner_message(**planner_fields(Action(tuple([0.]*17)),0))
    version, fields = unpack(raw,"planner")
    assert version == 1
    assert fields["upper_body_position"].shape == (17,)
    assert not any("hand" in x for x in fields)
    with pytest.raises(ValueError):
        unpack(raw[:-1],"planner")


def test_official_builder_byte_compatibility():
    root = os.environ.get("GEAR_SONIC_ROOT")
    if root is None:
        pytest.skip("Set GEAR_SONIC_ROOT to verify pinned upstream Python builder")
    path = Path(root)/"gear_sonic/utils/teleop/zmq/zmq_planner_sender.py"
    spec = importlib.util.spec_from_file_location("official_planner",path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    a = Action(tuple(np.linspace(-.3,.3,17)),vx=.15,mode=1)
    f = planner_fields(a,.7)
    assert planner_message(**f) == module.build_planner_message(**f)
    assert command_message(start=True) == module.build_command_message(True,False,True)


def test_timeout_holds_kneeling_and_invalidates_session():
    s=ready()
    epoch=s.epoch
    s.accept(Action(tuple([.1]*17),mode=5,height=.3),epoch,1,.01)
    applied=s.tick(.02,.02)
    s.update_state(raw_state(),.6)
    held=s.tick(.6,.02)
    assert held.mode == 5 and held.height == .3
    assert held.upper == applied.upper
    assert not s.armed and s.epoch != epoch
    with pytest.raises(ValueError):
        s.accept(Action(tuple([0.]*17)),epoch,2,.61)


def test_walking_stops_on_state_loss():
    s=ready()
    s.accept(Action(tuple([0.]*17),vx=.2,mode=1),s.epoch,1,.01)
    s.tick(.02,.02)
    held=s.tick(.3,.02)
    assert held.mode == 0 and held.vx == 0 and not s.armed
    assert s.reason == "state_timeout"


def test_replay_transition_and_limits():
    s=ready()
    a=Action(tuple([0.]*17),mode=5,height=.3)
    s.accept(a,s.epoch,1,.01)
    with pytest.raises(ValueError):
        s.accept(a,s.epoch,1,.02)
    with pytest.raises(ValueError,match="dwell"):
        s.accept(Action(a.upper),s.epoch,2,.03)
    s.update_state(raw_state(),2)
    with pytest.raises(ValueError,match="IDLE"):
        s.accept(Action(a.upper,mode=4,height=.3),s.epoch,2,2)
    with pytest.raises(ValueError):
        s.accept(Action(a.upper,mode=17),s.epoch,2,2)
    with pytest.raises(ValueError):
        s.accept(Action(a.upper,vx=.9,mode=1),s.epoch,2,2)


def test_slew_limits_first_motion():
    s=ready()
    s.accept(Action(tuple([1.]*17)),s.epoch,1,.01)
    a=s.tick(.02,.02)
    assert max(a.upper) == pytest.approx(.01)


def test_state_does_not_use_fake_base_position():
    raw={**raw_state(),"base_trans_measured":[99,99,99]}
    state=state_vector(raw,initial_action(raw))
    assert state.shape == (81,)
    np.testing.assert_array_equal(state[29:33],[1,0,0,0])
