"""Tests de D-023: nacimiento repartido entre regiones (spec v1.1 de Opus).

El 92% de sub-exposición del piloto venía de una trampa de explotación:
todos los agentes nacían en A, aprendían que S2 es malo en A y nunca lo
probaban en B (donde es bueno). D-023: los 5 agentes nacen repartidos
(2 en una región, 3 en la otra; el lado mayor lo sortea el seed).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.run_pilot import spawn_positions, make_world_config
from ai.world_state import WorldConfig


def test_spawn_repartido_dos_y_tres():
    cfg = make_world_config(30)
    eids = ["a0", "a1", "a2", "a3", "a4"]
    for seed in range(1, 9):
        ents = spawn_positions(eids, cfg, seed)
        regions = [cfg.region_A if hasattr(cfg, "region_A") else
                   ("A" if e.x < cfg.width * cfg.region_split else "B")
                   for e in ents]
        nA = sum(1 for r in regions if r == "A")
        nB = sum(1 for r in regions if r == "B")
        assert nA + nB == 5
        assert (nA, nB) in [(2, 3), (3, 2)], f"seed {seed}: {nA}/{nB}"
        # todos en y=15, posiciones válidas y sin colisiones
        xs = [e.x for e in ents]
        assert len(set(xs)) == 5, f"seed {seed}: posiciones colisionan {xs}"


def test_spawn_lado_mayor_sortea_por_seed():
    """El lado mayor (3) no es siempre el mismo: el seed lo decide."""
    cfg = make_world_config(30)
    eids = ["a0", "a1", "a2", "a3", "a4"]
    layouts = set()
    for seed in range(1, 20):
        ents = spawn_positions(eids, cfg, seed)
        regions = tuple("A" if e.x < cfg.width * cfg.region_split else "B"
                        for e in ents)
        layouts.add(regions)
    # al menos 2 layouts distintos en 19 seeds (2 en A vs 3 en A)
    assert len(layouts) >= 2, f"solo se vio {layouts}"


def test_spawn_determinista_por_seed():
    cfg = make_world_config(30)
    eids = ["a0", "a1", "a2", "a3", "a4"]
    a = spawn_positions(eids, cfg, seed=7)
    b = spawn_positions(eids, cfg, seed=7)
    assert [(e.eid, e.x, e.y) for e in a] == [(e.eid, e.x, e.y) for e in b]


def test_spawn_ambas_regiones_representadas():
    cfg = make_world_config(30)
    eids = ["a0", "a1", "a2", "a3", "a4"]
    for seed in range(1, 12):
        ents = spawn_positions(eids, cfg, seed)
        xs = [e.x for e in ents]
        assert min(xs) < cfg.width * cfg.region_split, f"seed {seed}: nadie en A"
        assert max(xs) >= cfg.width * cfg.region_split, f"seed {seed}: nadie en B"


def test_spawn_respeta_bordes():
    cfg = make_world_config(30)
    ents = spawn_positions(["a0", "a1", "a2", "a3", "a4"], cfg, seed=3)
    for e in ents:
        assert 0 <= e.x < cfg.width
        assert 0 <= e.y < cfg.height
        assert e.y == 15  # fila central, como antes
