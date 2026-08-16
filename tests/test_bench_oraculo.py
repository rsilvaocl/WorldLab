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
from ai.run_pilot import make_world_config, oracle_rules, oracle_truth

_TRUTH = oracle_truth(make_world_config(30))


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
            return {"energy_change": _TRUTH[(rkind, region, 0)]}
        if self.ciego_a == "region":
            return {"energy_change": _TRUTH[(rkind, "A", phase)]}
        return {"energy_change": _TRUTH[(rkind, region, phase)]}


def _bench(client, monkeypatch, repeats=1):
    import ai.bench_oraculo as mod
    monkeypatch.setattr(mod, "LLMClient", lambda **kw: client)
    return mod.bench_model(client.model, "ollama", "system", repeats, 60.0,
                           _TRUTH)


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
        return _TRUTH[(rkind, region, phase)] + 0.4
    r = _bench(FakeClient("casi", responde=casi), monkeypatch)
    assert r["exact_acc"] == 0.0
    assert r["level_acc"] > 0.5


def test_la_tabla_plana_no_agrega_informacion():
    """El aplanado es legibilidad, no información nueva: si agregara un hecho
    que la tabla del motor no tiene, dejaría de ser comparable con el resto de
    las condiciones y pasaría a ser una intervención sobre el experimento."""
    import re

    flat = oracle_rules(make_world_config(30))
    # las 16 celdas, exactamente, con su valor. re.escape porque "+8" es un
    # cuantificador si se pasa crudo al motor de regex.
    for (s, r, p), v in _TRUTH.items():
        assert re.search(
            rf"de {s} en región {r} durante fase {p} \([a-z]+\): {re.escape(f'{v:+g}')} ",
            flat), f"falta la celda ({s},{r},{p})={v:+g}"
    assert len(re.findall(r"^- Consumir", flat, re.M)) == 16, "16 celdas, ni una más"
    # y las reglas no-tabulares sobreviven al aplanado
    for clave in ("barrera te expulsa", "regeneran", "struct_a", "superar 100"):
        assert clave in flat


def test_el_prompt_del_oraculo_coincide_con_el_motor():
    """D-030 (1c): para las 16 celdas, lo que dice el prompt del oráculo es
    world.ground_truth_effect(). Si algún día alguien edita la ontología
    (EFFECT_SPEC o build_separable_effects) y no la fuente única, este test
    falla — hoy nada impedía que el oráculo recibiera una tabla que el motor
    no aplica."""
    import re
    from ai.world_state import WorldState

    cfg = make_world_config(days=30)
    world = WorldState(cfg, [])
    text = oracle_rules(cfg)
    truth = oracle_truth(cfg)
    assert len(truth) == 16
    for (s, r, p) in sorted(truth):
        m = re.search(
            rf"de {s} en región {r} durante fase {p} \([a-z]+\): ([+-]?\d+(?:\.\d+)?) ",
            text)
        assert m, f"celda ({s},{r},{p}) no está en el prompt del oráculo"
        valor_en_prompt = float(m.group(1))
        # fuente única == motor (ground_truth_effect lee cfg.consume_effects)
        assert truth[(s, r, p)] == world.ground_truth_effect(s, r, p), \
            f"oracle_truth ≠ motor en ({s},{r},{p})"
        # prompt == motor
        assert valor_en_prompt == world.ground_truth_effect(s, r, p), \
            f"prompt ≠ motor en ({s},{r},{p}): {valor_en_prompt} vs " \
            f"{world.ground_truth_effect(s, r, p)}"
