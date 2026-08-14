"""D-032: la geometría de las regiones va IDÉNTICA en las 4 condiciones.

Lo que estos tests protegen es la comparabilidad. Si la geometría se filtrara
solo a una condición, esa condición tendría una ventaja que no es la que el
experimento manipula, y la métrica de composición dejaría de significar algo.
La única diferencia legítima entre condiciones es `system_rules` (la tabla del
oráculo) y la memoria.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.llm_agent import LLMAgent
from ai.model_adapter import LLMClient
from ai.run_pilot import make_world_config, make_agents, oracle_rules, world_geometry


def _client():
    return LLMClient(backend="ollama", model="x")


CONDICIONES_LLM = ("sin_memoria", "memoria", "oraculo")


def test_la_geometria_sale_de_la_config_y_no_esta_escrita_a_mano():
    """Si alguien mueve la frontera en la config, el prompt la sigue."""
    cfg = make_world_config(30)
    g = world_geometry(cfg)
    split = int(cfg.width * cfg.region_split)
    assert f"x < {split}" in g and f"x >= {split}" in g
    assert f"{cfg.width}x{cfg.height}" in g

    cfg2 = make_world_config(30)
    cfg2.region_split = 0.25
    g2 = world_geometry(cfg2)
    assert f"x < {int(cfg2.width * 0.25)}" in g2
    assert g2 != g, "cambiar la config debe cambiar el texto"


def test_las_tres_condiciones_llm_reciben_la_MISMA_geometria():
    cfg = make_world_config(30)
    geos = {}
    for cond in CONDICIONES_LLM:
        agents = make_agents(cond, "m", _client(), cfg)
        geos[cond] = {a.geometry for a in agents.values()}
        assert len(geos[cond]) == 1, f"{cond}: agentes con geometría distinta"
    unicas = {next(iter(v)) for v in geos.values()}
    assert len(unicas) == 1, "las condiciones no comparten la geometría"
    assert unicas.pop() == world_geometry(cfg)


def test_la_geometria_va_en_la_mecanica_no_en_las_reglas_del_oraculo():
    """Si viviera en system_rules, solo la tendría el oráculo."""
    cfg = make_world_config(30)
    assert world_geometry(cfg) not in oracle_rules(cfg)
    sin_reglas = LLMAgent("a", _client(), goal="g", geometry=world_geometry(cfg))
    assert "OESTE" in sin_reglas._system_prompt(), (
        "una condición sin system_rules igual debe recibir la geometría")


def test_lo_UNICO_que_distingue_al_oraculo_sigue_siendo_su_tabla():
    """Diferencia exacta entre prompts: el bloque de conocimiento especial."""
    cfg = make_world_config(30)
    prompts = {}
    for cond in CONDICIONES_LLM:
        agents = make_agents(cond, "m", _client(), cfg)
        prompts[cond] = next(iter(agents.values()))._system_prompt()

    assert prompts["sin_memoria"] == prompts["memoria"], (
        "sin_memoria y memoria difieren en la MEMORIA, no en el system prompt")

    base = prompts["sin_memoria"]
    oraculo = prompts["oraculo"]
    assert oraculo != base
    # quitarle al oráculo su bloque de reglas debe devolver exactamente la base
    assert oracle_rules(cfg) in oraculo
    sin_tabla = oraculo.replace(
        "Conocimiento especial del mundo (además de la mecánica de arriba):\n"
        + oracle_rules(cfg) + "\n", "")
    assert sin_tabla == base, (
        "el oráculo tiene alguna ventaja ADEMÁS de su tabla: "
        f"{[l for l in sin_tabla.splitlines() if l not in base.splitlines()]}")


def test_la_geometria_no_revela_ningun_efecto():
    """Dice dónde, no qué vale. Ningún valor de la tabla puede aparecer."""
    cfg = make_world_config(30)
    g = world_geometry(cfg)
    for (s, r, p), v in cfg.consume_effects.items():
        if v != 0:
            assert f"{v:+g}" not in g, f"la geometría filtra el efecto de {s}-{r}-{p}"
    for palabra in ("energía", "consumir", "consume", "vale", "gana"):
        assert palabra.lower() not in g.lower(), f"la geometría menciona '{palabra}'"


def test_run_world_arranca_sin_NameError(monkeypatch, tmp_path):
    """Cobertura del LLAMADOR, no solo de make_agents.

    El primer intento de D-032 pasó los 5 tests de arriba y murió en la corrida
    real: un reemplazo de texto había metido `geometry=geometry` también en la
    llamada a make_agents dentro de run_world, donde esa variable no existe.
    Los tests llamaban a make_agents directo y no tocaban ese camino.
    """
    import ai.run_pilot as rp
    llamadas = {}

    def fake_make_agents(condition, model_name, client, world_cfg, force_sleep=None):
        llamadas["ok"] = True
        return {}

    def fake_sim(*a, **k):
        raise RuntimeError("corte deliberado: ya pasamos make_agents")

    monkeypatch.setattr(rp, "make_agents", fake_make_agents)
    monkeypatch.setattr(rp, "Simulator", fake_sim)
    try:
        rp.run_world("oraculo", 0.07, 42, 30, "m", _client(), str(tmp_path))
    except NameError:
        raise AssertionError("run_world referencia una variable inexistente")
    except Exception:
        pass
    assert llamadas.get("ok"), "run_world nunca llegó a construir los agentes"
