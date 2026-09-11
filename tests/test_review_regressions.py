from types import SimpleNamespace
import pytest
from sonic_lerobot.gateway import Gateway
from sonic_lerobot.schema import Action
from sonic_lerobot.runner import prediction_action, check_inference_age
from sonic_lerobot.learning import save_processors, read_schema


@pytest.mark.parametrize("payload", [[], None, 42, "state"])
def test_malformed_rpc_rejected_without_attribute_error(payload):
    gateway = Gateway.__new__(Gateway)
    gateway.supervisor = None
    with pytest.raises(ValueError, match="must be an object"):
        gateway.handle(payload, 0)


def test_prediction_noise_is_canonicalized_only_within_small_tolerance():
    noisy = Action((0.,)*17, vx=.001, vy=-.002, yaw_rate=.001, height=-.99999)
    decoded = prediction_action(noisy.vector())
    assert decoded.height == -1 and decoded.vx == decoded.vy == decoded.yaw_rate == 0
    large = Action((0.,)*17, vx=.1, height=-.9)
    decoded = prediction_action(large.vector())
    assert decoded.vx == pytest.approx(.1) and decoded.height == pytest.approx(-.9)
    walking = Action((0.,)*17, vx=.005, mode=1)
    assert prediction_action(walking.vector()).vx == pytest.approx(.005)


@pytest.mark.parametrize("now", [.401, 2., -.1])
def test_inflight_or_active_chunk_expiry(now):
    with pytest.raises(TimeoutError):
        check_inference_age(now, 0, .4)


def test_current_chunk_valid():
    check_inference_age(.2, 0, .4)


def test_processor_creation_uses_fresh_stats_and_training_filenames(tmp_path):
    calls = []
    def factory(cfg, **kwargs):
        assert kwargs == {"pretrained_path": None, "dataset_stats": {"test": 1}}
        return tuple(SimpleNamespace(save_pretrained=lambda path, **kw: calls.append((path, kw)))
                     for _ in range(2))
    save_processors(object(), {"test": 1}, tmp_path, factory)
    assert [kw["config_filename"] for _, kw in calls] == [
        "policy_preprocessor.json", "policy_postprocessor.json"]


def test_missing_local_schema_does_not_attempt_hub(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_schema(str(tmp_path))
