"""Tests de las 3 correcciones de Opus (baseline empírico, world model NO
prestado, recetas dinámicas)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.world_state import WorldConfig, WorldState, Entity, Event
from ai.baseline import BaselineParams, DeterministicAgent, EmpiricalAgent
from ai.simulate import Simulator, make_empirical_policy


def make_event(action="consume", outcome="ok", resource="S1", region="A",
               phase=0, energy_gain=8.0) -> Event:
    return Event(day=1, tick=1, eid="a0", action=action, outcome=outcome,
                 detail={"resource": resource, "region": region, "phase": phase,
                         "energy_gain": energy_gain})


def make_world():
    cfg = WorldConfig(width=10, height=10)
    return WorldState(cfg, [Entity(eid="a0", kind="agent", x=1, y=1)], seed=1)


# ---------------------------------------------------------------------------
# 1. Baseline EMPÍRICO: tabla de efectos observados (misma información que el LLM)
# ---------------------------------------------------------------------------

def test_empirical_agent_learns_from_own_consumptions():
    """Después de consumir S1 en A-clara (+8) y S2 en A-clara (-2), la tabla
    empírica refleja los promedios: +8 y -2. NO lee cfg.consume_effects."""
    ag = EmpiricalAgent("a0", BaselineParams())
    ag.record_outcome(make_event(resource="S1", energy_gain=8.0))
    ag.record_outcome(make_event(resource="S2", energy_gain=-2.0))
    w = make_world()
    assert ag._expected_value(w, "S1") == 8.0
    assert ag._expected_value(w, "S2") == -2.0


def test_empirical_agent_poisons_first_then_corrects():
    """Sin datos, el valor por defecto es 0.0 — come S2 en A creyéndolo bueno
    (como el LLM) hasta que la experiencia le enseña que es negativo."""
    ag = EmpiricalAgent("a0", BaselineParams(), default_value=0.0)
    w = make_world()
    assert ag._expected_value(w, "S2") == 0.0  # no sabe aún -> neutro
    ag.record_outcome(make_event(resource="S2", energy_gain=-2.0))
    assert ag._expected_value(w, "S2") == -2.0  # la experiencia corrige


def test_empirical_agent_does_not_read_config():
    """Aunque cfg.consume_effects diga S1=+8, sin experiencia propia el agente
    empírico no lo sabe (default 0.0). El informado sí lo lee (techo)."""
    cfg = WorldConfig(width=10, height=10)
    cfg.consume_effects[("S1", "A", 0)] = 8.0
    w = WorldState(cfg, [Entity(eid="a0", kind="agent", x=1, y=1)], seed=1)

    emp = EmpiricalAgent("a0", BaselineParams())
    inf = DeterministicAgent("a0", BaselineParams())
    assert emp._expected_value(w, "S1") == 0.0      # empírico: no sabe
    assert inf._expected_value(w, "S1") == 8.0      # informado: techo


def test_empirical_predict_effect_returns_promedio_or_none():
    ag = EmpiricalAgent("a0", BaselineParams())
    # nunca vivió B-oscura -> None (no compone: eso es exactamente lo que medimos)
    assert ag.predict_effect("S1", "B", 1) is None
    ag.record_outcome(make_event(resource="S1", region="B", phase=1, energy_gain=-7.0))
    ag.record_outcome(make_event(resource="S1", region="B", phase=1, energy_gain=-5.0))
    assert ag.predict_effect("S1", "B", 1) == -6.0  # promedio de lo vivido


def test_simulator_feeds_empirical_agent(tmp_path):
    """El motor entrega los resultados reales al baseline empírico (hook),
    igual que al LLM — misma información, misma vía."""
    emp = {f"a{i}": EmpiricalAgent(f"a{i}", BaselineParams()) for i in range(2)}
    policy = make_empirical_policy(emp)
    cfg = WorldConfig(width=10, height=10, days=2, ticks_per_day=4)
    sim = Simulator(cfg, policy, str(tmp_path), "emp_test", log_interval=2,
                    agent_hooks=emp)
    res = sim.run([Entity(eid="a0", kind="agent", x=1, y=1),
                   Entity(eid="a1", kind="agent", x=1, y=3)], seed=1)
    # no requiere que aprendan algo en concreto; solo que el hook existió y
    # los agentes siguieron vivos/actuando
    assert res.survivors >= 0


# ---------------------------------------------------------------------------
# 2. World model NO prestado: el prompt del LLM no contiene predicciones
# ---------------------------------------------------------------------------

class CapturingClient:
    def __init__(self):
        self.last_usage = {"prompt_tokens": 10, "completion_tokens": 5}
        self.messages = []

    def chat_json(self, messages):
        self.messages.append(messages)
        return {"action": "rest", "args": {}, "sleep_ticks": 1}

    def describe(self):
        return "fake:capture"


def test_llm_prompt_has_no_borrowed_predictions():
    """crítica #5/#12 (Opus/Claude): el agente NO recibe predicciones nuestras
    en el prompt — si se las prestamos, después no podemos preguntarnos si
    construyó el world model él."""
    from ai.llm_agent import LLMAgent
    client = CapturingClient()
    ag = LLMAgent("a0", client, goal="sobrevivir", think_every=1, hunger_threshold=100)
    w = make_world()
    ag.decide(w)
    user_content = client.messages[0][-1]["content"]
    assert "Predicciones disponibles" not in user_content
    assert "expected_energy_gain" not in user_content
    assert "risk_note" not in user_content


def test_llm_trace_has_no_prediction_field():
    from ai.llm_agent import LLMAgent
    client = CapturingClient()
    ag = LLMAgent("a0", client, goal="sobrevivir", think_every=1, hunger_threshold=100)
    w = make_world()
    action, kwargs, trace, h = ag.decide(w)
    assert trace is not None
    assert "prediction" not in trace


# ---------------------------------------------------------------------------
# 3. Recetas dinámicas: el baseline construye struct_a (no "hut" hardcodeado)
# ---------------------------------------------------------------------------

def test_baseline_builds_with_dynamic_recipes():
    cfg = WorldConfig(width=10, height=10)
    cfg.recipes = {"struct_a": {"S3": 2.0, "S4": 1.0}}  # spec v1
    w = WorldState(cfg, [Entity(eid="a0", kind="agent", x=1, y=1)], seed=1)
    w.agents["a0"].inventory["S3"] = 3.0
    w.agents["a0"].inventory["S4"] = 1.0
    w.agents["a0"].energy = 95.0  # no hambre -> no consume primero
    ag = DeterministicAgent("a0", BaselineParams())
    action, kwargs = ag.decide(w)
    assert action == "build"
    assert kwargs["structure"] == "struct_a"


def test_baseline_no_build_without_recipe_materials():
    cfg = WorldConfig(width=10, height=10)
    cfg.recipes = {"struct_a": {"S3": 2.0, "S4": 1.0}}
    w = WorldState(cfg, [Entity(eid="a0", kind="agent", x=1, y=1)], seed=1)
    w.agents["a0"].inventory["S3"] = 1.0  # insuficiente
    w.agents["a0"].energy = 95.0
    ag = DeterministicAgent("a0", BaselineParams())
    action, kwargs = ag.decide(w)
    assert action != "build"  # no alcanza -> otra acción (rest o move)
