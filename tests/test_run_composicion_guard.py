"""Tests del guard duro de la ronda de composición (D-034).

Lo que protegen: que el runner NUNCA se lance sin un gate de lectura con
pasa=true. Antes la precondición estaba declarada solo en un comentario y
cualquiera podía lanzar 1728 llamadas saltándose el gate. Ahora `verificar_gate`
aborta con mensaje claro si el archivo no existe, es inválido, o tiene
pasa=false.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from ai.run_composicion import verificar_gate


def test_falla_si_el_archivo_no_existe(tmp_path):
    with pytest.raises(SystemExit, match="GATE FALTANTE"):
        verificar_gate(str(tmp_path / "no_existe.json"))


def test_falla_si_pasa_es_false(tmp_path):
    p = tmp_path / "gate.json"
    p.write_text(json.dumps({
        "pasa": False, "exactitud_agregada": 0.663,
        "por_celda": {"A-0": 0.521, "A-1": 0.490, "B-0": 0.979},
    }))
    with pytest.raises(SystemExit, match="GATE NO PAS"):
        verificar_gate(str(p))


def test_falla_si_pasa_es_el_archivo_real_actual(tmp_path):
    """El archivo de gate real (pasa=false) debe bloquear la ronda."""
    real = (Path(__file__).resolve().parent.parent
            / "data" / "silver" / "gate_lectura_banco_memoria_indexada.json")
    if real.exists():
        with pytest.raises(SystemExit, match="GATE NO PAS"):
            verificar_gate(str(real))


def test_falla_si_no_es_json(tmp_path):
    p = tmp_path / "gate.json"
    p.write_text("esto no es json")
    with pytest.raises(SystemExit, match="GATE INVÁLIDO"):
        verificar_gate(str(p))


def test_pasa_si_pasa_true(tmp_path):
    p = tmp_path / "gate.json"
    p.write_text(json.dumps({
        "pasa": True, "exactitud_agregada": 0.78,
        "por_celda": {"A-0": 0.667, "A-1": 0.667, "B-0": 1.0},
    }))
    d = verificar_gate(str(p))
    assert d["pasa"] is True


def test_pasa_si_pasa_true_y_no_exige_otras_claves(tmp_path):
    """El guard solo exige pasa=true; no inventa requisitos adicionales."""
    p = tmp_path / "gate.json"
    p.write_text(json.dumps({"pasa": True}))
    assert verificar_gate(str(p))["pasa"] is True
