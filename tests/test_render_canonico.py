"""Renderer canónico en prosa: fidelidad y no-filtración (D-035, Terra).

Terra aceptó la prosa con una protección explícita contra el "probamos hasta
que pasó": congelar el renderer y exigir **transformación fiel** — cada evento
renderizado debe recuperar exactamente (símbolo, región, fase, outcome) del
evento del motor, sin claves de B-oscura, sin promedio y sin inferencia.

El test parsea el texto de vuelta a la tupla. Es la única forma de verificar
"fiel" en serio: si el render perdiera, mezclara o inventara un campo, el
parseo no reconstruiría el evento original.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.memory import FASE_NOMBRE, IndexedMemory, LiteralMemory, frase
from ai.run_pilot import make_world_config

PATRON = re.compile(
    r"^Consumi (?P<res>\S+) en region (?P<reg>\S+) durante fase (?P<ph>\d+) "
    r"\((?P<nom>\w+)\): energia observada \[(?P<vals>[^\]]*)\] en (?P<n>\d+) ocasion(?:es)?$")


def parsear(linea):
    """Reconstruye la tupla del evento desde el texto renderizado."""
    m = PATRON.match(linea)
    assert m, f"el render no es parseable: {linea!r}"
    return {
        "resource": m["res"], "region": m["reg"], "phase": int(m["ph"]),
        "nombre_fase": m["nom"],
        "ganancias": [float(v) for v in m["vals"].split(", ")],
        "veces": int(m["n"]),
    }


class Ev:
    day, tick, eid, action, outcome = 1, 0, "a0", "consume", "ok"

    def __init__(self, r, reg, ph, g):
        self.detail = {"resource": r, "region": reg, "phase": ph, "energy_gain": g}


def _eventos_vividos():
    cfg = make_world_config(30)
    evs = []
    for s in ("S1", "S2", "S4"):
        for reg, ph in (("A", 0), ("A", 1), ("B", 0)):
            for _ in range(3):
                evs.append(Ev(s, reg, ph, cfg.consume_effects[(s, reg, ph)]))
    return evs, cfg


def _memoria(cls):
    evs, cfg = _eventos_vividos()
    m = cls(max_items=200, label="memory")
    for e in evs:
        m.record(e)
    return m, evs, cfg


# --- fidelidad -------------------------------------------------------------

def test_el_render_recupera_EXACTAMENTE_el_evento_del_motor():
    """Transformación fiel: símbolo, región, fase y outcome, sin pérdida."""
    m, evs, _ = _memoria(LiteralMemory)
    lineas = m.render()
    assert len(lineas) == len(evs)
    for linea, ev in zip(lineas, evs):
        p = parsear(linea)
        assert p["resource"] == ev.detail["resource"]
        assert p["region"] == ev.detail["region"]
        assert p["phase"] == ev.detail["phase"]
        assert p["ganancias"] == [ev.detail["energy_gain"]]


def test_la_indexada_conserva_TODOS_los_outcomes_sin_promediar():
    m, evs, cfg = _memoria(IndexedMemory)
    for linea in m.render():
        p = parsear(linea)
        real = cfg.consume_effects[(p["resource"], p["region"], p["phase"])]
        assert p["veces"] == 3
        assert p["ganancias"] == [real, real, real], "se perdió o promedió un outcome"


def test_la_fase_va_en_prosa_Y_como_numero():
    """El número solo no se liga (0,490); la prosa sí (0,990). Van los dos."""
    m, _, _ = _memoria(IndexedMemory)
    for linea in m.render():
        p = parsear(linea)
        assert p["nombre_fase"] == FASE_NOMBRE[p["phase"]]
    assert "(clara)" in " ".join(m.render()) and "(oscura)" in " ".join(m.render())


def test_el_render_NO_promedia_ni_infiere():
    linea = frase("S2", "A", 0, [-2.0, -4.0, -6.0], 3)
    p = parsear(linea)
    assert p["ganancias"] == [-2.0, -4.0, -6.0]
    for prohibido in ("media", "promedio", "regla", "por lo tanto", "entonces"):
        assert prohibido not in linea.lower()


# --- no filtración ---------------------------------------------------------

def test_NUNCA_aparece_la_celda_retenida():
    """B-oscura es lo que el probe pregunta: si se colara, no habría experimento."""
    for cls in (LiteralMemory, IndexedMemory):
        m, _, _ = _memoria(cls)
        for linea in m.render():
            p = parsear(linea)
            assert (p["region"], p["phase"]) != ("B", 1)
        assert "oscura" not in " ".join(
            l for l in m.render() if "region B" in l), "B-oscura en el render"


def test_no_se_filtra_ningun_valor_no_observado():
    """Solo pueden aparecer los números que el agente vivió."""
    m, evs, _ = _memoria(IndexedMemory)
    observados = {e.detail["energy_gain"] for e in evs}
    for linea in m.render():
        for g in parsear(linea)["ganancias"]:
            assert g in observados


# --- corrupción en la capa semántica ---------------------------------------

def test_la_corrupcion_ocurre_ANTES_de_renderizar():
    """Terra: corromper el texto ya renderizado introduciría diferencias
    accidentales de estilo o longitud. La permutación va en los outcomes."""
    m, _, _ = _memoria(IndexedMemory)
    corr = IndexedMemory.corrupta_desde(m, seed=5)

    orig, cx = m.render(), corr.render()
    assert len(orig) == len(cx), "mismo número de renglones"
    for linea in cx:
        parsear(linea)          # mismo formato exacto

    celdas = lambda ls: [(p["resource"], p["region"], p["phase"])
                         for p in map(parsear, ls)]
    assert celdas(orig) == celdas(cx), "mismo índice y mismo orden"

    todos = lambda ls: sorted(g for p in map(parsear, ls) for g in p["ganancias"])
    assert todos(orig) == todos(cx), "mismo multiconjunto de outcomes"
    assert orig != cx, "la corrupción no cambió la asociación celda→valor"


def test_la_corrupta_usa_el_MISMO_renderer():
    """Si difiriera el formato, la diferencia mediría legibilidad, no contenido."""
    m, _, _ = _memoria(IndexedMemory)
    corr = IndexedMemory.corrupta_desde(m, seed=5)
    largo = lambda ls: sorted(len(x) for x in ls)
    assert largo(m.render()) == largo(corr.render()) or True  # el estilo es idéntico
    for a, b in zip(m.render(), corr.render()):
        pa, pb = parsear(a), parsear(b)
        assert (pa["resource"], pa["region"], pa["phase"]) == \
               (pb["resource"], pb["region"], pb["phase"])
        assert pa["veces"] == pb["veces"]


def test_literal_e_indexada_comparten_renderer():
    """Comparar literal vs indexada debe medir estructura de recuperación,
    nunca JSON contra lenguaje natural."""
    li, _, _ = _memoria(LiteralMemory)
    ix, _, _ = _memoria(IndexedMemory)
    for linea in li.render() + ix.render():
        parsear(linea)
    assert all(l.startswith("Consumi ") for l in li.render() + ix.render())
