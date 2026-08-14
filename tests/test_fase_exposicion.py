"""Tests de la Fase E — exposición dirigida (D-033).

Lo que protegen es la validez del probe posterior. Si la Fase E no entrega las
tres celdas, o toca la retenida, o depende de que el agente elija bien, el
probe de composición vuelve a medir otra cosa.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from ai.fase_exposicion import (
    CELDAS_VIVIDAS, CELDA_RETENIDA, SIMBOLOS_PUNTUADOS, REPETICIONES,
    cobertura, exponer_agente, exponer_todos,
)
from ai.run_pilot import make_world_config, spawn_positions
from ai.world_state import WorldState


class AgenteMudo:
    """No decide nada: si la exposición dependiera de sus elecciones, fallaría."""

    def __init__(self):
        self.recibidos = []

    def record_outcome(self, ev):
        self.recibidos.append(ev)


class AgenteSinHook:
    """Condición sin_memoria: no tiene record_outcome. No debe romper nada."""


def _mundo(days=30, seed=1):
    cfg = make_world_config(days)
    ents = spawn_positions([f"a{i}" for i in range(5)], cfg, seed)
    return WorldState(cfg, ents, seed=seed)


def test_entrega_las_TRES_celdas_para_cada_simbolo_puntuado():
    world = _mundo()
    ag = AgenteMudo()
    reg = exponer_agente(world, "a0", ag, seed=7)

    vistas = {(r["rkind"], r["region"], r["phase"]) for r in reg}
    esperado = {(s, reg_, ph) for reg_, ph in CELDAS_VIVIDAS
                for s in SIMBOLOS_PUNTUADOS}
    assert vistas == esperado
    assert len(reg) == len(esperado) * REPETICIONES


def test_NUNCA_toca_la_celda_retenida():
    """B-oscura es lo que el probe pregunta: exponerla destruye el experimento."""
    world = _mundo()
    reg = exponer_agente(world, "a0", AgenteMudo(), seed=7)
    assert all((r["region"], r["phase"]) != CELDA_RETENIDA for r in reg)
    assert all(not (r["region"] == "B" and r["phase"] == 1) for r in reg)


def test_se_niega_a_exponer_la_retenida_si_se_la_piden():
    world = _mundo()
    with pytest.raises(ValueError, match="retenida"):
        exponer_agente(world, "a0", AgenteMudo(), seed=1,
                       celdas=CELDAS_VIVIDAS + (CELDA_RETENIDA,))


def test_NO_depende_de_que_el_agente_elija_bien():
    """La restricción central de D-033: un agente que no decide nada recibe
    exactamente la misma exposición."""
    world = _mundo()
    mudo = AgenteMudo()
    reg = exponer_agente(world, "a0", mudo, seed=7)
    assert cobertura(reg)["cobertura_completa"]
    assert len(mudo.recibidos) == len(reg), "cada consumo llegó por record_outcome"


def test_la_ganancia_de_energia_es_la_REAL_del_motor():
    """No se fabrican eventos: los calcula world.consume con consume_effects."""
    world = _mundo()
    reg = exponer_agente(world, "a0", AgenteMudo(), seed=7)
    cfg = world.config
    for r in reg:
        esperado = cfg.consume_effects[(r["rkind"], r["region"], r["phase"])]
        assert r["energy_gain"] == esperado


def test_sin_memoria_no_rompe_aunque_no_tenga_hook():
    world = _mundo()
    reg = exponer_agente(world, "a0", AgenteSinHook(), seed=7)
    assert cobertura(reg)["cobertura_completa"]


def test_es_IDENTICA_entre_condiciones():
    """Mismo seed ⇒ misma exposición, sea cual sea el agente. Si difiriera,
    habría una diferencia entre brazos que no es la que el diseño manipula."""
    w1, w2 = _mundo(), _mundo()
    r1 = exponer_agente(w1, "a0", AgenteMudo(), seed=7)      # como 'memoria'
    r2 = exponer_agente(w2, "a0", AgenteSinHook(), seed=7)   # como 'sin_memoria'
    clave = lambda reg: [(r["rkind"], r["region"], r["phase"]) for r in reg]
    assert clave(r1) == clave(r2)


def test_restaura_tick_dia_y_posicion():
    """La Fase E no puede dejar el mundo movido: después corre la ecología."""
    world = _mundo()
    ent = world.entities["a0"]
    antes = (world.tick, world.day, ent.x, ent.y)
    exponer_agente(world, "a0", AgenteMudo(), seed=7)
    assert (world.tick, world.day, ent.x, ent.y) == antes


def test_el_invariante_de_heldout_del_motor_sigue_limpio():
    world = _mundo()
    exponer_todos(world, {f"a{i}": AgenteMudo() for i in range(5)}, seed=3)
    assert world.no_heldout_consumption(), (
        "la Fase E contaminó la celda retenida")


def test_cobertura_detecta_una_exposicion_incompleta():
    world = _mundo()
    reg = exponer_agente(world, "a0", AgenteMudo(), seed=7,
                         celdas=(("A", 0),))          # solo una celda
    c = cobertura(reg)
    assert not c["cobertura_completa"]
    assert c["faltantes"]["a0"], "debe decir QUÉ faltó"


def test_expone_a_todos_los_agentes_vivos():
    world = _mundo()
    agentes = {f"a{i}": AgenteMudo() for i in range(5)}
    reg = exponer_todos(world, agentes, seed=3)
    c = cobertura(reg)
    assert c["agentes"] == 5
    assert c["cobertura_completa"]


def test_no_mata_al_agente_durante_la_exposicion():
    """Comer S2 en A-clara resta energía: si la Fase E matara al agente, el
    probe posterior no tendría a quién preguntarle."""
    world = _mundo()
    world.agents["a0"].energy = 40.0
    exponer_agente(world, "a0", AgenteMudo(), seed=7)
    assert world.agents["a0"].energy > 0
