"""Tests del Model Adapter y agente LLM (fase 2) con cliente simulado."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.world_state import WorldConfig, WorldState, Entity
from ai.model_adapter import LLMClient, ModelError
from ai.llm_agent import LLMAgent, VALID_ACTIONS
from ai.simulate import Simulator, make_llm_policy


class FakeClient:
    """Cliente simulado: responde un JSON fijo y cuenta llamadas."""
    def __init__(self, response: dict | None = None):
        self.response = response or {"action": "gather", "args": {"target_eid": "res_food", "amount": 1.0}}
        self.calls = 0
        self.last_usage = {"prompt_tokens": 50, "completion_tokens": 10}

    def chat_json(self, messages):
        self.calls += 1
        return self.response

    def describe(self):
        return "fake:test"


def make_world() -> WorldState:
    cfg = WorldConfig(width=10, height=10, days=2, ticks_per_day=6)
    cfg.energy_per_unit["food"] = 8.0
    w = WorldState(cfg, [Entity(eid="a0", kind="agent", x=1, y=1)], seed=1)
    w._place(Entity(eid="res_food", kind="resource", x=2, y=1,
                    attrs={"kind": "food", "amount": 10.0}))
    return w


# ---------------------------------------------------------------------------
# Model Adapter
# ---------------------------------------------------------------------------

def test_extract_json_plain():
    assert LLMClient._extract_json('{"action": "move"}') == {"action": "move"}


def test_extract_json_with_markdown():
    assert LLMClient._extract_json('```json\n{"action": "move", "args": {"dx": 1}}\n```') == \
        {"action": "move", "args": {"dx": 1}}


def test_extract_json_with_noise():
    assert LLMClient._extract_json('Aquí va mi decisión: {"action": "rest"} fin.') == \
        {"action": "rest"}


def test_extract_json_invalid():
    try:
        LLMClient._extract_json("no hay json aquí")
        assert False, "debió lanzar ModelError"
    except ModelError:
        pass


def test_llm_client_rejects_bad_backend():
    try:
        LLMClient(backend="nope")
        assert False
    except ModelError:
        pass


# ---------------------------------------------------------------------------
# Agente LLM
# ---------------------------------------------------------------------------

def test_llm_agent_decides_valid_action():
    client = FakeClient()
    agent = LLMAgent("a0", client, goal="sobrevivir", think_every=1, hunger_threshold=100)
    world = make_world()
    action, kwargs, trace, horizonte = agent.decide(world)
    assert action == "gather"
    assert kwargs["target_eid"] == "res_food"
    assert trace is not None
    assert trace["proposed_action"]["action"] == "gather"


def test_llm_agent_rejects_invalid_action():
    client = FakeClient(response={"action": "fly", "args": {}})
    agent = LLMAgent("a0", client, goal="sobrevivir", think_every=1, hunger_threshold=100)
    world = make_world()
    action, kwargs, trace, horizonte = agent.decide(world)
    assert action == "rest"  # acción inválida -> descansa


def test_llm_agent_only_thinks_when_triggered():
    client = FakeClient()
    agent = LLMAgent("a0", client, goal="sobrevivir", think_every=999, hunger_threshold=0)
    world = make_world()
    # sin hambre, sin agente cerca, tick 0 no es múltiplo de 999... tick 0 % 999 == 0 => piensa
    action, kwargs, trace, horizonte = agent.decide(world)
    assert trace is not None
    # mover a tick 1 con energía alta -> no piensa
    world.tick = 1
    action2, kwargs2, trace2, h2 = agent.decide(world)
    assert action2 == "rest"
    assert trace2 is None


def test_llm_agent_hunger_trigger():
    client = FakeClient()
    agent = LLMAgent("a0", client, goal="sobrevivir", think_every=999, hunger_threshold=50)
    world = make_world()
    world.agents["a0"].energy = 10.0  # hambre
    action, kwargs, trace, horizonte = agent.decide(world)
    assert trace is not None
    assert trace["reason"] == "hambre"


def test_llm_agent_horizonte_parsed():
    """D-018: el agente declara sleep_ticks; se registra en el trace y el motor lo respeta."""
    client = FakeClient(response={"action": "rest", "args": {}, "sleep_ticks": 24})
    agent = LLMAgent("a0", client, goal="sobrevivir", think_every=1, hunger_threshold=100)
    world = make_world()
    action, kwargs, trace, horizonte = agent.decide(world)
    assert horizonte == 24
    assert trace["sleep_ticks"] == 24


def test_llm_agent_horizonte_invalid_clamped():
    client = FakeClient(response={"action": "rest", "args": {}, "sleep_ticks": 500})
    agent = LLMAgent("a0", client, goal="sobrevivir", think_every=1, hunger_threshold=100)
    world = make_world()
    action, kwargs, trace, horizonte = agent.decide(world)
    assert horizonte == 96  # clamp


# ---------------------------------------------------------------------------
# Simulador con política LLM
# ---------------------------------------------------------------------------

def test_simulator_with_llm_policy(tmp_path):
    client = FakeClient()
    agent = LLMAgent("a0", client, goal="sobrevivir", think_every=1, hunger_threshold=100)
    llm_agents = {"a0": agent}
    policy = make_llm_policy(llm_agents)

    cfg = WorldConfig(width=10, height=10, days=2, ticks_per_day=6)
    cfg.energy_per_unit["food"] = 8.0
    sim = Simulator(cfg, policy, str(tmp_path), "llm_test", log_interval=3)
    res = sim.run([Entity(eid="a0", kind="agent", x=1, y=1)], seed=1)

    assert res.events_path.endswith(".jsonl")
    # el trace_logger debe haber escrito traces (el agente pensó)
    from ai.logger import read_jsonl
    traces = read_jsonl(res.trace_path)
    assert any(l["type"] == "trace" for l in traces)
    assert client.calls > 0
