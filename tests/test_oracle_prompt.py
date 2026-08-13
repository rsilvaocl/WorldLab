"""Tests del prompt del oráculo — diagnóstico del colapso del piloto.

Hallazgo real (piloto, 96 mundos): el oráculo "solo caminaba" (1.202 move,
cero gather, cero consume). El JSON era 100% válido — no era saturación del
7B. Causa raíz: _system_prompt() reemplazaba TODO el prompt base cuando había
system_rules, y el oráculo perdía la mecánica "dx,dy son pasos de 1 casilla".
Proponía move con distancias imposibles (μ=4.45, 88% >1 casilla).

Fix (D-026): el contrato agente-motor (acciones disponibles + mecánica) va
SIEMPRE, incluso con system_rules. El conocimiento especial del oráculo se
agrega ADEMÁS, no en lugar de.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.llm_agent import LLMAgent


class FakeClient:
    def __init__(self):
        self.last_usage = {"prompt_tokens": 50, "completion_tokens": 10}

    def chat_json(self, messages):
        return {"action": "rest", "args": {}, "sleep_ticks": 1}

    def describe(self):
        return "fake:test"


def make_agent(system_rules=""):
    return LLMAgent("a0", FakeClient(), goal="sobrevivir",
                    system_rules=system_rules)


def test_prompt_base_incluye_mecanica_move_un_paso():
    ag = make_agent()
    p = ag._system_prompt()
    assert "dx,dy" in p
    assert "1 casilla" in p or "una casilla" in p
    assert "acciones_disponibles" in p
    assert "nunca saltes" in p


def test_prompt_base_no_revela_efectos():
    """D-020: el world model NO se presta — sin_memoria no conoce la tabla."""
    ag = make_agent()
    p = ag._system_prompt()
    assert "A-clara" not in p
    assert "+8" not in p
    assert "S1:" not in p


def test_prompt_oraculo_incluye_mecanica_Y_reglas():
    """Fix: el oráculo conserva la mecánica (contrato) Y recibe su tabla."""
    ag = make_agent(system_rules="S1: A-clara +8, A-oscura +4, B-clara -1, B-oscura -5\n")
    p = ag._system_prompt()
    # mecánica presente (lo que faltaba antes)
    assert "acciones_disponibles" in p
    assert "dx,dy" in p
    assert "1 casilla" in p or "una casilla" in p
    # conocimiento especial presente (su ventaja por diseño)
    assert "A-clara +8" in p
    assert "B-oscura -5" in p


def test_prompt_oraculo_no_duplica_mecanica_confundida():
    """El conocimiento especial no debe reemplazar la lista de acciones."""
    ag = make_agent(system_rules="S2: A-clara -2, A-oscura +1, B-clara +7, B-oscura +10\n")
    p = ag._system_prompt()
    assert "move{dx,dy}" in p
    assert "consume{rkind,amount}" in p
    # el oráculo NO debe perder la instrucción de responder JSON
    assert "Responde SOLO con JSON" in p
