"""Tests del baseline determinista y del runner (fase 0/1).

Exigencia de Opus: el baseline debe ser determinista, comparable, y la
optimización de parámetros debe correr en mundo de desarrollo (no contaminar
la corrida confirmatoria).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.world_state import WorldConfig, WorldState, Entity
from ai.baseline import BaselineParams, DeterministicAgent
from ai.simulate import Simulator, optimize_baseline, make_deterministic_policy
from ai.logger import read_jsonl


def make_config(days: int = 5, size: int = 12) -> WorldConfig:
    cfg = WorldConfig(width=size, height=size, days=days, ticks_per_day=8)
    cfg.energy_per_unit["food"] = 5.0
    return cfg


def make_agents(n: int = 3) -> list[Entity]:
    return [Entity(eid=f"a{i}", kind="agent", x=1, y=1 + i) for i in range(n)]


def test_deterministic_agent_decides():
    cfg = make_config()
    world = WorldState(cfg, make_agents(), seed=1)
    world.scatter_resources(10)
    agent = DeterministicAgent("a0", BaselineParams(), rng_seed=1)
    action, kwargs = agent.decide(world)
    assert action in {"move", "gather", "consume", "build", "rest"}


def test_deterministic_policy_deterministic():
    """Misma seed + misma política => mismas acciones (hash de estado igual)."""
    cfg = make_config(days=2)
    policy = make_deterministic_policy(BaselineParams())
    sim1 = Simulator(cfg, policy, "/tmp/worldlab_test", "det", log_interval=9999)
    sim2 = Simulator(cfg, policy, "/tmp/worldlab_test", "det", log_interval=9999)
    # ejecutar con el mismo seed: los eventos deben ser idénticos
    r1 = sim1.run(make_agents(), seed=7)
    r2 = sim2.run(make_agents(), seed=7)
    assert r1.to_dict() == r2.to_dict()


def test_simulator_runs_and_writes_jsonl(tmp_path):
    cfg = make_config(days=3)
    policy = make_deterministic_policy(BaselineParams())
    sim = Simulator(cfg, policy, str(tmp_path), "sim_test", log_interval=4)
    res = sim.run(make_agents(), seed=1)

    assert res.survivors >= 0
    assert res.total_actions_ok >= 0
    assert res.events_path.endswith(".jsonl")
    lines = read_jsonl(res.events_path)
    assert lines[0]["type"] == "meta"
    assert any(l["type"] == "event" for l in lines)
    assert any(l["type"] == "snapshot" for l in lines)


def test_simulator_survival_basic():
    """En un mundo con comida, el baseline debe sobrevivir los 3 días."""
    cfg = make_config(days=3, size=15)
    cfg.energy_per_tick = 0.3  # metabolismo suave
    cfg.energy_per_unit["food"] = 8.0
    policy = make_deterministic_policy(BaselineParams(eat_threshold=40.0))
    sim = Simulator(cfg, policy, "/tmp/worldlab_test", "surv", log_interval=9999)
    res = sim.run(make_agents(n=2), seed=1)
    assert res.survivors == 2, f"baseline no sobrevivió: {res.to_dict()}"


def test_optimize_baseline_returns_best():
    cfg = make_config(days=2, size=10)
    agents = make_agents(n=2)
    # grid pequeño de 4 combinaciones para test rápido
    grid = [
        {"eat_threshold": 20.0, "build_min": 4.0, "exploration": 0.05},
        {"eat_threshold": 40.0, "build_min": 8.0, "exploration": 0.3},
    ]
    best_params, best_score, results = optimize_baseline(
        cfg, agents, "/tmp/worldlab_test", "opt_test", param_grid=grid, n_seeds=2)
    assert len(results) == 2
    assert best_params in grid
    assert best_score == max(r["score"] for r in results)


def test_horizonte_no_congela_al_agente_al_cruzar_el_dia(tmp_path):
    """D-018: el horizonte se cuenta en ticks, y el reloj se reinicia cada día.

    BUG: next_think guardaba world.tick + horizonte contra un contador que
    world_state resetea a 0 al terminar el día (world_state.py:585-588). Un
    agente que pedía dormir 5 en el tick 6 de un día de 8 quedaba con
    next_think=11, valor que world.tick NUNCA alcanza — dormido de forma
    PERMANENTE, salvo que su energía cayera bajo wake_emergency_energy.

    Efecto medido en el piloto: el oráculo solo caminó (1.202 move, 0 consume)
    y las 3 condiciones LLM murieron. El baseline empírico no devuelve
    horizonte, así que nunca se congelaba: de ahí que sobreviviera solo él.
    """
    cfg = WorldConfig(width=8, height=8, days=3, ticks_per_day=8)
    cfg.energy_per_unit["food"] = 5.0
    despertares = []

    def policy(world, aid, tick, rng):
        despertares.append((world.day, world.tick))
        # pide dormir 5 SIEMPRE: cruza el fin del día a propósito
        return "rest", {}, None, 5

    sim = Simulator(cfg, policy, str(tmp_path), "horizonte", log_interval=99)
    sim.run([Entity(eid="a0", kind="agent", x=1, y=1)], seed=1)

    # 3 días × 8 ticks = 24 ticks, durmiendo 5 => ~5 despertares.
    # Con el bug: 2 (se congela al primer horizonte que cruza el día).
    assert len(despertares) >= 4, (
        f"agente congelado: solo {len(despertares)} despertares en 24 ticks "
        f"durmiendo 5 -> {despertares}")
    # y debe seguir despertando en los días 2 y 3, no solo en el primero
    assert {d for d, _ in despertares} >= {1, 2, 3}, \
        f"no despertó en todos los días: {sorted({d for d, _ in despertares})}"
