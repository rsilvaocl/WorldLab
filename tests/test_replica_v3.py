"""Tests de la réplica técnica con persistencia completa (D-038).

Lo que protegen: que el crudo tenga TODO lo que la corrida original descartó y
que el agregado se recompute EXACTO desde él. Sin esa reconciliación, volvemos
a tener un agregado que nadie puede auditar.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.run_replica_v3 import (CAMPOS, CONDICIONES, agregar_desde_crudo,
                               reconciliar, verificar_esquema, sha256)


def _fila(**kw):
    base = {"ts": "2026-08-15T00:00:00+00:00", "modelo": "m", "ontologia": 0,
            "condicion": "memoria_indexada", "agente": 0, "rkind": "S2",
            "region": "B", "phase": 1,
            "viv": {"A-0": -2.0, "A-1": 1.0, "B-0": 7.0},
            "predicho": 1.0, "real": 10.0, "nivel_predicho": 3,
            "nivel_real": 5, "correcto": False, "raw_content": '{"e": 1}',
            "parse_ok": True, "error": None, "intentos": 1}
    base.update(kw)
    return base


def _escribir(tmp_path, filas):
    p = tmp_path / "probes_crudos.jsonl"
    p.write_text("\n".join(json.dumps(f, ensure_ascii=False) for f in filas) + "\n")
    return str(p)


def test_el_esquema_exige_los_campos_que_la_corrida_original_descarto():
    """raw_content, error, intentos y timestamp: sin ellos no hay auditoría."""
    for c in ("raw_content", "error", "intentos", "ts", "parse_ok", "viv"):
        assert c in CAMPOS


def test_detecta_un_crudo_al_que_le_falta_un_campo(tmp_path):
    incompleta = _fila(); del incompleta["raw_content"]
    r = verificar_esquema(_escribir(tmp_path, [incompleta]))
    assert "raw_content" in r["campos_faltantes"] and not r["ok"]


def test_exige_AMBOS_brazos():
    """El vacío de la corrida original: solo se persistió memoria_indexada."""
    assert set(CONDICIONES) == {"memoria_indexada", "sin_memoria"}


def test_un_crudo_con_un_solo_brazo_no_pasa(tmp_path):
    r = verificar_esquema(_escribir(tmp_path, [_fila(), _fila(rkind="S1")]))
    assert r["brazos_presentes"] == ["memoria_indexada"]
    assert not r["ambos_brazos"] and not r["ok"]


def test_un_crudo_completo_pasa(tmp_path):
    filas = [_fila(condicion=c, rkind=s)
             for c in CONDICIONES for s in ("S1", "S2", "S4")]
    r = verificar_esquema(_escribir(tmp_path, filas))
    assert r["ok"] and r["ambos_brazos"] and r["n_filas"] == 6


def test_los_nulos_se_cuentan_en_AMBOS_brazos(tmp_path):
    # claves distintas (rkind/agente): son probes DIFERENTES, no duplicados
    filas = ([_fila(condicion="memoria_indexada", rkind="S1", parse_ok=False, predicho=None)] +
             [_fila(condicion="memoria_indexada", rkind="S2")] +
             [_fila(condicion="memoria_indexada", rkind="S4")] +
             [_fila(condicion="sin_memoria", rkind="S1", parse_ok=False, predicho=None)] +
             [_fila(condicion="sin_memoria", rkind="S2", parse_ok=False, predicho=None)] +
             [_fila(condicion="sin_memoria", rkind="S4")])
    ag = agregar_desde_crudo(_escribir(tmp_path, filas))
    comp = ag["m"]["componentes_por_condicion"]
    assert comp["memoria_indexada"]["nulos"] == 1
    assert comp["sin_memoria"]["nulos"] == 2, (
        "los nulos de sin_memoria son justo lo que la corrida original no registró")


def test_los_reintentos_se_agregan(tmp_path):
    filas = [_fila(rkind="S1", intentos=3), _fila(rkind="S2", intentos=1),
             _fila(condicion="sin_memoria", rkind="S1")]
    ag = agregar_desde_crudo(_escribir(tmp_path, filas))
    assert ag["m"]["componentes_por_condicion"]["memoria_indexada"]["reintentos_totales"] == 2


def test_el_agregado_reconcilia_EXACTO_con_el_crudo(tmp_path):
    filas = [_fila(ontologia=o, condicion=c, rkind=s, correcto=(s == "S1"))
             for o in range(3) for c in CONDICIONES for s in ("S1", "S2", "S4")]
    crudo = _escribir(tmp_path, filas)
    ag_path = tmp_path / "agregado.json"
    json.dump(agregar_desde_crudo(crudo), open(ag_path, "w"))
    assert reconciliar(crudo, str(ag_path))["reconcilia"]


def test_un_agregado_manipulado_NO_reconcilia(tmp_path):
    filas = [_fila(ontologia=o, condicion=c, rkind=s, correcto=(s == "S1"))
             for o in range(3) for c in CONDICIONES for s in ("S1", "S2", "S4")]
    crudo = _escribir(tmp_path, filas)
    ag = agregar_desde_crudo(crudo)
    ag["m"]["difs"][0] = -0.99                      # alguien "mejora" el resultado
    ag_path = tmp_path / "agregado.json"
    json.dump(ag, open(ag_path, "w"))
    r = reconciliar(crudo, str(ag_path))
    assert not r["reconcilia"] and "m" in r["discrepan"]


def test_el_checksum_cambia_si_cambia_un_byte(tmp_path):
    p = tmp_path / "x.jsonl"; p.write_text("a\n"); h1 = sha256(str(p))
    p.write_text("b\n")
    assert sha256(str(p)) != h1


def test_los_duplicados_se_detectan_y_se_verifica_que_CONCUERDEN(tmp_path):
    """Retomar una corrida interrumpida puede repetir probes. Con temperature=0
    deberían coincidir carácter a carácter; si no, es evidencia de que la
    decodificación no es determinista y hay que reportarlo."""
    from ai.run_replica_v3 import duplicados
    a = _fila(); b = _fila()                       # mismo probe, misma respuesta
    d = duplicados([a, b])
    assert d["repetidos"] == 1 and d["deterministico"] and d["unicos"] == 1


def test_duplicados_DISCORDANTES_abortan_el_agregado(tmp_path):
    """No se promedia ni se elige uno: se levanta y se reporta."""
    import pytest
    a = _fila(predicho=1.0, raw_content='{"e":1}')
    b = _fila(predicho=9.0, raw_content='{"e":9}')   # el mismo probe, otra respuesta
    d = duplicados_wrapper([a, b])
    assert d["discordantes"] == 1 and not d["deterministico"]
    with pytest.raises(RuntimeError, match="no fue determinista"):
        agregar_desde_crudo(_escribir(tmp_path, [a, b]))


def duplicados_wrapper(filas):
    from ai.run_replica_v3 import duplicados
    return duplicados(filas)


def test_un_duplicado_concordante_NO_infla_el_conteo(tmp_path):
    filas = [_fila(condicion=c, rkind=s) for c in CONDICIONES for s in ("S1","S2","S4")]
    ag1 = agregar_desde_crudo(_escribir(tmp_path, filas))
    ag2 = agregar_desde_crudo(_escribir(tmp_path, filas + filas))   # todo repetido
    assert ag1["m"]["tasas"] == ag2["m"]["tasas"], "el duplicado alteró las tasas"
