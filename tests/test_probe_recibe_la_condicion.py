"""El probe de composición DEBE llevar la manipulación de cada condición.

Bug encontrado el 14/08, sobre la métrica PRIMARIA: `predict_effect` armaba un
prompt desnudo, sin `system_rules` y sin `memory`. Las tres condiciones LLM
recibían mensajes byte-idénticos (118 y 221 caracteres), así que el probe de
composición nunca pudo distinguirlas: medía a un modelo adivinando.

Y habría vuelto inútil la Fase E (D-033) — entregar experiencias a mano a una
memoria que después nadie lee.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.llm_agent import LLMAgent
from ai.memory import LiteralMemory
from ai.run_pilot import make_world_config, oracle_rules, world_geometry


class SpyClient:
    def __init__(self):
        self.mensajes = None
        self.last_usage = {"prompt_tokens": 0, "completion_tokens": 0}

    def describe(self):
        return "spy"

    def chat_json(self, messages):
        self.mensajes = messages
        return {"energy_change": 0}

    def texto(self):
        return self.mensajes[0]["content"] + "\n" + self.mensajes[1]["content"]


class Ev:
    day, tick, eid, action, outcome = 1, 0, "a0", "consume", "ok"

    def __init__(self, r, reg, ph, g):
        self.detail = {"resource": r, "region": reg, "phase": ph, "energy_gain": g}


def _memoria_de_tres_celdas():
    mem = LiteralMemory(max_items=80, label="memory")
    for ev in (Ev("S2", "A", 0, -2.0), Ev("S2", "A", 1, 1.0), Ev("S2", "B", 0, 7.0)):
        mem.record(ev)
    return mem


def _agentes():
    cfg = make_world_config(30)
    geo = world_geometry(cfg)
    return {
        "oraculo": LLMAgent("a0", SpyClient(), goal="g",
                            system_rules=oracle_rules(cfg), geometry=geo),
        "memoria": LLMAgent("a0", SpyClient(), goal="g", geometry=geo,
                            memory=_memoria_de_tres_celdas()),
        "sin_memoria": LLMAgent("a0", SpyClient(), goal="g", geometry=geo),
    }


def test_las_condiciones_NO_reciben_el_mismo_prompt():
    """El fallo original: los tres mensajes eran idénticos carácter a carácter."""
    ags = _agentes()
    for a in ags.values():
        a.predict_effect("S2", "B", 1)
    textos = {n: a.client.texto() for n, a in ags.items()}
    assert len(set(textos.values())) == 3, (
        "si dos condiciones reciben el mismo prompt, el probe no las distingue")


def test_el_oraculo_recibe_su_tabla():
    a = _agentes()["oraculo"]
    a.predict_effect("S2", "B", 1)
    t = a.client.texto()
    assert "Consumir 1 de S2 en región B durante fase 1" in t


def test_memoria_recibe_sus_recuerdos_con_region_fase_y_ganancia():
    """Sin esos tres campos no hay con qué componer B-oscura."""
    a = _agentes()["memoria"]
    a.predict_effect("S2", "B", 1)
    t = a.client.texto()
    # D-035: el render es prosa canónica, no JSON — la fase va en palabras
    for clave in ("region A", "region B", "fase 1 (oscura)", "+7", "S2"):
        assert clave in t, f"falta {clave} en el prompt de memoria"


def test_sin_memoria_no_recibe_ni_tabla_ni_recuerdos():
    """Es el control: si recibiera algo, dejaría de ser el piso."""
    a = _agentes()["sin_memoria"]
    a.predict_effect("S2", "B", 1)
    t = a.client.texto()
    assert "Consumir 1 de S2" not in t
    assert "energia observada" not in t
    assert "PREGUNTA HIPOTÉTICA" in t


def test_memoria_NO_recibe_la_tabla_del_oraculo():
    """La ventaja del oráculo tiene que seguir siendo suya y solo suya."""
    a = _agentes()["memoria"]
    a.predict_effect("S2", "B", 1)
    assert "Conocimiento especial del mundo" not in a.client.texto()


def test_la_pregunta_sigue_siendo_forced_choice_y_no_revela_la_respuesta():
    """El probe pregunta sin decir: la celda retenida no puede venir servida
    a quien no la tiene por su condición."""
    for nombre in ("memoria", "sin_memoria"):
        a = _agentes()[nombre]
        a.predict_effect("S2", "B", 1)
        t = a.client.texto()
        assert "+10" not in t and "10.0" not in t, (
            f"{nombre}: el valor de B-oscura se filtró al prompt")


def test_la_memoria_vacia_no_ensucia_el_prompt():
    cfg = make_world_config(30)
    a = LLMAgent("a0", SpyClient(), goal="g",
                 memory=LiteralMemory(max_items=10, label="memory"))
    a.predict_effect("S2", "B", 1)
    t = a.client.texto()
    assert "[]" in t, "una memoria vacía se muestra vacía, no se omite"  # lista vacía
    assert "PREGUNTA HIPOTÉTICA" in t
