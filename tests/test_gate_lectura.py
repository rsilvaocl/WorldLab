"""Tests del gate de lectura, memoria indexada y potencia (spec de Terra).

Lo que protegen: que el gate use los umbrales pre-registrados, que la memoria
indexada no filtre nada que el agente no haya vivido, y que la corrupción
comparta índice y volumen con la condición que contrasta — sin eso, la
diferencia mediría legibilidad o longitud en vez de contenido.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from ai.gate_lectura import (
    CELDAS_VIVIDAS, GATE_AGREGADO, GATE_POR_CELDA, MDE, N_MINIMO,
    agregar_gate, correr_gate_lectura, n_requerido, plan_de_potencia,
    sigma_bootstrap_p80,
)
from ai.memory import IndexedMemory, LiteralMemory
from ai.run_pilot import make_world_config


class Ev:
    day, tick, eid, action, outcome = 1, 0, "a0", "consume", "ok"

    def __init__(self, r, reg, ph, g):
        self.detail = {"resource": r, "region": reg, "phase": ph, "energy_gain": g}


def _memoria(cls=IndexedMemory, reps=3):
    cfg = make_world_config(30)
    m = cls(max_items=200, label="memory")
    for s in ("S1", "S2", "S4"):
        for reg, ph in CELDAS_VIVIDAS:
            for _ in range(reps):
                m.record(Ev(s, reg, ph, cfg.consume_effects[(s, reg, ph)]))
    return m


class AgenteQueLee:
    """Lee su memoria indexada y contesta bien."""

    def __init__(self, mem, fallar=()):
        self.mem = mem
        self.fallar = set(fallar)

    def predict_effect(self, rkind, region, phase):
        if (region, phase) in self.fallar:
            return 99.0
        # lee la capa SEMÁNTICA (filas), no el texto: el render es prosa (D-035)
        for (rk, reg, ph), gains in self.mem.filas():
            if (rk, reg, ph) == (rkind, region, phase):
                return gains[0]
        return None


# --- memoria indexada ------------------------------------------------------

def test_la_indexada_agrupa_por_celda_y_NO_promedia():
    """El límite entre indexada y agregada: la aritmética la hace el agente."""
    m = _memoria()
    filas = m.filas()
    assert len(filas) == 9, "3 símbolos × 3 celdas vividas"
    for _clave, gains in filas:
        assert len(gains) == 3, "conserva los tres outcomes, no su media"
    texto = " ".join(m.render()).lower()
    assert "media" not in texto and "promedio" not in texto


def test_la_indexada_NO_contiene_la_celda_retenida():
    """Solo experiencias propias: el agente nunca estuvo en B-oscura."""
    m = _memoria()
    for (_rk, reg, ph), _g in m.filas():
        assert (reg, ph) != ("B", 1)


def test_la_indexada_tiene_la_MISMA_informacion_que_la_literal():
    """Cambia la accesibilidad, no la información (por eso es admisible)."""
    lit, idx = _memoria(LiteralMemory), _memoria(IndexedMemory)
    assert lit.indice() == idx.indice()


def test_la_corrupta_comparte_indice_y_volumen():
    """Terra: si no comparte índice y volumen, la diferencia mide legibilidad
    o longitud en vez de contenido."""
    fuente = _memoria()
    corr = IndexedMemory.corrupta_desde(fuente, seed=1)

    celdas = lambda m: {c for c, _ in m.filas()}
    assert celdas(corr) == celdas(fuente), "mismo índice"
    veces = lambda m: sorted(len(g) for _, g in m.filas())
    assert veces(corr) == veces(fuente), "mismo volumen"

    todos = lambda m: sorted(g for _, gs in m.filas() for g in gs)
    assert todos(corr) == todos(fuente), "mismo multiconjunto de outcomes"


def test_la_corrupta_SI_rompe_la_asociacion_celda_valor():
    fuente = _memoria()
    corr = IndexedMemory.corrupta_desde(fuente, seed=3)
    par = lambda m: {c: tuple(g) for c, g in m.filas()}
    assert par(corr) != par(fuente), "la permutación no cambió nada"


# --- gate de lectura -------------------------------------------------------

def test_los_umbrales_son_los_preregistrados():
    assert GATE_AGREGADO == 0.75
    assert GATE_POR_CELDA == 0.60


def test_un_agente_que_lee_bien_pasa_el_gate():
    cfg = make_world_config(30)
    r = correr_gate_lectura(AgenteQueLee(_memoria()), cfg.consume_effects)
    assert r["exactitud_agregada"] == 1.0
    assert r["pasa"]


def test_el_gate_pregunta_SOLO_por_celdas_vividas():
    cfg = make_world_config(30)
    r = correr_gate_lectura(AgenteQueLee(_memoria()), cfg.consume_effects)
    assert all((f["region"], f["phase"]) != ("B", 1) for f in r["filas"])
    assert len(r["filas"]) == 9


def test_una_celda_floja_tumba_el_gate_aunque_el_agregado_alcance():
    """Los dos umbrales son exigencias distintas: 2 de 3 celdas perfectas dan
    0,67 agregado, pero la tercera en 0 no puede pasar."""
    cfg = make_world_config(30)
    r = correr_gate_lectura(AgenteQueLee(_memoria(), fallar=[("B", 0)]),
                            cfg.consume_effects)
    assert r["por_celda"]["B-0"] == 0.0
    assert not r["pasa"]


def test_el_gate_agregado_evalua_la_representacion_no_cada_caso():
    """Terra: excluir selectivamente mundos que fallen sesga el estimando."""
    cfg = make_world_config(30)
    buenos = [correr_gate_lectura(AgenteQueLee(_memoria()), cfg.consume_effects)
              for _ in range(3)]
    malo = correr_gate_lectura(AgenteQueLee(_memoria(), fallar=[("B", 0)]),
                               cfg.consume_effects)
    ag = agregar_gate(buenos + [malo])
    assert ag["n_agentes"] == 4 and ag["n_preguntas"] == 36
    assert ag["por_celda"]["B-0"] == 0.75, "el malo entra al promedio, no se excluye"


def test_el_0_52_de_la_memoria_literal_NO_pasa():
    """El dato que motivó todo esto: 0,52 contra un umbral de 0,75."""
    class Flojo:
        def __init__(self):
            self.n = 0

        def predict_effect(self, rkind, region, phase):
            self.n += 1
            cfg = make_world_config(30)
            real = cfg.consume_effects[(rkind, region, phase)]
            return real if self.n % 2 else 99.0      # ~0,5 de acierto
    cfg = make_world_config(30)
    r = correr_gate_lectura(Flojo(), cfg.consume_effects)
    assert r["exactitud_agregada"] < GATE_AGREGADO
    assert not r["pasa"]


# --- potencia --------------------------------------------------------------

def test_la_formula_de_N_es_la_de_terra():
    # ((1.96+1.282)/0.25 * σ)^2, con piso 16
    assert n_requerido(0.25) == N_MINIMO
    assert n_requerido(0.30) == N_MINIMO
    assert n_requerido(0.35) == 21
    assert n_requerido(0.40) == 27


def test_el_piso_de_16_seeds_se_respeta():
    assert n_requerido(0.01) == 16
    assert n_requerido(0.5) == 43


def test_sigma_cero_NO_devuelve_el_piso_sino_que_marca_degenerado():
    """Fallo silencioso real, encontrado en el piloto del 14/08.

    La Fase E estandariza la exposición: el contenido de la memoria es idéntico
    en todo seed y con temperature=0 la respuesta también. σ_Δ salió 0,0 exacto
    en 8 seeds. Devolver el piso de 16 haría pasar por respuesta válida la
    señal de que el mundo no es la unidad estadística.
    """
    plan = plan_de_potencia([-0.333] * 8)
    assert plan["degenerado"] is True
    assert plan["n_requerido"] is None
    assert "unidad estadística" in plan["motivo"]

    # con varianza real sí devuelve un N
    normal = plan_de_potencia([0.1, 0.4, 0.2, 0.5, 0.0, 0.3], seed=1)
    assert normal.get("degenerado") is None
    assert normal["n_requerido"] >= 16


def test_usa_el_limite_superior_del_bootstrap_no_la_media():
    """Terra: no subpotenciar por una estimación ruidosa del smoke."""
    difs = [0.1, 0.4, 0.2, 0.5, 0.0, 0.3, 0.35, 0.15]
    s = sigma_bootstrap_p80(difs, seed=1)
    assert s["sigma_p80"] >= s["sigma_puntual"]
    plan = plan_de_potencia(difs, seed=1)
    assert plan["n_requerido"] >= plan["n_con_sigma_puntual"]
    assert plan["mde"] == MDE


def test_sigma_necesita_al_menos_dos_seeds():
    with pytest.raises(ValueError, match="al menos 2"):
        sigma_bootstrap_p80([0.3])


def test_las_tres_componentes_se_reportan_SEPARADAS():
    """Terra: abstención y recuperación no son extremos de un único eje.
    DeepSeek recupera menos Y se abstiene menos que gemma; presentarlas juntas
    insinuaría una teoría sobre la abstención que los datos no sostienen."""
    from ai.gate_lectura import tres_componentes
    VIV = {"A-0": -2.0, "A-1": 1.0, "B-0": 7.0}
    val = lambda f, c: VIV[c]
    filas = ([{"predicho": 1.0, "correcto": False}] * 6 +      # repite A-oscura
             [{"predicho": 7.0, "correcto": False}] * 2 +      # repite B-clara
             [{"predicho": 99.0, "correcto": True}] * 1 +      # no repite, acierta
             [{"predicho": None, "correcto": False}] * 1)      # se abstiene
    r = tres_componentes(filas, val)
    assert r["tasa_respuesta"] == 0.9
    assert r["exactitud_condicionada"] == round(1 / 9, 3)
    assert r["exactitud_cruda"] == 0.1
    assert r["recuperacion_valor_vivido"] == round(8 / 9, 3)
    assert r["sesgo_fase"] == 0.75 and r["sesgo_region"] == 0.25
    assert r["brecha_fase_menos_region"] == 0.5


def test_un_modelo_que_se_abstiene_mucho_no_parece_recuperar_menos():
    """El caso que motivó separarlas: la tasa de recuperación se calcula sobre
    las RESPUESTAS, no sobre el total, o la abstención la contaminaría."""
    from ai.gate_lectura import tres_componentes
    VIV = {"A-0": -2.0, "A-1": 1.0, "B-0": 7.0}
    val = lambda f, c: VIV[c]
    abstemio = ([{"predicho": 1.0, "correcto": False}] * 2 +
                [{"predicho": None, "correcto": False}] * 8)
    r = tres_componentes(abstemio, val)
    assert r["tasa_respuesta"] == 0.2
    assert r["recuperacion_valor_vivido"] == 1.0, (
        "recupera en el 100% de lo que responde, aunque responda poco")
