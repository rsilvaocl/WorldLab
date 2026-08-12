"""Tests del logger JSONL (fase 0)."""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.world_state import WorldConfig, WorldState, Entity
from ai.logger import JsonlLogger, read_jsonl


def make_world_with_logger(tmpdir):
    cfg = WorldConfig(width=10, height=10)
    w = WorldState(cfg, [Entity(eid="a0", kind="agent", x=1, y=1)], seed=1)
    log = JsonlLogger(str(tmpdir / "sim.jsonl"), meta={"experiment": "test", "seed": 1})
    return w, log


def test_logger_writes_events(tmp_path):
    w, log = make_world_with_logger(tmp_path)
    ev = w.move("a0", 1, 0)
    log.log_event(ev)
    log.close()

    lines = read_jsonl(str(tmp_path / "sim.jsonl"))
    assert lines[0]["type"] == "meta"
    assert lines[0]["experiment"] == "test"
    assert lines[1]["type"] == "event"
    assert lines[1]["action"] == "move"
    assert lines[1]["outcome"] == "ok"
    assert lines[1]["eid"] == "a0"


def test_logger_snapshot(tmp_path):
    w, log = make_world_with_logger(tmp_path)
    log.log_snapshot(day=1, tick=0, state=w)
    log.close()

    lines = read_jsonl(str(tmp_path / "sim.jsonl"))
    snap = lines[1]
    assert snap["type"] == "snapshot"
    assert snap["day"] == 1
    assert snap["entities"][0]["eid"] == "a0"
    assert "energy" in snap["agents"]["a0"]


def test_logger_trace(tmp_path):
    w, log = make_world_with_logger(tmp_path)
    log.log_trace(day=1, tick=0, eid="a0", trace={
        "observation": "food nearby", "goal": "survive",
        "prediction": {"expected_value": 0.7}, "proposed_action": "gather"})
    log.close()

    lines = read_jsonl(str(tmp_path / "sim.jsonl"))
    trace = lines[1]
    assert trace["type"] == "trace"
    assert trace["proposed_action"] == "gather"
    assert trace["prediction"]["expected_value"] == 0.7


def test_logger_replay_roundtrip(tmp_path):
    """Reconstruir una simulación corta desde eventos: los eventos registrados
    deben coincidir con los del estado en memoria."""
    cfg = WorldConfig(width=10, height=10)
    w = WorldState(cfg, [Entity(eid="a0", kind="agent", x=1, y=1)], seed=1)
    log = JsonlLogger(str(tmp_path / "sim.jsonl"), meta={"experiment": "replay"})
    for _ in range(5):
        ev = w.move("a0", 1, 0)
        log.log_event(ev)
        w.advance_tick()
    log.close()

    lines = read_jsonl(str(tmp_path / "sim.jsonl"))
    events = [l for l in lines if l["type"] == "event"]
    assert len(events) == 5
    assert all(e["outcome"] == "ok" for e in events)
