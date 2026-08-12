"""Tests de la ontología aprobada (spec 2026-08-11, §8):
cúmulos, regeneración, muerte por inanición, efecto de struct_a."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.world_state import WorldConfig, WorldState, Entity, \
    build_separable_effects, separable_invariant_holds

SYMBOLS = ["S1", "S2", "S3", "S4"]

# valores de la especificación §8
EFFECT_SPEC = {
    "S1": (+8.0, -11.0, -4.0),
    "S2": (-2.0,  +9.0, +3.0),
    "S3": ( 0.0,   0.0,  0.0),
    "S4": (+1.0,   0.0, -1.0),
}


def make_world_config(**kw) -> WorldConfig:
    cfg = WorldConfig(width=30, height=30, days=5, ticks_per_day=8,
                      region_split=0.5, n_phases=2, phase_ticks=24,
                      energy_per_tick=0.4)
    base = {s: spec[0] for s, spec in EFFECT_SPEC.items()}
    d_region = {s: {"B": spec[1]} for s, spec in EFFECT_SPEC.items() if spec[1]}
    d_phase = {s: {1: spec[2]} for s, spec in EFFECT_SPEC.items() if spec[2]}
    cfg.consume_effects = build_separable_effects(base, d_region, d_phase)
    cfg.phase_barriers = {(1, "B"): True}
    cfg.recipes = {"struct_a": {"S3": 2.0, "S4": 1.0}}
    cfg.struct_effects = {"struct_a": {"metabolism_factor": 0.5, "phase": 1, "range": 1}}
    cfg.clusters_n = 8
    cfg.clusters_radius = 3
    cfg.clusters_per_region = 4
    cfg.regen_per_day = 0.5
    cfg.starvation_ticks = 48
    for k, v in kw.items():
        setattr(cfg, k, v)
    return cfg


# ---------------------------------------------------------------------------
# 1. Cúmulos — requisito crítico: los 4 símbolos en ambas regiones
# ---------------------------------------------------------------------------

def test_spec_effects_separable():
    cfg = make_world_config()
    # S1: +8 / +4 / -3 / -7 (celda retenida derivable)
    assert cfg.consume_effects[("S1", "A", 0)] == 8.0
    assert cfg.consume_effects[("S1", "A", 1)] == 4.0
    assert cfg.consume_effects[("S1", "B", 0)] == -3.0
    assert cfg.consume_effects[("S1", "B", 1)] == -7.0
    assert separable_invariant_holds(cfg.consume_effects)


def test_clusters_seeded_with_all_symbols_in_both_regions():
    """REQUISITO CRÍTICO: para cada símbolo y cada región, existe al menos un
    cúmulo. Debe fallar si la siembra deja un símbolo ausente de una región,
    en cualquier seed."""
    for seed in range(1, 6):
        w = WorldState(make_world_config(), [Entity(eid="a0", kind="agent", x=1, y=1)],
                       seed=seed)
        w.seed_clusters(SYMBOLS, density=0.12)
        assert w.symbols_present_in_all_regions(), f"seed {seed}: símbolo ausente de una región"


def test_clusters_deterministic_same_seed():
    w1 = WorldState(make_world_config(), [Entity(eid="a0", kind="agent", x=1, y=1)], seed=42)
    w2 = WorldState(make_world_config(), [Entity(eid="a0", kind="agent", x=1, y=1)], seed=42)
    w1.seed_clusters(SYMBOLS, density=0.12)
    w2.seed_clusters(SYMBOLS, density=0.12)
    r1 = sorted((e.x, e.y, e.attrs["kind"]) for e in w1.entities.values() if e.kind == "resource")
    r2 = sorted((e.x, e.y, e.attrs["kind"]) for e in w2.entities.values() if e.kind == "resource")
    assert r1 == r2


def test_clusters_per_region():
    w = WorldState(make_world_config(), [Entity(eid="a0", kind="agent", x=1, y=1)], seed=1)
    w.seed_clusters(SYMBOLS, density=0.12)
    by_cluster = {}
    for e in w.entities.values():
        if e.kind == "resource":
            c = e.attrs["cluster"]
            by_cluster.setdefault(c, set()).add(e.attrs["kind"])
    assert len(by_cluster) == 8
    # cada cúmulo es de UN solo símbolo
    for c, syms in by_cluster.items():
        assert len(syms) == 1


# ---------------------------------------------------------------------------
# 2. Regeneración
# ---------------------------------------------------------------------------

def test_regen_restores_to_initial_cap():
    cfg = make_world_config(regen_per_day=0.5, days=3)
    w = WorldState(cfg, [Entity(eid="a0", kind="agent", x=1, y=1)], seed=1)
    w.seed_clusters(SYMBOLS, density=0.12)
    # vaciar un recurso por completo
    res = next(e for e in w.entities.values() if e.kind == "resource")
    initial = res.attrs["initial_amount"]
    res.attrs["amount"] = 0.0
    # simular N días: ticks_per_day=8 => 8*3 ticks
    for _ in range(8 * 3):
        w.advance_tick()
    # tras 3 días con regen 0.5/día => +1.5, tope en initial
    assert res.attrs["amount"] == min(initial, 1.5)
    # nunca por encima del tope
    assert res.attrs["amount"] <= initial


def test_regen_never_exceeds_initial():
    cfg = make_world_config(regen_per_day=0.5, days=10)
    w = WorldState(cfg, [Entity(eid="a0", kind="agent", x=1, y=1)], seed=1)
    w.seed_clusters(SYMBOLS, density=0.12)
    for _ in range(8 * 10):
        w.advance_tick()
    for e in w.entities.values():
        if e.kind == "resource":
            assert e.attrs["amount"] <= e.attrs["initial_amount"]


# ---------------------------------------------------------------------------
# 3. Muerte por inanición sostenida (48 ticks CONSECUTIVOS)
# ---------------------------------------------------------------------------

def make_single_agent_world(**kw) -> WorldState:
    cfg = make_world_config(energy_per_tick=0.0, **kw)  # sin metabolismo: control del contador
    w = WorldState(cfg, [Entity(eid="a0", kind="agent", x=1, y=1)], seed=1)
    w.agents["a0"].inventory["S1"] = 5.0
    return w


def test_starvation_47_ticks_alive_48_dead():
    w = make_single_agent_world(starvation_ticks=48)
    w.agents["a0"].energy = 0.0
    for _ in range(47):
        w.advance_tick()
    assert "a0" in w.agents   # 47 ticks: sigue vivo
    w.advance_tick()          # tick 48: muere
    assert "a0" not in w.agents
    # inventario cae al suelo
    dropped = [e for e in w.entities.values() if e.kind == "resource"
               and e.attrs.get("owner_dropped") == "a0"]
    assert len(dropped) == 1
    assert dropped[0].attrs["amount"] == 5.0
    assert dropped[0].pos() == (1, 1)  # última celda


def test_starvation_counter_resets_on_eat():
    """Si el agente come en el tick 47, el contador se reinicia (consecutivos)."""
    w = make_single_agent_world(starvation_ticks=48)
    w.agents["a0"].energy = 0.0
    for _ in range(47):
        w.advance_tick()
    assert "a0" in w.agents
    # recupera energía (como si hubiera comido) => contador se resetea
    w.agents["a0"].energy = 30.0
    w.advance_tick()
    assert "a0" in w.agents
    assert w.agents["a0"].starvation_ticks == 0


# ---------------------------------------------------------------------------
# 4. Efecto de struct_a (metabolismo ×0.5 en fase oscura, adyacente)
# ---------------------------------------------------------------------------

def test_struct_a_halves_metabolism_in_dark_phase():
    # config coherente: día de 24 ticks, fase de 12 (clara 0-11, oscura 12-23)
    cfg = make_world_config(energy_per_tick=0.4, phase_ticks=12, ticks_per_day=24)
    # agente 1 junto a struct_a, agente 2 lejos
    w = WorldState(cfg, [
        Entity(eid="a_near", kind="agent", x=5, y=5),
        Entity(eid="a_far", kind="agent", x=20, y=5),
    ], seed=1)
    w._place(Entity(eid="struct", kind="object", x=6, y=5, attrs={"structure": "struct_a"}))
    for aid in ("a_near", "a_far"):
        w.agents[aid].energy = 50.0
    # fase oscura: tick 12..21
    w.tick = 12
    for _ in range(10):
        w.advance_tick()
    near_energy = w.agents["a_near"].energy
    far_energy = w.agents["a_far"].energy
    # 10 ticks oscuros: near pierde 0.4*0.5*10=2, far pierde 0.4*10=4
    assert abs(near_energy - (50.0 - 2.0)) < 0.01
    assert abs(far_energy - (50.0 - 4.0)) < 0.01
    assert near_energy > far_energy


def test_struct_a_no_effect_in_clear_phase():
    cfg = make_world_config(energy_per_tick=0.4, phase_ticks=12, ticks_per_day=24)
    w = WorldState(cfg, [
        Entity(eid="a_near", kind="agent", x=5, y=5),
        Entity(eid="a_far", kind="agent", x=20, y=5),
    ], seed=1)
    w._place(Entity(eid="struct", kind="object", x=6, y=5, attrs={"structure": "struct_a"}))
    for aid in ("a_near", "a_far"):
        w.agents[aid].energy = 50.0
    # fase clara: tick 0
    for _ in range(10):
        w.advance_tick()
    assert abs(w.agents["a_near"].energy - (50.0 - 4.0)) < 0.01
    assert abs(w.agents["a_far"].energy - (50.0 - 4.0)) < 0.01
