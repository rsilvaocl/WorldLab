"""Tests de D-024: probe de salida al iniciar la inanición (spec v1.1 de Opus).

El piloto mostró que los agentes LLM morían antes del final (superv=0), así
que sus probes nunca corrían (0/0) y su conocimiento final se perdía.

D-024: cuando la energía llega a 0 y ARRANCA el contador de inanición
(starvation_ticks == 1), se dispara el callback on_starvation_start — ANTES
de que el agente desaparezca (muerte a los starvation_ticks). Ese es el
momento de capturar el estado de conocimiento final con un probe.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.world_state import WorldConfig, WorldState, Entity


def make_world(starvation_ticks=5) -> WorldState:
    cfg = WorldConfig(width=10, height=10, days=30, ticks_per_day=6,
                      energy_per_tick=1.0, starvation_ticks=starvation_ticks)
    w = WorldState(cfg, [Entity(eid="a0", kind="agent", x=1, y=1)], seed=1)
    return w


def test_hook_dispara_al_primer_tick_de_inanicion():
    w = make_world(starvation_ticks=5)
    w.agents["a0"].energy = 0.3  # el primer advance_tick lo deja en 0
    fired = []
    w.on_starvation_start = lambda aid, world: fired.append((aid, world.tick))
    # avanzar hasta que dispare
    for _ in range(3):
        w.advance_tick()
    assert len(fired) == 1, f"el hook debe disparar UNA vez, disparó {len(fired)}"
    aid, tick = fired[0]
    assert aid == "a0"
    # el agente sigue vivo en el primer tick de inanición (muerte a los 5)
    assert "a0" in w.agents


def test_hook_no_dispara_si_el_agente_recupera_energia():
    w = make_world(starvation_ticks=5)
    w.agents["a0"].energy = 0.3
    fired = []
    w.on_starvation_start = lambda aid, world: fired.append(aid)
    # primer tick: llega a 0 y dispara (starvation_ticks 0->1)
    w.advance_tick()
    assert fired == ["a0"]
    # el agente recupera energía (p.ej. consume): el contador se resetea
    w.agents["a0"].energy = 50.0
    w.advance_tick()
    assert w.agents["a0"].starvation_ticks == 0
    # vuelve a caer a 0: debe disparar OTRA vez (nuevo episodio)
    fired.clear()
    w.agents["a0"].energy = 0.1
    w.advance_tick()
    assert fired == ["a0"]


def test_hook_recibe_el_mundo_con_estado_visible():
    w = make_world(starvation_ticks=5)
    w.agents["a0"].energy = 0.3
    captured = {}
    def hook(aid, world):
        captured["aid"] = aid
        captured["day"] = world.day
        captured["tick"] = world.tick
        captured["agent_vivo"] = aid in world.agents
        captured["region"] = world.region(world.agents[aid].entity.x,
                                          world.agents[aid].entity.y)
    w.on_starvation_start = hook
    w.advance_tick()
    assert captured["agent_vivo"] is True
    assert captured["region"] in ("A", "B")


def test_sin_hook_el_mundo_sigue_funcionando():
    """El callback es opcional: sin registrar, no cambia el comportamiento."""
    w = make_world(starvation_ticks=3)
    w.agents["a0"].energy = 0.1
    for _ in range(10):
        w.advance_tick()
    # el agente muere a los 3 ticks de inanición como siempre
    assert "a0" not in w.agents


def test_hook_excepcion_no_tumba_el_mundo():
    """Si el probe falla, el mundo sigue (defensa en profundidad)."""
    w = make_world(starvation_ticks=5)
    w.agents["a0"].energy = 0.3
    def boom(aid, world):
        raise RuntimeError("probe exploded")
    w.on_starvation_start = boom
    for _ in range(2):
        w.advance_tick()  # no debe crashear
    assert "a0" in w.agents
