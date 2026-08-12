"""Tests del probe de composición (D-005)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.world_state import WorldConfig, WorldState, Entity
from ai.llm_agent import LLMAgent
from ai.probe import CompositionProbe, run_probe_set


def make_crossed_world():
    cfg = WorldConfig(width=20, height=10, phase_ticks=5, n_phases=2, region_split=0.5)
    cfg.consume_effects[("S1", "A", 0)] = 8.0
    cfg.consume_effects[("S1", "A", 1)] = 8.0
    cfg.consume_effects[("S1", "B", 0)] = -5.0
    cfg.consume_effects[("S1", "B", 1)] = -5.0
    cfg.phase_barriers[(1, "B")] = True   # B-oscura: nunca vivida
    return WorldState(cfg, [Entity(eid="a0", kind="agent", x=2, y=2)], seed=1)


class ProbeFakeClient:
    """Responde predicciones correctas (agente que compuso las reglas)."""
    def __init__(self, mapping):
        self.mapping = mapping  # (rkind, region, phase) -> energy_change
        self.last_usage = {"prompt_tokens": 10, "completion_tokens": 5}
        self.calls = 0

    def chat_json(self, messages):
        self.calls += 1
        user = messages[-1]["content"]
        # extraer región y fase del prompt
        import re
        region = re.search(r"región ([AB])", user).group(1)
        phase = 1 if "oscura" in user else 0
        rkind = re.search(r"recurso '(\w+)'", user).group(1)
        return {"energy_change": self.mapping[(rkind, region, phase)]}

    def describe(self):
        return "fake:probe"


def test_ground_truth_effect():
    w = make_crossed_world()
    assert w.ground_truth_effect("S1", "A", 0) == 8.0
    assert w.ground_truth_effect("S1", "B", 0) == -5.0
    assert w.ground_truth_effect("S1", "B", 1) == -5.0


def test_never_lived_detection():
    w = make_crossed_world()
    probe = CompositionProbe(w, None, "/tmp/worldlab_probe", "t")
    assert probe._never_lived("B", 1) is True   # retenido
    assert probe._never_lived("A", 0) is False  # vivido
    assert probe._never_lived("B", 0) is False


def test_probe_set_records_all_cells(tmp_path):
    w = make_crossed_world()
    client = ProbeFakeClient({
        ("S1", "A", 0): 8.0, ("S1", "A", 1): 8.0,
        ("S1", "B", 0): -5.0, ("S1", "B", 1): -5.0,
    })
    agent = LLMAgent("a0", client, goal="sobrevivir")
    results = run_probe_set(w, agent, str(tmp_path), "probe_test")

    assert len(results) == 4
    by_cell = {(r["region"], r["phase"]): r for r in results}
    assert by_cell[("B", 1)]["never_lived"] is True
    assert by_cell[("A", 0)]["never_lived"] is False

    # el agente (que "compuso") acierta las 4, incluida la retenida
    assert all(r["sign_correct"] for r in results)
    assert by_cell[("B", 1)]["absolute_error"] == 0.0


def test_probe_writes_jsonl(tmp_path):
    w = make_crossed_world()
    client = ProbeFakeClient({
        ("S1", "A", 0): 8.0, ("S1", "A", 1): 8.0,
        ("S1", "B", 0): -5.0, ("S1", "B", 1): -5.0,
    })
    agent = LLMAgent("a0", client, goal="sobrevivir")
    run_probe_set(w, agent, str(tmp_path), "probe_write")
    path = Path(tmp_path) / "probe_write_probes.jsonl"
    lines = [json.loads(l) for l in open(path) if l.strip()]
    assert len(lines) == 4
    assert lines[0]["probe_type"] == "composition"


def test_probe_detects_agent_failure(tmp_path):
    """Un agente que NO compuso (responde +8 en todas) falla solo en B-oscura."""
    w = make_crossed_world()
    client = ProbeFakeClient({
        ("S1", "A", 0): 8.0, ("S1", "A", 1): 8.0,
        ("S1", "B", 0): 8.0, ("S1", "B", 1): 8.0,   # no aprendió B
    })
    agent = LLMAgent("a0", client, goal="sobrevivir")
    results = run_probe_set(w, agent, str(tmp_path), "probe_fail")
    by_cell = {(r["region"], r["phase"]): r for r in results}
    # acierta A-clara y A-oscura (regla A), falla B-clara y B-oscura
    assert by_cell[("A", 0)]["sign_correct"] is True
    assert by_cell[("B", 1)]["sign_correct"] is False   # la retenida delata
