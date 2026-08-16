"""Tests de D-026: acciones disponibles en la observación (spec v1.1 de Opus).

El motor expone `available_actions(eid)`: SOLO acciones que el validador
aceptaría en este instante, con argumentos ya rellenados. NO presta world
model (no revela efectos) — solo los botones que existen.

Reglas verificadas aquí:
- move: solo direcciones que pasan can_move
- gather: solo recursos a distancia <= 1 con cantidad disponible
- pickup: solo recursos DROPEADOS a distancia <= 1
- consume/drop: solo rkinds presentes en el inventario
- give: solo agentes adyacentes × recursos que tiene
- build: solo recetas con materiales suficientes en celdas adyacentes libres
- talk: solo si hay energía
- rest: siempre disponible
- La observación del LLMAgent incluye acciones_disponibles (D-026)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.world_state import WorldConfig, WorldState, Entity
from ai.llm_agent import LLMAgent


class FakeClient:
    def __init__(self, response=None):
        self.response = response or {"action": "rest", "args": {}, "sleep_ticks": 1}
        self.calls = 0
        self.last_usage = {"prompt_tokens": 50, "completion_tokens": 10}

    def chat_json(self, messages):
        self.calls += 1
        return self.response

    def describe(self):
        return "fake:test"


def make_world() -> WorldState:
    cfg = WorldConfig(width=10, height=10, days=2, ticks_per_day=6)
    cfg.energy_per_unit["S1"] = 8.0
    cfg.recipes = {"struct_a": {"S3": 2.0, "S4": 1.0}}
    w = WorldState(cfg, [Entity(eid="a0", kind="agent", x=1, y=1)], seed=1)
    # recurso adyacente (x=2,y=1) con cantidad
    w._place(Entity(eid="e_0001", kind="resource", x=2, y=1,
                    attrs={"kind": "S1", "amount": 10.0}))
    # recurso lejano (x=8,y=8) — NO debe aparecer en gather
    w._place(Entity(eid="e_0002", kind="resource", x=8, y=8,
                    attrs={"kind": "S1", "amount": 5.0}))
    # recurso agotado adyacente — NO debe aparecer
    w._place(Entity(eid="e_0003", kind="resource", x=1, y=2,
                    attrs={"kind": "S1", "amount": 0.0}))
    # recurso dropeado en la misma celda del agente (1,1) — es recurso
    # adyacente (distancia 0 <= 1): gather también lo acepta (consistente
    # con el fix "gather distancia <= 1"); pickup es la vía alternativa.
    w._place(Entity(eid="e_0004", kind="resource", x=1, y=1,
                    attrs={"kind": "S2", "amount": 3.0, "owner_dropped": "a9"}))
    # otro agente adyacente (x=1,y=0)
    w._place(Entity(eid="a1", kind="agent", x=1, y=0))
    # bloqueo en (0,1): pared no-recurso para probar can_move
    w._place(Entity(eid="wall", kind="object", x=0, y=1, attrs={"structure": "wall"}))
    return w


def acts_of(actions, name):
    return [a for a in actions if a["action"] == name]


def test_rest_siempre_disponible():
    w = make_world()
    acts = w.available_actions("a0")
    assert any(a["action"] == "rest" for a in acts)


def test_move_solo_direcciones_validas():
    w = make_world()
    acts = acts_of(w.available_actions("a0"), "move")
    dirs = {(a["args"]["dx"], a["args"]["dy"]) for a in acts}
    # a0 en (1,1): (0,1) OK, (1,0) OK, (-1,0) bloqueado por wall, (0,-1) ocupado por a1
    assert (0, 1) in dirs
    assert (1, 0) in dirs
    assert (-1, 0) not in dirs  # wall
    assert (0, -1) not in dirs  # a1 ocupa


def test_gather_solo_adyacente_con_cantidad():
    w = make_world()
    acts = acts_of(w.available_actions("a0"), "gather")
    targets = {a["args"]["target_eid"] for a in acts}
    assert "e_0001" in targets          # adyacente con cantidad
    assert "e_0004" in targets          # dropeado en la celda (distancia 0 <= 1)
    assert "e_0002" not in targets      # lejano
    assert "e_0003" not in targets      # agotado (amount 0)
    for a in acts:
        assert "target_eid" in a["args"] and a["args"].get("amount") is not None


def test_pickup_solo_dropeados_adyacentes():
    w = make_world()
    acts = acts_of(w.available_actions("a0"), "pickup")
    targets = {a["args"]["target_eid"] for a in acts}
    assert "e_0004" in targets
    assert "e_0001" not in targets  # sembrado, no dropeado


def test_consume_drop_solo_inventario():
    w = make_world()
    w.agents["a0"].inventory["S1"] = 2.0
    acts = w.available_actions("a0")
    consumes = acts_of(acts, "consume")
    drops = acts_of(acts, "drop")
    assert {a["args"]["rkind"] for a in consumes} == {"S1"}
    assert {a["args"]["rkind"] for a in drops} == {"S1"}


def test_give_solo_agente_adyacente_con_recurso():
    w = make_world()
    w.agents["a0"].inventory["S1"] = 2.0
    acts = acts_of(w.available_actions("a0"), "give")
    assert len(acts) == 1
    assert acts[0]["args"]["target_eid"] == "a1"
    assert acts[0]["args"]["rkind"] == "S1"


def test_build_solo_con_materiales_y_celda_libre():
    w = make_world()
    # sin materiales: no debe haber build
    assert acts_of(w.available_actions("a0"), "build") == []
    # mover recursos/agentes que ocupan las 4 adyacentes de (1,1):
    # (0,1)=wall, (2,1)=e_0001, (1,0)=a1, (1,2)=e_0003 — dejo (1,2) libre
    w.entities["e_0003"].x, w.entities["e_0003"].y = 8, 3
    w.agents["a0"].inventory["S3"] = 2.0
    w.agents["a0"].inventory["S4"] = 1.0
    acts = acts_of(w.available_actions("a0"), "build")
    assert len(acts) >= 1
    for a in acts:
        assert a["args"]["structure"] == "struct_a"
        assert w.in_bounds(a["args"]["x"], a["args"]["y"])
        assert not w.entities_at(a["args"]["x"], a["args"]["y"])


def test_talk_solo_con_energia():
    w = make_world()
    w.agents["a0"].energy = 5.0
    acts = acts_of(w.available_actions("a0"), "talk")
    assert len(acts) == 1
    w.agents["a0"].energy = 0.5
    assert acts_of(w.available_actions("a0"), "talk") == []


def test_agente_muerto_solo_rest():
    w = make_world()
    w.agents.pop("a0", None)
    w.entities.pop("a0", None)
    acts = w.available_actions("a0")
    assert acts == [{"action": "rest", "args": {}}]


def test_observation_incluye_acciones_disponibles():
    w = make_world()
    ag = LLMAgent("a0", FakeClient(), goal="sobrevivir", think_every=1,
                  hunger_threshold=1.0, radius=6)
    obs = ag._build_observation(w)
    assert "acciones_disponibles" in obs
    acts = obs["acciones_disponibles"]
    assert any(a["action"] == "move" for a in acts)
    assert any(a["action"] == "rest" for a in acts)
    # gather trae el eid opaco, no semántica
    gather = [a for a in acts if a["action"] == "gather"]
    for a in gather:
        assert a["args"]["target_eid"].startswith("e_") or a["args"]["target_eid"].startswith("res")


def test_acciones_disponibles_no_revelan_efectos():
    """D-026: la lista dice QUÉ botones existen, no QUÉ hacen."""
    w = make_world()
    obs_str = str(w.available_actions("a0"))
    assert "energy_gain" not in obs_str
    assert "consume_effects" not in obs_str
    assert "+8" not in obs_str


def _mundo_agente_en(ax, ay, rx, ry, amount=10.0, seed=1):
    """Mundo mínimo con un agente en (ax,ay) y un recurso en (rx,ry)."""
    cfg = WorldConfig(width=12, height=12, days=2, ticks_per_day=6)
    cfg.energy_per_unit["S1"] = 8.0
    w = WorldState(cfg, [Entity(eid="a0", kind="agent", x=ax, y=ay)], seed=seed)
    w._place(Entity(eid="e_res", kind="resource", x=rx, y=ry,
                    attrs={"kind": "S1", "amount": amount}))
    return w


def test_gather_disponible_exactamente_cuando_el_motor_lo_acepta():
    """Paso 0 del handoff gate-oráculo: available_actions no debe ser más
    estrecho que world.gather() en adyacencia. Con el agente en cada celda a
    distancia Manhattan <= 2 del recurso, gather aparece en el menú si y solo
    si el motor lo aceptaría (distancia <= 1)."""
    rx, ry = 5, 5
    for dx in range(-2, 3):
        for dy in range(-2, 3):
            if abs(dx) + abs(dy) > 2:
                continue
            w = _mundo_agente_en(rx + dx, ry + dy, rx, ry)
            disponible = any(a["args"].get("target_eid") == "e_res"
                             for a in acts_of(w.available_actions("a0"), "gather"))
            motor_acepta = w.gather("a0", "e_res").outcome == "ok"
            assert disponible == motor_acepta, (
                f"divergencia en offset ({dx},{dy}): menú={disponible}, motor={motor_acepta}")


def test_menu_move_barajado_reproducible_misma_seed():
    """Misma seed => mismo orden de direcciones de move (menu_rng determinista)."""
    w1 = _mundo_agente_en(5, 5, 1, 1, seed=1)
    w2 = _mundo_agente_en(5, 5, 1, 1, seed=1)
    d1 = [(a["args"]["dx"], a["args"]["dy"])
          for a in acts_of(w1.available_actions("a0"), "move")]
    d2 = [(a["args"]["dx"], a["args"]["dy"])
          for a in acts_of(w2.available_actions("a0"), "move")]
    assert len(d1) == 4          # las 4 direcciones libres, solo que barajadas
    assert d1 == d2              # y reproducibles con la misma seed


def test_menu_move_barajado_cambia_entre_seeds():
    """El orden del menú cambia entre seeds: el orden de una lista no debe ser
    información (corrección de instrumento del sesgo posicional)."""
    def ordenes_por_seed(seed):
        w = _mundo_agente_en(5, 5, 1, 1, seed=seed)
        return tuple((a["args"]["dx"], a["args"]["dy"])
                     for a in acts_of(w.available_actions("a0"), "move"))
    ordenes = {ordenes_por_seed(s) for s in range(1, 9)}
    # 8 seeds, 4! = 24 permutaciones: esperamos más de un orden distinto.
    assert len(ordenes) > 1
