"""Tests de la métrica de exposición por celda (Opus, 12/08):
sin exposición en una celda vivida, un fallo del probe retenido es
'no tenía qué componer', no 'no compuso'."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.analyze_pilot import exposure_per_cell, exposure_summary, MIN_EXPOSURE


def write_events(tmp_path, events):
    p = tmp_path / "piloto_memoria_7_s1_seed1.jsonl"
    lines = [json.dumps(e, ensure_ascii=False) for e in events]
    p.write_text("\n".join(lines) + "\n")
    return p


def consume(eid, region, phase, n):
    return [{"type": "event", "eid": eid, "action": "consume", "outcome": "ok",
             "day": 1, "tick": i, "detail": {"region": region, "phase": phase,
                                             "resource": "S1", "energy_gain": 8.0}}
            for i in range(n)]


def test_exposure_counts_per_cell(tmp_path):
    events = (consume("a0", "A", 0, 4) + consume("a0", "A", 1, 2) +
              consume("a0", "B", 0, 5) + consume("a0", "B", 1, 1))
    p = write_events(tmp_path, events)
    counts = exposure_per_cell(p, "a0")
    assert counts[("A", 0)] == 4
    assert counts[("A", 1)] == 2
    assert counts[("B", 0)] == 5


def test_subexposed_detected(tmp_path):
    """a0 tiene 3+ consumos en todas las celdas (expuesto); a1 solo en A-clara
    (sub-expuesto: nunca cruzó a B ni comió de noche)."""
    events = (consume("a0", "A", 0, 4) + consume("a0", "A", 1, 3) + consume("a0", "B", 0, 5)
              + consume("a1", "A", 0, 2))  # a1: solo 2 en A-clara, 0 en las otras
    p = write_events(tmp_path, events)
    # probes sintéticos para el summary — el nombre real es
    # piloto_{cond}_{dens}_s{seed}_probes.jsonl (sin _seed1)
    probes = [{"eid": "a0", "never_lived": False}, {"eid": "a1", "never_lived": False}]
    (tmp_path / "piloto_memoria_7_s1_probes.jsonl").write_text(
        "\n".join(json.dumps(x) for x in probes) + "\n")
    results = [{"condition": "memoria", "density": 0.07, "seed": 1}]
    summary = exposure_summary(results, tmp_path)
    assert summary["total_agents"] == 2
    assert len(summary["subexposed"]) == 1
    se = summary["subexposed"][0]
    assert se["eid"] == "a1"
    assert "A-1" in se["low_cells"] and "B-0" in se["low_cells"]
    assert summary["frac_subexposed"] == 0.5


def test_subexposed_threshold():
    """Corte exacto: 3 consumos = expuesto; 2 = sub-expuesto (Opus)."""
    assert MIN_EXPOSURE == 3
