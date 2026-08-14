"""Tests del banco de selección del oráculo.

El banco decide qué modelo corre la ronda. Si su desagregado miente, elegimos
mal el techo del experimento. Lo que se fija acá es que el promedio NUNCA
pueda tapar el colapso de una dimensión — que es exactamente el defecto que
qwen2.5:7b exhibió (6/12 de promedio escondiendo 6/6 y 0/6).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.bench_oraculo import bench_model, cells
from ai.probe_observability import TRUTH


class FakeClient:
    """Cliente parametrizable: acierta o falla según la dimensión pedida."""

    def __init__(self, model="fake", ciego_a=None, responde=None):
        self.model = model
        self.ciego_a = ciego_a          # "fase" | "region" | None
        self.responde = responde        # callable(rkind, region, phase) -> valor
        self.last_usage = {"prompt_tokens": 0, "completion_tokens": 0}
        self.calls = 0

    def describe(self):
        return f"fake:{self.model}"

    def chat_json(self, messages):
        self.calls += 1
        user = messages[-1]["content"]
        rkind = next(s for s in ("S1", "S2", "S3", "S4") if f"'{s}'" in user)
        region = "A" if "región A" in user else "B"
        phase = 1 if "fase oscura" in user else 0
        if self.responde is not None:
            return {"energy_change": self.responde(rkind, region, phase)}
        if self.ciego_a == "fase":
            # colapsa la fase: contesta siempre la celda de fase 0
            return {"energy_change": TRUTH[(rkind, region, 0)]}
        if self.ciego_a == "region":
            return {"energy_change": TRUTH[(rkind, "A", phase)]}
        return {"energy_change": TRUTH[(rkind, region, phase)]}


def _bench(client, monkeypatch, repeats=1):
    import ai.bench_oraculo as mod
    monkeypatch.setattr(mod, "LLMClient", lambda **kw: client)
    return mod.bench_model(client.model, "ollama", "system", repeats, 60.0)


def test_las_16_celdas_cubren_las_dos_dimensiones_y_la_retenida():
    cs = cells()
    assert len(cs) == 16
    assert len(set(cs)) == 16
    assert ("S2", "B", 1) in cs, "la celda retenida debe estar en el banco"
    assert {c[1] for c in cs} == {"A", "B"}
    assert {c[2] for c in cs} == {0, 1}


def test_oraculo_perfecto_da_1_en_todas_las_dimensiones(monkeypatch):
    r = _bench(FakeClient("perfecto"), monkeypatch)
    assert r["exact_acc"] == 1.0
    assert r["por_region"] == {"A": 1.0, "B": 1.0}
    assert r["por_fase"] == {"0": 1.0, "1": 1.0}
    assert r["celda_retenida_B_oscura"] == 1.0
    assert r["sin_respuesta"] == 0


def test_el_desagregado_destapa_el_colapso_de_fase(monkeypatch):
    """El caso qwen2.5:7b: promedio decente, una dimensión en el suelo."""
    r = _bench(FakeClient("ciego_fase", ciego_a="fase"), monkeypatch)
    assert r["por_fase"]["0"] == 1.0
    assert r["por_fase"]["1"] < 1.0, "colapsar la fase debe verse en el corte"
    assert r["por_region"]["A"] == r["por_region"]["B"], (
        "un ciego a la fase liga la región igual de bien en ambas: el promedio "
        "por región no delata nada, por eso el corte por fase es obligatorio")
    assert r["exact_acc"] > r["por_fase"]["1"], "el promedio tapa el colapso"


def test_el_desagregado_destapa_el_colapso_de_region(monkeypatch):
    r = _bench(FakeClient("ciego_region", ciego_a="region"), monkeypatch)
    assert r["por_region"]["A"] == 1.0
    assert r["por_region"]["B"] < 1.0
    # S3 vale 0 en las 4 celdas (control, D-022), así que un ciego a la región
    # lo acierta por coincidencia: el techo de un ciego es 1/4, no 0.
    assert r["celda_retenida_B_oscura"] == 0.25, (
        "quien no liga región solo acierta la celda retenida en el símbolo control")
    fallos = [x for x in r["rows"]
              if x["region"] == "B" and x["phase"] == 1 and not x["exact"]]
    assert {x["rkind"] for x in fallos} == {"S1", "S2", "S4"}, (
        "los tres símbolos con efecto real deben fallar")


def test_sin_respuesta_no_cuenta_como_acierto(monkeypatch):
    r = _bench(FakeClient("mudo", responde=lambda *a: None), monkeypatch)
    assert r["sin_respuesta"] == 16
    assert r["exact_acc"] == 0.0


def test_el_calentamiento_queda_fuera_del_cronometro(monkeypatch):
    """La primera llamada carga el modelo; en producción queda residente."""
    c = FakeClient("carga")
    r = _bench(c, monkeypatch)
    assert c.calls == 17, "16 celdas + 1 calentamiento"
    assert r["n"] == 16, "el calentamiento no entra en el conteo"


def test_repeats_multiplica_las_celdas(monkeypatch):
    r = _bench(FakeClient("rep"), monkeypatch, repeats=2)
    assert r["n"] == 32


def test_nivel_de_magnitud_es_mas_indulgente_que_exacto(monkeypatch):
    """level_acc usa los 6 niveles de D-010: un modelo cercano pero no exacto
    puede servir de techo aunque falle la igualdad estricta."""
    def casi(rkind, region, phase):
        return TRUTH[(rkind, region, phase)] + 0.4
    r = _bench(FakeClient("casi", responde=casi), monkeypatch)
    assert r["exact_acc"] == 0.0
    assert r["level_acc"] > 0.5
