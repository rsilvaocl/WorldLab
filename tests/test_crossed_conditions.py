"""Tests de condiciones cruzadas: ciclo de fases, barreras por (fase, región)
y efectos de consumo por (recurso, región, fase) — infraestructura para el
diseño de dos condiciones con cruce retenido (Opus, cuarta decisión).

El escenario canónico:
  - Región A: consumir ▲ da energía (+8).  Región B: consumir ▲ enferma (-5).
  - Fase clara (0) y oscura (1) alternan cada phase_ticks.
  - Barrera: región B inaccesible durante fase oscura.
  El agente vive A-clara, A-oscura, B-clara — nunca B-oscura.
  La pregunta de composición ("¿▲ en B-oscura?") solo se responde bien
  componiendo las dos reglas. Eso lo probará el experimento, no el motor.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.world_state import WorldConfig, WorldState, Entity, \
    build_separable_effects, separable_invariant_holds


def make_crossed_world(phase_ticks: int = 5) -> WorldState:
    cfg = WorldConfig(width=20, height=10, phase_ticks=phase_ticks, n_phases=2,
                      region_split=0.5)
    # ▲ = "S1": da energía en A (fase 0 y 1), enferma en B (fase 0 y 1)
    cfg.consume_effects[("S1", "A", 0)] = 8.0
    cfg.consume_effects[("S1", "A", 1)] = 8.0
    cfg.consume_effects[("S1", "B", 0)] = -5.0
    cfg.consume_effects[("S1", "B", 1)] = -5.0
    # barrera: B bloqueada en fase oscura (1)
    cfg.phase_barriers[(1, "B")] = True
    w = WorldState(cfg, [Entity(eid="a0", kind="agent", x=2, y=2)], seed=1)
    w.agents["a0"].inventory["S1"] = 5.0
    return w


def test_phase_cycle_advances():
    w = make_crossed_world(phase_ticks=5)
    assert w.phase() == 0
    w.tick = 5   # siguiente fase
    assert w.phase() == 1
    w.tick = 10
    assert w.phase() == 0  # vuelve al inicio


def test_no_phase_cycle_when_disabled():
    cfg = WorldConfig(width=10, height=10)
    w = WorldState(cfg, [Entity(eid="a0", kind="agent", x=1, y=1)], seed=1)
    w.tick = 999
    assert w.phase() == 0


def test_region_split():
    w = make_crossed_world()
    assert w.region(2, 5) == "A"    # x < 10
    assert w.region(15, 5) == "B"   # x >= 10


def test_barrier_blocks_entry_in_blocked_phase():
    w = make_crossed_world()
    # a0 en (2,2) región A, fase 0 (clara): puede entrar a B
    w.entities["a0"].x = 8   # cerca del borde (región A aún: x=8 < 10)
    ev = w.move("a0", 1, 0)  # a (9,2) aún A — ok
    assert ev.outcome == "ok"
    ev = w.move("a0", 1, 0)  # a (10,2) región B, fase clara — permitido
    assert ev.outcome == "ok"
    # fase oscura: B bloqueada — no se puede ENTRAR
    w.tick = 5
    w.entities["a0"].x = 9
    ev = w.move("a0", 1, 0)  # a (10,2) B en fase oscura — bloqueado
    assert ev.outcome == "impossible"
    assert ev.detail["reason"] == "blocked_by_phase"
    # no se movió
    assert w.entities["a0"].x == 9


def test_exit_from_blocked_region_allowed():
    """Si el agente quedó dentro de B al cambiar la fase, puede SALIR."""
    w = make_crossed_world()
    w.entities["a0"].x = 12  # dentro de B
    w.tick = 5               # fase oscura, B bloqueada
    # moverse dentro de B: permitido (la barrera impide entrar, no congelar)
    ev = w.move("a0", -1, 0) # 12 -> 11, sigue en B
    assert ev.outcome == "ok"
    assert w.entities["a0"].x == 11
    # salir de B hacia A: permitido (A no está bloqueada)
    w.entities["a0"].x = 10
    ev = w.move("a0", -1, 0) # 10 -> 9 (A)
    assert ev.outcome == "ok"
    assert w.entities["a0"].x == 9


def test_consume_crossed_effect():
    w = make_crossed_world()
    # en A (x=2): +8 (energía baja para no chocar con el cap de 100)
    w.agents["a0"].energy = 50.0
    before = w.agents["a0"].energy
    ev = w.consume("a0", "S1", amount=1.0)
    assert ev.outcome == "ok"
    assert ev.detail["energy_gain"] == 8.0
    assert w.agents["a0"].energy == before + 8.0
    # en B (x=12): -5
    w.agents["a0"].inventory["S1"] = 5.0
    w.entities["a0"].x = 12
    before = w.agents["a0"].energy
    ev = w.consume("a0", "S1", amount=1.0)
    assert ev.outcome == "ok"
    assert ev.detail["energy_gain"] == -5.0
    assert w.agents["a0"].energy == before - 5.0


def test_consume_flat_when_no_crossed_effect():
    cfg = WorldConfig(width=10, height=10)
    cfg.energy_per_unit["S1"] = 4.0
    w = WorldState(cfg, [Entity(eid="a0", kind="agent", x=1, y=1)], seed=1)
    w.agents["a0"].inventory["S1"] = 3.0
    before = w.agents["a0"].energy
    ev = w.consume("a0", "S1", amount=1.0)
    assert ev.outcome == "ok"
    assert ev.detail["energy_gain"] == 4.0


def test_perception_includes_region_and_phase():
    """El agente percibe fase y región — sin eso no puede aprender la regla
    cruzada (condición necesaria del world modeling)."""
    w = make_crossed_world()
    vis = w.visible_to("a0", radius=4)
    assert "region" in vis and vis["region"] == "A"
    assert "phase" in vis and vis["phase"] == 0


# ---------------------------------------------------------------------------
# Separabilidad (exigencia de Opus: la celda retenida debe ser derivable)
# ---------------------------------------------------------------------------

def make_separable_config():
    cfg = WorldConfig(width=20, height=10, phase_ticks=5, n_phases=2, region_split=0.5)
    cfg.consume_effects = build_separable_effects(
        base={"S1": 5.0, "S2": 3.0},
        delta_region={"S1": {"B": -8.0}, "S2": {"B": 2.0}},
        delta_phase={"S1": {1: -3.0}, "S2": {1: 4.0}},
    )
    cfg.phase_barriers[(1, "B")] = True
    return cfg


def test_separable_effects_generate_all_cells():
    cfg = make_separable_config()
    eff = cfg.consume_effects
    # S1: base 5; A-clara = 5; A-oscura = 5-3 = 2; B-clara = 5-8 = -3; B-oscura = 5-8-3 = -6
    assert eff[("S1", "A", 0)] == 5.0
    assert eff[("S1", "A", 1)] == 2.0
    assert eff[("S1", "B", 0)] == -3.0
    assert eff[("S1", "B", 1)] == -6.0
    # B-oscura derivable: A-oscura + (B-clara − A-clara) = 2 + (-3 - 5) = -6
    assert eff[("S1", "B", 1)] == eff[("S1", "A", 1)] + (eff[("S1", "B", 0)] - eff[("S1", "A", 0)])


def test_separable_invariant_holds():
    cfg = make_separable_config()
    assert separable_invariant_holds(cfg.consume_effects) is True


def test_separable_invariant_detects_hand_tuned_break():
    """Si alguien edita UNA celda a mano (p.ej. B-oscura = +12), el invariante
    se rompe y el test de composición deja de significar nada."""
    cfg = make_separable_config()
    cfg.consume_effects[("S1", "B", 1)] = 12.0   # hecho suelto, no componible
    assert separable_invariant_holds(cfg.consume_effects) is False


def test_phase_has_own_effect():
    """La fase necesita efecto propio (δ_fase ≠ 0) en al menos dos recursos;
    si la fase solo controla la barrera, B-oscura == B-clara y no hay segunda
    regla que componer."""
    cfg = make_separable_config()
    eff = cfg.consume_effects
    resources_with_phase_effect = [
        r for r in ("S1", "S2")
        if eff[(r, "A", 0)] != eff[(r, "A", 1)]
    ]
    assert len(resources_with_phase_effect) >= 2


# ---------------------------------------------------------------------------
# Expulsión de regiones bloqueadas (crítica de Opus: nadie puede vivir B-oscura)
# ---------------------------------------------------------------------------

def test_expulsion_when_phase_changes():
    """Un agente en B al llegar la fase oscura es expulsado a la celda libre
    más cercana en región no bloqueada — NO puede vivir la celda retenida."""
    w = make_crossed_world()
    w.entities["a0"].x = 15   # dentro de B
    # avanza ticks hasta entrar en fase oscura (phase_ticks=5)
    for _ in range(5):
        w.advance_tick()
    assert w.phase() == 1
    # a0 ya no está en B
    assert w.region(w.entities["a0"].x, w.entities["a0"].y) == "A"
    # quedó registrado el evento expelled
    expelled = [e for e in w.events if e.action == "expelled"]
    assert len(expelled) >= 1


def test_no_heldout_consumption_after_expulsion():
    """Red de detección: tras la expulsión, NINGÚN consume ok ocurre en la
    celda retenida (B-oscura) durante la simulación."""
    w = make_crossed_world()
    # colocar al agente en B y simular varios ciclos completos de fase
    w.entities["a0"].x = 15
    w.agents["a0"].inventory["S1"] = 50.0
    for _ in range(30):
        # consumir cuando tenga hambre (siempre: energía baja)
        if w.agents["a0"].energy < 30:
            w.consume("a0", "S1", amount=1.0)
        w.advance_tick()
    assert w.no_heldout_consumption() is True


def test_heldout_detector_catches_manual_violation():
    """La red de detección FALLA si alguien fuerza un consume en B-oscura
    (por ejemplo, bypass manual) — el test de composición estaría contaminado."""
    w = make_crossed_world()
    w.tick = 5   # fase oscura
    w.entities["a0"].x = 15  # B
    w.agents["a0"].inventory["S1"] = 5.0
    w.consume("a0", "S1", amount=1.0)   # forzado: vive la celda retenida
    assert w.no_heldout_consumption() is False
