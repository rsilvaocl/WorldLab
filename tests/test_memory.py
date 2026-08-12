"""Tests de memoria literal y condición llm_memoria_corrupta (spec §4.3-4.4)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.world_state import WorldConfig, WorldState, Entity, Event
from ai.memory import LiteralMemory
from ai.llm_agent import LLMAgent
from ai.simulate import Simulator, make_llm_policy


class MemFakeClient:
    def __init__(self):
        self.last_usage = {"prompt_tokens": 10, "completion_tokens": 5}
        self.calls = 0

    def chat_json(self, messages):
        self.calls += 1
        return {"action": "rest", "args": {}, "sleep_ticks": 1}

    def describe(self):
        return "fake:mem"


def make_event(day=1, tick=1, action="consume", outcome="ok", region="A", phase=0,
               resource="S1", energy_gain=8.0) -> Event:
    return Event(day=day, tick=tick, eid="a0", action=action, outcome=outcome,
                 detail={"region": region, "phase": phase,
                         "resource": resource, "energy_gain": energy_gain})


# ---------------------------------------------------------------------------
# Memoria literal
# ---------------------------------------------------------------------------

def test_memory_records_literal_events():
    mem = LiteralMemory(max_items=10)
    mem.record(make_event())
    assert len(mem) == 1
    item = mem.items[0]
    # literal: sin interpretación, sin "aprendizaje"
    assert item["action"] == "consume"
    assert item["region"] == "A"
    assert item["phase"] == 0
    assert item["energy_gain"] == 8.0
    assert "learning" not in item and "conclusion" not in item


def test_memory_caps_at_max():
    mem = LiteralMemory(max_items=5)
    for i in range(10):
        mem.record(make_event(tick=i))
    assert len(mem) == 5
    assert mem.items[0]["tick"] == 5  # solo los últimos 5


def test_memory_render_returns_snapshot():
    mem = LiteralMemory(max_items=5)
    mem.record(make_event())
    rendered = mem.render()
    assert len(rendered) == 1
    assert rendered[0]["action"] == "consume"


# ---------------------------------------------------------------------------
# Condición corrupta: mismo volumen, hechos de otro seed
# ---------------------------------------------------------------------------

def test_corrupt_memory_same_volume():
    """La memoria corrupta tiene el MISMO volumen que la real (mismo largo,
    misma estructura) pero con hechos que el agente NO vivió."""
    real = LiteralMemory(max_items=60)
    for i in range(30):
        real.record(make_event(tick=i, region="A", energy_gain=8.0))

    # eventos de OTRO seed (mundo distinto): mismos registros, otros hechos
    other_seed_events = [make_event(tick=i, region="B", phase=1, energy_gain=-7.0)
                         for i in range(30)]
    corrupt = LiteralMemory.from_events(other_seed_events, max_items=60)

    assert len(corrupt) == len(real)                 # mismo volumen
    assert [k for k in corrupt.render()[0]] == [k for k in real.render()[0]]  # misma estructura
    assert corrupt.render()[0]["region"] == "B"      # hechos de otro seed
    assert real.render()[0]["region"] == "A"


def test_llm_agent_includes_memory_in_observation():
    client = MemFakeClient()
    mem = LiteralMemory(max_items=60)
    mem.record(make_event())
    agent = LLMAgent("a0", client, goal="sobrevivir", think_every=1,
                     hunger_threshold=100, memory=mem)
    cfg = WorldConfig(width=10, height=10)
    w = WorldState(cfg, [Entity(eid="a0", kind="agent", x=1, y=1)], seed=1)
    action, kwargs, trace, h = agent.decide(w)
    obs = trace["observation"]
    assert "memory" in obs
    assert obs["memory"][0]["action"] == "consume"


def test_llm_agent_without_memory_has_no_memory_field():
    client = MemFakeClient()
    agent = LLMAgent("a0", client, goal="sobrevivir", think_every=1, hunger_threshold=100)
    cfg = WorldConfig(width=10, height=10)
    w = WorldState(cfg, [Entity(eid="a0", kind="agent", x=1, y=1)], seed=1)
    action, kwargs, trace, h = agent.decide(w)
    assert "memory" not in trace["observation"]


def test_simulator_records_outcomes_into_memory(tmp_path):
    """El motor entrega el resultado real de cada acción a la memoria."""
    class ActingClient(MemFakeClient):
        def chat_json(self, messages):
            self.calls += 1
            return {"action": "move", "args": {"dx": 1, "dy": 0}, "sleep_ticks": 1}

    client = ActingClient()
    mem = LiteralMemory(max_items=60)
    agent = LLMAgent("a0", client, goal="sobrevivir", think_every=1,
                     hunger_threshold=100, memory=mem)
    llm_agents = {"a0": agent}
    policy = make_llm_policy(llm_agents)

    cfg = WorldConfig(width=10, height=10, days=2, ticks_per_day=4)
    cfg.energy_per_unit["S1"] = 8.0
    sim = Simulator(cfg, policy, str(tmp_path), "mem_test", log_interval=2,
                    agent_hooks=llm_agents)
    res = sim.run([Entity(eid="a0", kind="agent", x=1, y=1)], seed=1)

    assert len(mem) > 0
    # todos los registros son literales del motor
    assert all("tick" in i and "action" in i and "outcome" in i for i in mem.items)
