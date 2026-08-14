"""Test de D-029 (Paso 2): la región de cada entidad visible es PERCEPCIÓN.

La región de una entidad visible se etiqueta en `visible_to` (identidad
visible, D-012) sin prestar world model (dónde está algo no es qué pasa si lo
consumís, D-020). Una entidad al otro lado de la frontera reporta región
distinta a la del agente; una del mismo lado, la misma.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.world_state import WorldConfig, WorldState, Entity, build_separable_effects


def _cfg() -> WorldConfig:
    cfg = WorldConfig(width=30, height=30, days=5, ticks_per_day=24,
                      energy_per_tick=0.3, region_split=0.5, n_phases=2,
                      phase_ticks=12, clusters_n=0)
    cfg.consume_effects = build_separable_effects(
        base={"S1": +8.0, "S2": -2.0, "S3": 0.0, "S4": +1.0},
        delta_region={"S1": {"B": -9.0}, "S2": {"B": +9.0}, "S4": {"B": +6.0}},
        delta_phase={"S1": {1: -4.0}, "S2": {1: +3.0}, "S4": {1: -9.0}})
    return cfg


def test_entidad_al_otro_lado_de_la_frontera_reporta_region_distinta():
    cfg = _cfg()  # split_x = 15
    world = WorldState(cfg, [
        Entity(eid="a0", kind="agent", x=14, y=10),
        Entity(eid="r1", kind="resource", x=15, y=10,
               attrs={"kind": "S2", "amount": 1}),
    ], seed=1)
    obs = world.visible_to("a0", radius=4)
    vis = {v["eid"]: v for v in obs["visible"]}
    assert obs["region"] == "A"
    assert "r1" in vis
    assert vis["r1"]["region"] == "B", \
        "una entidad al otro lado de la frontera debe reportar región B"


def test_entidad_del_mismo_lado_reporta_la_misma_region():
    cfg = _cfg()
    world = WorldState(cfg, [
        Entity(eid="a0", kind="agent", x=14, y=10),
        Entity(eid="r1", kind="resource", x=12, y=10,
               attrs={"kind": "S2", "amount": 1}),
    ], seed=1)
    obs = world.visible_to("a0", radius=4)
    vis = {v["eid"]: v for v in obs["visible"]}
    assert obs["region"] == "A"
    assert vis["r1"]["region"] == "A"


def test_agente_visible_al_otro_lado_tambien_reporta_region():
    cfg = _cfg()
    world = WorldState(cfg, [
        Entity(eid="a0", kind="agent", x=14, y=10),
        Entity(eid="a1", kind="agent", x=16, y=10),
    ], seed=1)
    obs = world.visible_to("a0", radius=4)
    vis = {v["eid"]: v for v in obs["visible"]}
    assert vis["a1"]["region"] == "B"


def test_entidades_fuera_del_radio_no_aparecen():
    cfg = _cfg()
    world = WorldState(cfg, [
        Entity(eid="a0", kind="agent", x=14, y=10),
        Entity(eid="r1", kind="resource", x=14, y=20,
               attrs={"kind": "S2", "amount": 1}),
    ], seed=1)
    obs = world.visible_to("a0", radius=4)
    assert all(v["eid"] != "r1" for v in obs["visible"])
