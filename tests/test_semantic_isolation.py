"""Test anti-fuga semántica (exigencia de Opus).

La abstracción del vocabulario (crítica #1 de Claude) se rompe si CUALQUIER
cadena semántica llega al prompt del agente — no solo en los eids. Este test
falla si el payload de percepción contiene palabras con significado humano
(food, water, wood, stone, iron, comida, agua, madera, piedra, hierro, etc.).

El mundo experimental usa IDs opacos (S1..S4, ▲, kappa). Los nombres bonitos
viven SOLO en el visor, mapeados al dibujar.
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.world_state import WorldConfig, WorldState, Entity

# cadenas que NUNCA deben aparecer en el payload de percepción
SEMANTIC_STRINGS = [
    "food", "water", "wood", "stone", "iron",
    "comida", "agua", "madera", "piedra", "hierro",
    "comer", "beber", "eat", "drink",
]

OPAQUE_IDS = ["S1", "S2", "S3", "S4"]


def test_perception_payload_is_semantic_free():
    cfg = WorldConfig(width=15, height=15)
    cfg.energy_per_unit["S1"] = 8.0
    cfg.energy_per_unit["S2"] = 5.0
    w = WorldState(cfg, [
        Entity(eid="a0", kind="agent", x=7, y=7),
        Entity(eid="a1", kind="agent", x=9, y=9),
    ], seed=1)
    # recursos con ids opacos
    for i, rid in enumerate(OPAQUE_IDS):
        w._place(Entity(eid=f"r_{i}", kind="resource", x=8 + i, y=7,
                        attrs={"kind": rid, "amount": 10.0}))
    # un recurso soltado (eid opaco)
    w._drop_seq += 1
    w._place(Entity(eid=f"e_{w._drop_seq:04d}", kind="resource", x=6, y=8,
                    attrs={"kind": "S2", "amount": 5.0, "owner_dropped": "a0"}))

    payload = json.dumps(w.visible_to("a0", radius=6), ensure_ascii=False).lower()
    for s in SEMANTIC_STRINGS:
        assert s not in payload, f"FUGA SEMÁNTICA: '{s}' aparece en la percepción"


def test_eids_are_opaque():
    """Ningún eid del mundo experimental revela el tipo."""
    cfg = WorldConfig(width=15, height=15)
    w = WorldState(cfg, [Entity(eid="a0", kind="agent", x=1, y=1)], seed=1)
    w._drop_seq += 1
    w._place(Entity(eid=f"e_{w._drop_seq:04d}", kind="resource", x=2, y=2,
                    attrs={"kind": "S1", "amount": 3.0, "owner_dropped": "a0"}))
    for e in w.entities.values():
        assert not any(s in e.eid.lower() for s in ["food", "water", "wood", "stone", "iron"])
        assert e.eid.startswith(("a", "r_", "e_", "b_"))


def test_visible_to_reveals_opaque_rkind():
    """La percepción revela el id opaco (S1), nunca el nombre bonito."""
    cfg = WorldConfig(width=15, height=15)
    w = WorldState(cfg, [Entity(eid="a0", kind="agent", x=1, y=1)], seed=1)
    w._place(Entity(eid="r_0", kind="resource", x=2, y=1,
                    attrs={"kind": "S1", "amount": 10.0}))
    vis = w.visible_to("a0", radius=4)
    rkind = next(v["rkind"] for v in vis["visible"] if v["kind"] == "resource")
    assert rkind == "S1"
