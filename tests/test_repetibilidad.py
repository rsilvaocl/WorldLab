"""Tests del runner de repetibilidad (D-039).

Lo que protegen: que la selección sea determinista y reproducible, que el
artefacto guarde lo que faltaba (claves, ambas respuestas, timestamps), y que
el resumen NO afirme determinismo ni estime tasas con n=10.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.run_repetibilidad import N_POR_MODELO, SEED, resumir, seleccionar


def _crudo(tmp_path, n_ont=20):
    filas = [{"modelo": m, "ontologia": o, "condicion": c, "agente": a,
              "rkind": r, "ts": "2026-08-15T00:00:00+00:00",
              "predicho": 1.0, "raw_content": "{}"}
             for m in ("gemma2:9b", "llama3.1:8b")
             for o in range(n_ont) for c in ("memoria_indexada", "sin_memoria")
             for a in (0, 1) for r in ("S1", "S2", "S4")]
    p = tmp_path / "crudo.jsonl"
    p.write_text("\n".join(json.dumps(f) for f in filas) + "\n")
    return str(p)


def test_la_seleccion_es_determinista_y_reproducible(tmp_path):
    """Cualquiera puede reproducir exactamente qué probes se eligieron."""
    c = _crudo(tmp_path)
    assert seleccionar(c) == seleccionar(c)
    assert seleccionar(c, seed=SEED) != seleccionar(c, seed=SEED + 1)


def test_selecciona_N_por_modelo(tmp_path):
    sel = seleccionar(_crudo(tmp_path))
    assert set(sel) == {"gemma2:9b", "llama3.1:8b"}
    assert all(len(v) == N_POR_MODELO for v in sel.values())
    for v in sel.values():
        assert len(set(v)) == len(v), "no debe repetir claves"


def test_el_n_esta_congelado_y_no_se_amplia():
    """Terra: 4 discordancias bastan para refutar determinismo; 10 casos NO
    bastan para estimar una tasa de inestabilidad."""
    assert N_POR_MODELO == 10 and SEED == 7


def _comp(modelo, identico, n):
    return [{"clave": {"modelo": modelo, "ontologia": i, "condicion": "x",
                       "agente": 0, "rkind": "S1"},
             "identico": identico} for i in range(n)]


def test_el_resumen_NO_afirma_determinismo(tmp_path):
    """Con 10/10 se dice 'no se observaron discordancias', no 'es determinista'."""
    p = tmp_path / "c.jsonl"
    p.write_text("\n".join(json.dumps(f) for f in _comp("gemma2:9b", True, 10)) + "\n")
    r = resumir(str(p))["gemma2:9b"]
    assert r["lectura"] == "10/10 idénticos; no se observaron discordancias"
    assert "determinista" not in r["lectura"]


def test_el_resumen_NO_estima_una_tasa(tmp_path):
    """Con 6/10 se reportan las discordancias observadas, no un '40%'."""
    filas = _comp("deepseek-v4-flash", True, 6) + _comp("deepseek-v4-flash", False, 4)
    p = tmp_path / "c.jsonl"
    p.write_text("\n".join(json.dumps(f) for f in filas) + "\n")
    r = resumir(str(p))["deepseek-v4-flash"]
    assert r["discordantes"] == 4 and r["n"] == 10
    assert "%" not in r["lectura"] and "tasa" not in r["lectura"]
    assert r["lectura"] == "6/10 idénticos; 4 discordancias observadas"
