"""Tests de invariantes del motor WorldLab (fase 0).

Cubre los golden tests de física/mecánica que Opus marcó como innegociables:
  - determinismo: misma seed + misma secuencia de acciones => hash de estado idéntico
  - no-teletransporte: solo se mueve con validación y costo de energía
  - validación: fuera de límites, casillas bloqueadas, entidades inexistentes
  - conservación: la energía se gasta de forma determinista
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.world_state import WorldConfig, WorldState, Entity


def make_world(seed: int = 1) -> WorldState:
    cfg = WorldConfig(width=10, height=10, seed=seed)
    agents = [Entity(eid=f"a{i}", kind="agent", x=1, y=1 + i, attrs={"name": f"A{i}"})
              for i in range(2)]
    return WorldState(cfg, agents, seed=seed)


# ---------------------------------------------------------------------------
# Determinismo
# ---------------------------------------------------------------------------

def test_determinism_same_seed_same_hash():
    w1, w2 = make_world(seed=42), make_world(seed=42)
    for w in (w1, w2):
        w.move("a0", 1, 0)
        w.move("a1", 0, 1)
        w.advance_tick()
    assert w1.state_hash() == w2.state_hash()


def test_determinism_different_seed_different_hash():
    """Con estocasticidad real (scatter de recursos), seeds distintas
    producen mundos distintos => hash distinto."""
    w1, w2 = make_world(seed=1), make_world(seed=2)
    for w in (w1, w2):
        w.scatter_resources(20)
        w.advance_tick()
    assert w1.state_hash() != w2.state_hash()


def test_scatter_resources_same_seed_same_distribution():
    """Misma seed => misma distribución de recursos (reproducibilidad)."""
    w1, w2 = make_world(seed=5), make_world(seed=5)
    w1.scatter_resources(15)
    w2.scatter_resources(15)
    r1 = sorted((e.x, e.y) for e in w1.entities.values() if e.kind == "resource")
    r2 = sorted((e.x, e.y) for e in w2.entities.values() if e.kind == "resource")
    assert r1 == r2
    assert w1.state_hash() == w2.state_hash()


def test_determinism_same_seed_same_action_sequence():
    """La misma secuencia de acciones produce el mismo hash, sin importar
    el orden de registro interno (los eventos no afectan el estado)."""
    w1, w2 = make_world(seed=7), make_world(seed=7)
    for w in (w1, w2):
        w.move("a0", 2, 0)
        w.move("a0", 0, 2)
        w.move("a1", -1, 0)
        w.advance_tick()
        w.advance_tick()
    assert w1.state_hash() == w2.state_hash()


# ---------------------------------------------------------------------------
# No-teletransporte / validación de movimiento
# ---------------------------------------------------------------------------

def test_move_valid():
    w = make_world()
    ev = w.move("a0", 1, 0)
    assert ev.outcome == "ok"
    assert w.entities["a0"].pos() == (2, 1)


def test_move_out_of_bounds_rejected():
    w = make_world()
    w.entities["a0"].x = 9  # borde
    ev = w.move("a0", 1, 0)
    assert ev.outcome == "impossible"
    assert ev.detail["reason"] == "out_of_bounds"
    assert w.entities["a0"].pos() == (9, 1)  # no se movió


def test_move_blocked_rejected():
    w = make_world()
    # a1 está en (1,2); un objeto en (2,2) bloquea el paso de a1 hacia la derecha
    w._place(Entity(eid="obj", kind="object", x=2, y=2))
    ev = w.move("a1", 1, 0)
    assert ev.outcome == "impossible"
    assert ev.detail["reason"] == "blocked"
    assert w.entities["a1"].pos() == (1, 2)


def test_move_unknown_entity_rejected():
    w = make_world()
    ev = w.move("ghost", 1, 0)
    assert ev.outcome == "impossible"
    assert ev.detail["reason"] == "no_such_entity"


def test_no_energy_no_move():
    w = make_world()
    w.agents["a0"].energy = 0.5  # menos que move_energy (1.0)
    ev = w.move("a0", 1, 0)
    assert ev.outcome == "impossible"
    assert ev.detail["reason"] == "no_energy"


# ---------------------------------------------------------------------------
# Energía / metabolismo
# ---------------------------------------------------------------------------

def test_energy_consumed_on_move():
    w = make_world()
    before = w.agents["a0"].energy
    w.move("a0", 1, 0)
    assert w.agents["a0"].energy == before - w.config.move_energy


def test_tick_metabolism():
    w = make_world()
    before = w.agents["a0"].energy
    w.advance_tick()
    assert w.agents["a0"].energy == before - w.config.energy_per_tick
    assert w.tick == 1


def test_day_rollover():
    w = make_world()
    cfg = w.config
    for _ in range(cfg.ticks_per_day):
        w.advance_tick()
    assert w.day == 2
    assert w.tick == 0


# ---------------------------------------------------------------------------
# Percepción limitada
# ---------------------------------------------------------------------------

def test_visibility_radius():
    cfg = WorldConfig(width=20, height=20)
    w = WorldState(cfg, [
        Entity(eid="a0", kind="agent", x=10, y=10),
        Entity(eid="near", kind="resource", x=12, y=10),   # dentro de radio 4
        Entity(eid="far", kind="resource", x=18, y=10),    # fuera de radio 4
    ], seed=1)
    vis = w.visible_to("a0", radius=4)
    seen_ids = {v["eid"] for v in vis["visible"]}
    assert "near" in seen_ids
    assert "far" not in seen_ids
    # el agente NO ve el estado completo (solo su percepción)
    assert "agents" not in vis and "entities" not in vis
