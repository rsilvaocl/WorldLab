"""Tests del probe de observabilidad (diagnóstico de instrumento).

El probe no mide al modelo: mide qué información está presente en la
observación que el modelo recibió. Estos tests fijan el ground truth y el
muestreo para que un resultado bajo en Q3 no pueda achacarse al probe.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.probe_observability import (
    load_observations, region_of, truth_step_to_B, run,
)
from ai.run_pilot import make_world_config, oracle_truth

_TRUTH = oracle_truth(make_world_config(30))


class ObsFakeClient:
    """Cliente que lee `region` y la tabla, pero NO sabe dónde queda B.

    Es la hipótesis nula del probe: un agente perfecto en todo lo que la
    observación contiene, ciego en lo que no contiene.
    """

    def __init__(self):
        self.last_usage = {"prompt_tokens": 0, "completion_tokens": 0}
        self.calls = []

    def describe(self):
        return "fake:observability"

    def chat_json(self, messages):
        user = messages[-1]["content"]
        self.calls.append(user)
        # el JSON es la PRIMERA línea tras "Estado actual:"; después viene la
        # línea de contexto en prosa (LLMAgent.context_line) y luego la pregunta
        obs = json.loads(user.split("Estado actual:\n", 1)[1].split("\n", 1)[0])
        if '"region"' in user.split("Estado actual:")[0] or "¿en qué región estás" in user:
            return {"region": obs["region"], "reason": "lo dice mi observación"}
        if "cambiaría tu energía" in user:
            val = _TRUTH[("S2", obs["region"], int(obs["phase"]))]
            return {"energy_change": val, "reason": "tabla del oráculo"}
        # rumbo a B: sin información en la observación, adivina
        return {"dx": -1, "dy": 0, "reason": "no sé dónde queda B"}


def write_traces(tmp_path, rows):
    p = tmp_path / "t_traces.jsonl"
    with open(p, "w", encoding="utf-8") as f:
        f.write(json.dumps({"type": "meta", "kind": "agent_trace"}) + "\n")
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return str(p)


def make_rows():
    """Observaciones con el rumbo DEDUCIBLE: cada una ve una entidad de B.

    Las x elegidas dejan la frontera (x=15) dentro del radio de visión 6, que
    es la única situación en que Q3 tiene respuesta posible tras D-029. Si el
    agente no ve ninguna entidad de la otra región, el rumbo sigue siendo
    indeducible y el probe no lo puntúa.
    """
    rows = []
    for day in range(2, 8):
        for i, x in enumerate((10, 12, 14)):
            rows.append({
                "type": "trace", "eid": f"a{i}", "day": day, "tick": 0,
                "observation": {"day": day, "tick": 0, "energy": 50.0,
                                "position": [x, 12], "region": "A", "phase": 0,
                                "inventory": {}, "heard": [],
                                "visible": [{"dx": 15 - x, "dy": 0, "eid": "r_b",
                                             "kind": "resource", "region": "B",
                                             "rkind": "S2"}],
                                "acciones_disponibles": []},
            })
    return rows


def test_region_de_una_x_respeta_la_frontera():
    assert region_of(14, 15) == "A"
    assert region_of(15, 15) == "B"


def test_rumbo_correcto_es_hacia_x_creciente_y_no_se_puntua_dentro_de_B():
    assert truth_step_to_B(14, 15) == +1
    assert truth_step_to_B(0, 15) == +1
    assert truth_step_to_B(20, 15) is None   # ya está en B: no es navegación


def test_muestreo_reparte_entre_agentes_y_salta_el_dia_1(tmp_path):
    rows = make_rows()
    rows.append({"type": "trace", "eid": "a0", "day": 1, "tick": 0,
                 "observation": {"position": [1, 1], "region": "A", "phase": 0}})
    path = write_traces(tmp_path, rows)

    picked = load_observations(path, n=6, seed=42, skip_first_day=True)
    assert len(picked) == 6
    assert all(r["day"] > 1 for r in picked), "el día 1 precede a la expulsión de B"
    assert len(set(r["eid"] for r in picked)) == 3, "debe repartir entre agentes"


def test_dia_1_se_incluye_si_se_pide(tmp_path):
    rows = make_rows()
    rows.append({"type": "trace", "eid": "a9", "day": 1, "tick": 0,
                 "observation": {"position": [1, 1], "region": "A", "phase": 0}})
    path = write_traces(tmp_path, rows)
    picked = load_observations(path, n=50, seed=1, skip_first_day=False)
    assert any(r["day"] == 1 for r in picked)


def test_agente_ciego_al_rumbo_acierta_q1_q2_y_falla_q3(tmp_path):
    """La firma que buscamos: lectura y tabla perfectas, navegación en el suelo."""
    path = write_traces(tmp_path, make_rows())
    out = str(tmp_path / "probe.jsonl")

    summary = run(path, ObsFakeClient(), "system", n=6, seed=42, split_x=15,
                  rkind="S2", out_path=out, skip_first_day=True,
                  truth=_TRUTH)

    assert summary["q1_region_acc"] == 1.0
    assert summary["q2_value_acc"] == 1.0
    assert summary["q3_heading_acc"] == 0.0
    assert summary["q3_scored_n"] == 6, "todas las muestras estaban en A"


def test_escribe_jsonl_y_summary(tmp_path):
    path = write_traces(tmp_path, make_rows())
    out = str(tmp_path / "sub" / "probe.jsonl")
    run(path, ObsFakeClient(), "system", n=3, seed=7, split_x=15,
        rkind="S2", out_path=out, skip_first_day=True,
        truth=_TRUTH)

    lines = [json.loads(l) for l in open(out, encoding="utf-8")]
    assert len(lines) == 3
    assert {"q1_correct", "q2_correct", "q3_correct", "distance_to_B"} <= set(lines[0])
    assert Path(out.replace(".jsonl", "_summary.json")).exists()


def test_muestras_dentro_de_B_no_se_puntuan_como_navegacion(tmp_path):
    rows = [{"type": "trace", "eid": "a0", "day": 3, "tick": 0,
             "observation": {"day": 3, "tick": 0, "position": [20, 12],
                             "region": "B", "phase": 0, "inventory": {},
                             "visible": [], "heard": [], "acciones_disponibles": []}}]
    path = write_traces(tmp_path, rows)
    summary = run(path, ObsFakeClient(), "system", n=1, seed=1, split_x=15,
                  rkind="S2", out_path=str(tmp_path / "p.jsonl"),
                  skip_first_day=True, truth=_TRUTH)
    assert summary["q3_scored_n"] == 0
    assert summary["q3_heading_acc"] is None


# ----------------------------------------------------------------------
# Defectos del instrumento encontrados al auditar la primera corrida del probe
# (2026-08-13). Los tres convertían una respuesta correcta en "no contestó" o
# en "contestó mal". Quedan fijados para que no vuelvan.

def test_num_no_confunde_el_indice_del_simbolo_con_el_valor():
    """`re.search(r"[-+]?\\d+", "S2: -2")` devuelve 2, no -2.

    Un modelo que contestaba "S2: -2" tenía razón y se registraba equivocado.
    """
    from ai.probe_observability import _num
    assert _num("S2: -2") == -2.0
    assert _num("S2 en A-clara vale -2") == -2.0
    assert _num("S1: +8") == 8.0
    assert _num("-2") == -2.0
    assert _num(-2) == -2.0
    assert _num("+1") == 1.0
    assert _num("sin dato") is None
    assert _num(True) is None, "un bool no es un cambio de energía"


def test_json_con_signo_mas_explicito_se_parsea():
    """Le PEDIMOS al modelo "el número con signo" y JSON no admite `+1`.

    El modelo que obedecía la instrucción producía JSON inválido y su
    predicción — posiblemente correcta — se guardaba como null, indistinguible
    de no haber contestado. Afecta a predict_effect (D-010), que es la
    medición primaria del experimento.
    """
    from ai.model_adapter import LLMClient
    assert LLMClient._extract_json('{"energy_change": +1}') == {"energy_change": 1}
    assert LLMClient._extract_json(
        '{"energy_change": +9, "reason": "x"}') == {"energy_change": 9, "reason": "x"}
    # sigue funcionando lo que ya funcionaba
    assert LLMClient._extract_json('{"energy_change": -2}') == {"energy_change": -2}
    assert LLMClient._extract_json(
        '```json\n{"action": "rest"}\n```') == {"action": "rest"}


def test_el_signo_mas_dentro_de_una_cadena_no_se_toca():
    """La reparación es de posición de VALOR, no un reemplazo global."""
    from ai.model_adapter import LLMClient
    out = LLMClient._extract_json('{"energy_change": +1, "reason": "sube +1 por tick"}')
    assert out["energy_change"] == 1
    assert out["reason"] == "sube +1 por tick", "el texto libre no se altera"


def test_el_probe_guarda_la_respuesta_cruda(tmp_path):
    """Sin el crudo no se puede distinguir 'el modelo dijo mal' de 'el parser
    lo rompió' — que es exactamente la duda que abrió esta auditoría."""
    path = write_traces(tmp_path, make_rows())
    out = str(tmp_path / "probe.jsonl")
    run(path, ObsFakeClient(), "system", n=2, seed=42, split_x=15,
        rkind="S2", out_path=out, skip_first_day=True,
        truth=_TRUTH)
    rows = [json.loads(l) for l in open(out, encoding="utf-8")]
    for r in rows:
        assert r["q1_raw"] and r["q2_raw"] and r["q3_raw"]
        assert "reason" in r["q2_raw"]


# ----------------------------------------------------------------------
# Defecto encontrado al auditar el probe post-fix (D-029 aplicado, 2026-08-13):
# Q3 se puntuaba sobre las 12 muestras cuando solo 3 eran contestables. Tras
# D-029 cada entidad visible trae su región, pero el radio de visión es 6: si
# ninguna entidad de la otra región está a la vista, el rumbo sigue siendo
# indeducible y puntuarlo mide otra vez una pregunta imposible.

def _obs(x, visible):
    return {"day": 3, "tick": 0, "energy": 50.0, "position": [x, 12],
            "region": "A", "phase": 0, "inventory": {}, "heard": [],
            "acciones_disponibles": [], "visible": visible}


def test_q3_solo_puntua_donde_el_rumbo_es_deducible(tmp_path):
    rows = [
        # sin vecinos de B a la vista: indeducible, NO se puntúa
        {"type": "trace", "eid": "a0", "day": 3, "tick": 0,
         "observation": _obs(4, [{"dx": -1, "dy": 0, "eid": "r1",
                                  "kind": "resource", "region": "A"}])},
        # con un recurso de B visible: deducible, SÍ se puntúa
        {"type": "trace", "eid": "a1", "day": 3, "tick": 0,
         "observation": _obs(13, [{"dx": 5, "dy": -6, "eid": "r2",
                                   "kind": "resource", "region": "B"}])},
    ]
    path = write_traces(tmp_path, rows)
    summary = run(path, ObsFakeClient(), "system", n=2, seed=1, split_x=15,
                  rkind="S2", out_path=str(tmp_path / "p.jsonl"),
                  skip_first_day=True, truth=_TRUTH)

    assert summary["q3_scored_n"] == 1, "solo la muestra con B a la vista puntúa"
    assert summary["q3_derivable_n"] == 1
    # el cliente falso siempre contesta oeste => falla la única puntuable
    assert summary["q3_heading_acc"] == 0.0
    # y la tasa sobre todas existe aparte, para ver cuánto alcanza el gradiente
    assert summary["q3_heading_acc_todas"] == 0.0

    filas = [json.loads(l) for l in open(tmp_path / "p.jsonl", encoding="utf-8")]
    por_x = {f["position"][0]: f for f in filas}
    assert por_x[4]["q3_derivable"] is False
    assert por_x[13]["q3_derivable"] is True
    assert por_x[13]["q3_dx_vecinos_otra_region"] == [5]


def test_el_probe_arma_el_prompt_igual_que_el_agente(tmp_path):
    """Si el probe y el bucle de acción construyen el mensaje distinto, el
    probe deja de medir las condiciones del agente y mide las suyas."""
    from ai.llm_agent import LLMAgent
    path = write_traces(tmp_path, make_rows())
    client = ObsFakeClient()
    run(path, client, "system", n=1, seed=1, split_x=15, rkind="S2",
        out_path=str(tmp_path / "p.jsonl"), skip_first_day=True, truth=_TRUTH)
    esperado = LLMAgent.context_line({"region": "A", "phase": 0})
    assert esperado == "Estás en la región A, en la fase 0 (clara)."
    assert all(esperado in c for c in client.calls), (
        "cada llamada del probe debe llevar la misma línea de contexto que el agente")


def test_context_line_no_inventa_nada_que_no_este_en_la_observacion():
    from ai.llm_agent import LLMAgent
    assert LLMAgent.context_line({"region": "B", "phase": 1}) == \
        "Estás en la región B, en la fase 1 (oscura)."
    # solo reafirma campos existentes: sin region/phase no fabrica valores
    linea = LLMAgent.context_line({})
    assert "región ," in linea and "fase 0 (clara)" in linea


def test_thinking_se_traduce_al_payload_de_la_api():
    """DeepSeek v4 razona por defecto. Sobre el prompt real del agente eso son
    58.5 s y 5076 tokens de salida por decisión contra 1.2 s y 29 sin razonar,
    sin ninguna ganancia de precisión (D-031). El flag tiene que llegar al
    payload o la corrida cuesta 49x sin que nadie lo note."""
    from ai.model_adapter import LLMClient
    import json as _json

    capturado = {}

    class FakeReq:
        def __init__(self, url, data=None, headers=None, method=None):
            capturado["payload"] = _json.loads(data.decode())

    c = LLMClient(backend="ollama", model="x", thinking=False)
    assert c.thinking is False
    c2 = LLMClient(backend="ollama", model="x")
    assert c2.thinking is None, "sin especificar, se respeta el default del proveedor"

    import ai.model_adapter as mod
    orig = mod.urllib.request.Request
    mod.urllib.request.Request = FakeReq
    try:
        for th, esperado in ((False, "disabled"), (True, "enabled"), (None, None)):
            capturado.clear()
            cli = LLMClient(backend="ollama", model="x", thinking=th)
            try:
                cli.chat_json([{"role": "user", "content": "hola"}])
            except Exception:
                pass   # la request falsa no responde; solo interesa el payload
            if esperado is None:
                assert "thinking" not in capturado["payload"]
            else:
                assert capturado["payload"]["thinking"] == {"type": esperado}
    finally:
        mod.urllib.request.Request = orig
