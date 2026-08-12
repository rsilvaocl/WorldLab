"""Tests de acciones económicas del motor WorldLab (fase 0).

Cubre: gather (recolectar), consume (comer/beber), drop/pickup (soltar/tomar),
give (transferir), build (construir), talk (comunicar con costo).
Todas las primitivas son FÍSICAS — no existe trade() (crítica #2 de Claude).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.world_state import WorldConfig, WorldState, Entity


def make_econ_world() -> WorldState:
    cfg = WorldConfig(width=10, height=10)
    cfg.energy_per_unit["food"] = 5.0
    w = WorldState(cfg, [
        Entity(eid="a0", kind="agent", x=1, y=1),
        Entity(eid="a1", kind="agent", x=3, y=1),
    ], seed=1)
    w._place(Entity(eid="res_food", kind="resource", x=2, y=1, attrs={"kind": "food", "amount": 10.0}))
    return w


# ---------------------------------------------------------------------------
# gather
# ---------------------------------------------------------------------------

def test_gather_ok():
    w = make_econ_world()
    ev = w.gather("a0", "res_food", amount=3.0)
    assert ev.outcome == "ok"
    assert w.agents["a0"].inventory["food"] == 3.0
    assert w.entities["res_food"].attrs["amount"] == 7.0


def test_gather_not_adjacent():
    w = make_econ_world()
    ev = w.gather("a1", "res_food", amount=1.0)  # a1 está en (3,1), recurso en (2,1) — distancia 1, adyacente!
    assert ev.outcome == "ok"
    ev = w.gather("a0", "res_food", amount=1.0)
    assert ev.outcome == "ok"


def test_gather_depleted():
    w = make_econ_world()
    w.entities["res_food"].attrs["amount"] = 0.0
    ev = w.gather("a0", "res_food", amount=1.0)
    assert ev.outcome == "impossible"
    assert ev.detail["reason"] == "depleted"


def test_gather_non_resource():
    w = make_econ_world()
    w._place(Entity(eid="obj", kind="object", x=1, y=2))
    ev = w.gather("a0", "obj", amount=1.0)
    assert ev.outcome == "impossible"
    assert ev.detail["reason"] == "not_a_resource"


# ---------------------------------------------------------------------------
# consume
# ---------------------------------------------------------------------------

def test_consume_gains_energy():
    w = make_econ_world()
    w.agents["a0"].inventory["food"] = 10.0
    before = w.agents["a0"].energy
    ev = w.consume("a0", "food", amount=2.0)
    assert ev.outcome == "ok"
    assert w.agents["a0"].energy == min(before + 10.0, 100.0)
    assert w.agents["a0"].inventory["food"] == 8.0


def test_consume_not_enough():
    w = make_econ_world()
    w.agents["a0"].inventory["food"] = 1.0
    ev = w.consume("a0", "food", amount=5.0)
    assert ev.outcome == "impossible"
    assert ev.detail["reason"] == "not_enough"


# ---------------------------------------------------------------------------
# drop / pickup
# ---------------------------------------------------------------------------

def test_drop_creates_ground_resource():
    w = make_econ_world()
    w.agents["a0"].inventory["food"] = 5.0
    ev = w.drop("a0", "food", amount=3.0)
    assert ev.outcome == "ok"
    assert w.agents["a0"].inventory["food"] == 2.0
    dropped = [e for e in w.entities.values() if e.kind == "resource" and e.attrs.get("owner_dropped") == "a0"]
    assert len(dropped) == 1
    assert dropped[0].attrs["amount"] == 3.0
    assert dropped[0].pos() == (1, 1)  # en la celda del agente


def test_pickup_from_ground():
    w = make_econ_world()
    w.agents["a0"].inventory["food"] = 5.0
    w.drop("a0", "food", amount=3.0)
    w.agents["a0"].inventory["food"] = 0.0  # vacía inventario
    dropped = [e for e in w.entities.values() if e.attrs.get("owner_dropped") == "a0"][0]
    ev = w.pickup("a0", dropped.eid)
    assert ev.outcome == "ok"
    assert w.agents["a0"].inventory["food"] == 3.0
    assert dropped.eid not in w.entities  # recurso agotado se elimina


def test_give_transfers():
    w = make_econ_world()
    w.agents["a0"].inventory["food"] = 10.0
    ev = w.give("a0", "a1", "food", amount=4.0)  # a0 (1,1) y a1 (3,1) no adyacentes — distancia 2
    assert ev.outcome == "impossible"
    assert ev.detail["reason"] == "not_adjacent"


def test_give_ok_when_adjacent():
    w = make_econ_world()
    w.agents["a0"].inventory["food"] = 10.0
    # mover a1 junto a a0
    w.entities["a1"].x = 2
    w.entities["a1"].y = 1
    ev = w.give("a0", "a1", "food", amount=4.0)
    assert ev.outcome == "ok"
    assert w.agents["a0"].inventory["food"] == 6.0
    assert w.agents["a1"].inventory["food"] == 4.0


def test_give_not_enough():
    w = make_econ_world()
    w.agents["a0"].inventory["food"] = 1.0
    w.entities["a1"].x = 2
    w.entities["a1"].y = 1
    ev = w.give("a0", "a1", "food", amount=5.0)
    assert ev.outcome == "impossible"


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------

def test_build_consumes_materials():
    w = make_econ_world()
    w.agents["a0"].inventory["wood"] = 4.0
    w.agents["a0"].inventory["stone"] = 2.0
    ev = w.build("a0", "hut", x=1, y=2, materials={"wood": 3.0, "stone": 1.0})
    assert ev.outcome == "ok"
    assert w.agents["a0"].inventory["wood"] == 1.0
    assert w.agents["a0"].inventory["stone"] == 1.0
    huts = [e for e in w.entities.values() if e.attrs.get("structure") == "hut"]
    assert len(huts) == 1


def test_build_missing_material():
    w = make_econ_world()
    w.agents["a0"].inventory["wood"] = 1.0
    ev = w.build("a0", "hut", x=1, y=2, materials={"wood": 3.0})
    assert ev.outcome == "impossible"
    assert ev.detail["reason"] == "missing_material"


def test_build_cell_occupied():
    w = make_econ_world()
    w.agents["a0"].inventory["wood"] = 5.0
    w._place(Entity(eid="obj", kind="object", x=1, y=2))
    ev = w.build("a0", "hut", x=1, y=2, materials={"wood": 3.0})
    assert ev.outcome == "impossible"
    assert ev.detail["reason"] == "cell_occupied"


# ---------------------------------------------------------------------------
# talk (comunicación con costo)
# ---------------------------------------------------------------------------

def test_talk_ok_and_costs_energy():
    w = make_econ_world()
    before = w.agents["a0"].energy
    ev = w.talk("a0", "hierro al norte")
    assert ev.outcome == "ok"
    assert w.agents["a0"].energy == before - 1.0
    assert ev.detail["message"] == "hierro al norte"


def test_talk_empty_rejected():
    w = make_econ_world()
    ev = w.talk("a0", "")
    assert ev.outcome == "impossible"


def test_talk_no_energy():
    w = make_econ_world()
    w.agents["a0"].energy = 0.5
    ev = w.talk("a0", "hola")
    assert ev.outcome == "impossible"
    assert ev.detail["reason"] == "no_energy"
