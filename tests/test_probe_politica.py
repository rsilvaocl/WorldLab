"""Tests del probe de política (matriz contrafactual de Terra).

Lo que hay que proteger: que los tres escenarios sean REALMENTE distintos en lo
que le exigen al agente. Si el menú de acciones no distingue A/B/C, el probe no
separa selección de planificación y su resultado no significa nada.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.probe_politica import best_worst_in, build_state, run_matrix
from ai.run_pilot import make_world_config


CFG = make_world_config(30)


def _menu(world, eid="a0"):
    return world.available_actions(eid)


def test_el_bueno_y_el_malo_salen_de_la_config():
    good, bad = best_worst_in(CFG, "A", 0)
    assert good == "S1" and CFG.consume_effects[("S1", "A", 0)] == 8.0
    assert bad == "S2" and CFG.consume_effects[("S2", "A", 0)] == -2.0
    # y en B-clara el orden se invierte: el probe no asume una región
    g2, b2 = best_worst_in(CFG, "B", 0)
    assert CFG.consume_effects[(g2, "B", 0)] > CFG.consume_effects[(b2, "B", 0)]


def test_escenario_A_ofrece_AMBOS_consume_sin_navegar():
    world, good, bad = build_state(CFG, "A", 6, 8, far=5, seed=1)
    menu = _menu(world)
    consumibles = {a["args"].get("rkind") for a in menu if a["action"] == "consume"}
    assert good in consumibles and bad in consumibles, (
        "en A la decisión debe ser puramente cuál consumir")
    assert world.agents["a0"].inventory[good] > 0


def test_escenario_B_ofrece_AMBOS_gather_adyacentes():
    world, good, bad = build_state(CFG, "B", 6, 8, far=5, seed=1)
    menu = _menu(world)
    targets = {a["args"].get("target_eid") for a in menu if a["action"] == "gather"}
    assert {"r_good", "r_bad"} <= targets, (
        "en B ambos recursos deben ser recolectables sin moverse")


def test_escenario_C_deja_SOLO_el_malo_al_alcance():
    world, good, bad = build_state(CFG, "C", 6, 8, far=5, seed=1)
    menu = _menu(world)
    targets = {a["args"].get("target_eid") for a in menu if a["action"] == "gather"}
    assert targets == {"r_bad"}, (
        "en C el bueno NO debe ser alcanzable en un paso: si lo fuera, C no "
        "mediría planificación")
    # pero tiene que estar VISIBLE, o el agente no puede saber que existe
    vis = world.visible_to("a0", radius=6)
    kinds = [v.get("rkind") for v in vis["visible"] if v.get("rkind")]
    assert good in kinds, "el recurso bueno debe verse desde donde está el agente"


def test_los_tres_escenarios_son_A_clara():
    """La tabla se lee por (símbolo, región, fase): si el escenario cayera en
    otra celda, el 'bueno' y el 'malo' serían otros y el probe mentiría."""
    for esc in ("A", "B", "C"):
        world, _, _ = build_state(CFG, esc, 6, 8, far=5, seed=1)
        ent = world.entities["a0"]
        assert world.region(ent.x, ent.y) == "A"
        assert world.phase() == 0


def test_el_agente_tiene_hambre_en_los_tres():
    """Sin hambre el agente no piensa (hunger_threshold=30): el probe mediría
    la ausencia de decisión, no la decisión."""
    for esc in ("A", "B", "C"):
        world, _, _ = build_state(CFG, esc, 6, 8, far=5, seed=1)
        assert world.agents["a0"].energy < 30.0


class FakeGoloso:
    """Siempre agarra lo adyacente: la hipótesis 'falla la selección'."""

    def __init__(self):
        self.last_usage = {"prompt_tokens": 0, "completion_tokens": 0}

    def describe(self):
        return "fake:goloso"

    def chat_json(self, messages):
        user = messages[-1]["content"]
        if '"rkind": "S2"' in user or "'rkind': 'S2'" in user:
            return {"action": "consume", "args": {"rkind": "S2"}, "sleep_ticks": 1}
        return {"action": "gather", "args": {"target_eid": "r_bad", "amount": 1},
                "sleep_ticks": 1}


def test_la_matriz_detecta_al_goloso(tmp_path):
    s = run_matrix(CFG, FakeGoloso(), repeats=2, far=5,
                   out_path=str(tmp_path / "m.json"))
    assert s["B_ambos_adyacentes"]["elige_malo"] == 1.0
    assert s["C_bueno_lejos"]["elige_malo"] == 1.0
    assert s["simbolo_bueno"] == "S1" and s["valor_bueno"] == 8.0
    assert s["simbolo_malo"] == "S2" and s["valor_malo"] == -2.0
