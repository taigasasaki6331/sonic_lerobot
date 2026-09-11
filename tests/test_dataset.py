import json
import numpy as np
import pytest
from sonic_lerobot.dataset import load_episode
from sonic_lerobot.schema import STATE_DIM,ACTION_DIM,SCHEMA_ID


def test_export_validates_timing_and_result(tmp_path):
    meta={"schema_id":SCHEMA_ID,"complete":True,"result":"success","fps":30}
    (tmp_path/"episode.json").write_text(json.dumps(meta))
    np.savez(tmp_path/"frames.npz",state=np.zeros((3,STATE_DIM)),action=np.zeros((3,ACTION_DIM)),rgb=np.zeros((3,2,2,3),dtype=np.uint8))
    timing=tmp_path/"timing.jsonl"
    timing.write_text("\n".join(json.dumps({"receive_monotonic":t}) for t in (0,1/30,2/30)))
    m,d=load_episode(tmp_path)
    assert d["state"].shape[1]==STATE_DIM
    timing.write_text("\n".join(json.dumps({"receive_monotonic":t}) for t in (0,.5,.6)))
    with pytest.raises(ValueError,match="gaps"):
        load_episode(tmp_path)
