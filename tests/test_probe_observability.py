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
    TRUTH, load_observations, region_of, truth_step_to_B, run,
)


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
        obs = json.loads(user.split("Estado actual:\n", 1)[1].split("\n\n", 1)[0])
        if '"region"' in user.split("Estado actual:")[0] or "¿en qué región estás" in user:
            return {"region": obs["region"], "reason": "lo dice mi observación"}
        if "cambiaría tu energía" in user:
            val = TRUTH[("S2", obs["region"], int(obs["phase"]))]
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
    rows = []
    for day in range(2, 8):
        for i, x in enumerate((4, 10, 14)):
            rows.append({
                "type": "trace", "eid": f"a{i}", "day": day, "tick": 0,
                "observation": {"day": day, "tick": 0, "energy": 50.0,
                                "position": [x, 12], "region": "A", "phase": 0,
                                "inventory": {}, "visible": [], "heard": [],
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
                  rkind="S2", out_path=out, skip_first_day=True)

    assert summary["q1_region_acc"] == 1.0
    assert summary["q2_value_acc"] == 1.0
    assert summary["q3_heading_acc"] == 0.0
    assert summary["q3_scored_n"] == 6, "todas las muestras estaban en A"


def test_escribe_jsonl_y_summary(tmp_path):
    path = write_traces(tmp_path, make_rows())
    out = str(tmp_path / "sub" / "probe.jsonl")
    run(path, ObsFakeClient(), "system", n=3, seed=7, split_x=15,
        rkind="S2", out_path=out, skip_first_day=True)

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
                  skip_first_day=True)
    assert summary["q3_scored_n"] == 0
    assert summary["q3_heading_acc"] is None
