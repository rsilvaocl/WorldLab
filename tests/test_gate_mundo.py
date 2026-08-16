"""Tests del gate de viabilidad/exposición del mundo (spec de Terra).

Lo que protegen: que los umbrales sean los que Terra fijó ANTES de ver datos, y
que el gate no pueda pasar por accidente. Si el gate se afloja, el rediseño de
la tabla vuelve a ser tuning retrospectivo — justo lo que evita.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.gate_mundo import (
    SEEDS_GATE, AOnlyAgent, candidatas, gate1_viabilidad, gate2_exposicion,
    gate3_b_importa, invariantes_ok, l1, spec_a_efectos,
    G1_LONGEVIDAD_MEDIA, G1_SUPERV_MIN, G1_SEEDS_MIN, G2_FRACCION_D025,
    G3_DELTA_LONGEVIDAD,
)
from ai.baseline import BaselineParams
from ai.world_state import WorldConfig, WorldState, Entity
from ai.run_pilot import EFFECT_SPEC, make_world_config


def _mundos(n=12, longev=0.9, superv=5, b_clara=3, d025=True, energia=60.0):
    eids = [f"a{i}" for i in range(5)]
    return [{
        "seed": s,
        "longevidad": {e: longev for e in eids},
        "longevidad_media": longev,
        "supervivientes": superv,
        "energia_final_supervivientes": energia,
        "consumos_b_clara": {e: b_clara for e in eids},
        "exposicion_d025": {e: d025 for e in eids},
    } for s in range(1, n + 1)]


def test_los_umbrales_son_los_que_fijo_terra():
    """Si alguien los baja, el gate deja de significar lo que se acordó."""
    assert G1_LONGEVIDAD_MEDIA == 0.80
    assert (G1_SUPERV_MIN, G1_SEEDS_MIN) == (4, 9)
    assert G2_FRACCION_D025 == 0.75
    assert G3_DELTA_LONGEVIDAD == 0.20
    assert SEEDS_GATE == tuple(range(1, 13)), "12 seeds fijas, 1..12"


def test_gate1_falla_si_el_mundo_se_vuelve_invivible():
    """El sentido del gate 1: impedir que 'arreglar B' mate el mundo."""
    assert gate1_viabilidad(_mundos())["pasa"]
    assert not gate1_viabilidad(_mundos(longev=0.5))["pasa"]
    assert not gate1_viabilidad(_mundos(superv=3))["pasa"]


def test_gate1_tolera_hasta_tres_seeds_malas():
    m = _mundos()
    for i in range(3):
        m[i]["supervivientes"] = 2
    assert gate1_viabilidad(m)["pasa"], "9/12 debe alcanzar"
    m[3]["supervivientes"] = 2
    assert not gate1_viabilidad(m)["pasa"], "8/12 no"


def test_gate2_exige_exposicion_real_a_B_clara():
    assert gate2_exposicion(_mundos())["pasa"]
    # el caso que motivó todo esto: casi nadie consume en B-clara
    assert not gate2_exposicion(_mundos(b_clara=0))["pasa"]
    # un solo consumo no basta: el umbral es 2
    assert not gate2_exposicion(_mundos(b_clara=1))["pasa"]
    # vivir B-clara sin las otras celdas no habilita composición
    assert not gate2_exposicion(_mundos(d025=False))["pasa"]


def test_gate2_el_piso_por_seed_y_el_agregado_son_exigencias_DISTINTAS():
    """El mínimo por seed (3/5 = 60%) es MÁS BAJO que el agregado (75%).

    No es contradicción, es un piso más una media: ninguna seed puede caer bajo
    3/5, y además el promedio tiene que llegar a 3,75/5. Un mundo parejo en
    exactamente 3/5 cumple el piso y NO el agregado — hace falta que algunas
    seeds expongan a 4 o 5 agentes para compensar.
    """
    m = _mundos()
    for mundo in m:                      # exactamente 3 de 5 en todas las seeds
        for e in ("a3", "a4"):
            mundo["consumos_b_clara"][e] = 0
            mundo["exposicion_d025"][e] = False   # sin B-clara no hay D-025
    r = gate2_exposicion(m)
    assert r["seeds_con_3_agentes_expuestos"] == 12, "el piso por seed se cumple"
    assert r["fraccion_d025"] == 0.6
    assert not r["pasa"], "60% agregado < 75%: el piso solo no basta"

    # con 4/5 expuestos en la mitad de las seeds, el agregado llega
    for mundo in m[:6]:
        mundo["consumos_b_clara"]["a3"] = 3
        mundo["exposicion_d025"]["a3"] = True
    r2 = gate2_exposicion(m)
    assert r2["fraccion_d025"] == 0.7
    assert not r2["pasa"], "70% sigue sin alcanzar"


def test_gate2_pasa_con_exposicion_alta_pero_no_perfecta():
    """Terra: exigir 5/5 confundiría el gate de composición con control perfecto.
    Con 4/5 expuestos en todas las seeds (80%) el gate pasa."""
    m = _mundos()
    for mundo in m:
        mundo["consumos_b_clara"]["a4"] = 0
        mundo["exposicion_d025"]["a4"] = False
    r = gate2_exposicion(m)
    assert r["fraccion_d025"] == 0.8
    assert r["pasa"], "4/5 en todas las seeds debe bastar"


def test_gate3_falla_si_A_only_rinde_casi_igual():
    """El corazón del rediseño: si A-only empata, B sigue sin importar."""
    libre, aonly = _mundos(longev=0.9, superv=5, energia=60.0), _mundos(
        longev=0.88, superv=5, energia=58.0)
    assert not gate3_b_importa(libre, aonly)["pasa"]

    aonly_peor = _mundos(longev=0.60, superv=3, energia=30.0)
    assert gate3_b_importa(libre, aonly_peor)["pasa"]


def test_gate3_exige_las_TRES_condiciones():
    libre = _mundos(longev=0.9, superv=5, energia=60.0)
    # solo longevidad, sin supervivientes extra ni energía
    assert not gate3_b_importa(libre, _mundos(longev=0.6, superv=5, energia=59.0))["pasa"]
    # solo energía
    assert not gate3_b_importa(libre, _mundos(longev=0.89, superv=5, energia=20.0))["pasa"]


def test_la_tabla_actual_conserva_sus_invariantes():
    assert invariantes_ok(EFFECT_SPEC)


def test_las_candidatas_conservan_separabilidad_D022_y_el_control():
    cands = candidatas(EFFECT_SPEC, deltas=(-2, -1, 0, 1, 2))
    assert len(cands) > 5
    for spec in cands[:40]:
        assert invariantes_ok(spec)
        eff = spec_a_efectos(spec)
        assert all(eff[("S3", r, p)] == 0 for r in ("A", "B") for p in (0, 1))


def test_las_candidatas_vienen_ordenadas_por_cambio_minimo():
    """La regla que hace reproducible el rediseño: se toma la PRIMERA que pasa,
    no la que mejor se vea después de mirar los resultados."""
    cands = candidatas(EFFECT_SPEC, deltas=(-2, -1, 0, 1, 2))
    dists = [l1(c, EFFECT_SPEC) for c in cands]
    assert dists == sorted(dists)
    assert dists[0] == 0.0, "la tabla actual es su propia candidata más cercana"


def test_A_only_se_niega_a_cruzar():
    cfg = make_world_config(30)
    cfg.days = 2
    # agente en A pegado a la frontera, con un recurso jugoso en B
    ents = [Entity(eid="a0", kind="agent", x=14, y=15),
            Entity(eid="r_b", kind="resource", x=16, y=15,
                   attrs={"kind": "S2", "amount": 10.0, "initial_amount": 10.0})]
    world = WorldState(cfg, ents, seed=1)
    ag = AOnlyAgent("a0", BaselineParams(), rng_seed=0, split_x=15)
    for _ in range(6):
        action, kwargs = ag.decide(world)
        if action == "move":
            assert world.entities["a0"].x + int(kwargs.get("dx", 0)) < 15
            world.move("a0", kwargs.get("dx", 0), kwargs.get("dy", 0))
        assert not (action == "gather" and kwargs.get("target_eid") == "r_b"), (
            "A-only no puede recolectar en B")
    assert world.entities["a0"].x < 15


def test_el_prefiltro_es_necesario_pero_NO_suficiente():
    """Descarta por aritmética, no reemplaza a la simulación.

    Documenta la asimetría: si el prefiltro rechaza, el gate 3 no puede pasar;
    si acepta, el mundo simulado sigue teniendo la última palabra (traslado,
    metabolismo y ventana de fase no están en la cuenta).
    """
    from ai.gate_mundo import prefiltro_analitico
    # la tabla actual: B-clara (+7) NO le gana a A-clara (+8) => rechazada
    assert not prefiltro_analitico(EFFECT_SPEC)

    # subir δ_región de S2 hace que B-clara valga más que A-clara
    mejor_B = dict(EFFECT_SPEC)
    b, dr, dp = EFFECT_SPEC["S2"]
    mejor_B["S2"] = (b, dr + 5, dp)      # B-clara: +7 -> +12
    assert prefiltro_analitico(mejor_B)


def test_el_prefiltro_protege_la_vivibilidad_de_A():
    """Arreglar B rompiendo el mundo es lo que el gate 1 prohíbe."""
    from ai.gate_mundo import prefiltro_analitico, spec_a_efectos
    roto = {"S1": (-1.0, 0.0, 0.0), "S2": (-2.0, 20.0, 3.0),
            "S3": (0.0, 0.0, 0.0), "S4": (-1.0, 0.0, 0.0)}
    eff = spec_a_efectos(roto)
    assert max(eff[(s, "A", 0)] for s in ("S1", "S2", "S4")) <= 0
    assert not prefiltro_analitico(roto), "A invivible debe rechazarse"


def test_las_seeds_de_afinado_son_DISJUNTAS_de_las_del_gate():
    """Afinar y evaluar en los mismos mundos infla el resultado del gate."""
    from ai.gate_mundo import SEEDS_TUNING, SEEDS_GATE, GRID
    assert not (set(SEEDS_TUNING) & set(SEEDS_GATE))
    assert len(GRID) == 18, "el presupuesto de búsqueda es el mismo para ambas políticas"
