"""Tests de D-025: corte de exposición en el análisis (spec v1.1 de Opus).

Un agente con <3 consumos en alguna celda vivida es SUB-EXPONENTE: su probe
retenido no dice "no compuso", dice "no tenía qué componer". El análisis debe
excluir sus probes retenidos del score de composición y reportarlos aparte.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.analyze_pilot import probe_rates, MIN_EXPOSURE


def make_probes(out_dir: Path, eid: str, n_retained: int, correct: bool,
                probe_moment: str = "final"):
    """Escribe un archivo de probes simulado para un agente."""
    path = out_dir / "piloto_baseline_empirico_7_s1_probes.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        # 3 celdas vividas + N retenidas
        for phase in (0, 1):
            f.write(json.dumps({
                "experiment": "piloto_baseline_empirico_7_s1", "eid": eid,
                "rkind": "S1", "region": "A", "phase": phase,
                "never_lived": False, "level_correct": True,
                "predicted_level": 3, "truth_level": 3, "probe_moment": probe_moment,
            }) + "\n")
        f.write(json.dumps({
            "experiment": "piloto_baseline_empirico_7_s1", "eid": eid,
            "rkind": "S1", "region": "B", "phase": 0,
            "never_lived": False, "level_correct": True,
            "predicted_level": 3, "truth_level": 3, "probe_moment": probe_moment,
        }) + "\n")
        for _ in range(n_retained):
            f.write(json.dumps({
                "experiment": "piloto_baseline_empirico_7_s1", "eid": eid,
                "rkind": "S1", "region": "B", "phase": 1,
                "never_lived": True, "level_correct": correct,
                "predicted_level": 4 if correct else 2,
                "truth_level": 4, "probe_moment": probe_moment,
            }) + "\n")


def test_probe_rates_sin_excluir_incluye_subexpuestos(tmp_path):
    make_probes(tmp_path, "a1", n_retained=2, correct=True)
    pr = probe_rates(tmp_path, "baseline_empirico", 0.07, 1)
    # sin marcar sub-expuestos: los 2 retenidos entran al score
    assert pr["n_retained"] == 2
    assert pr["n_retained_subexposed"] == 0


def test_probe_rates_excluye_subexpuestos_del_score(tmp_path):
    make_probes(tmp_path, "a1", n_retained=2, correct=True)
    pr = probe_rates(tmp_path, "baseline_empirico", 0.07, 1,
                     subexposed_eids={"a1"})
    assert pr["n_retained"] == 0          # fuera del score
    assert pr["retained_rate"] is None
    assert pr["n_retained_subexposed"] == 2
    assert pr["retained_subexposed_correct"] == 2


def test_probe_rates_solo_excluye_al_subexpuesto(tmp_path):
    make_probes(tmp_path, "a1", n_retained=1, correct=True)
    make_probes(tmp_path, "a2", n_retained=1, correct=False)
    pr = probe_rates(tmp_path, "baseline_empirico", 0.07, 1,
                     subexposed_eids={"a1"})
    # solo a2 (bien expuesto) cuenta en el score; a1 va aparte
    assert pr["n_retained"] == 1
    assert pr["retained_rate"] == 0.0     # a2 falló (correct=False)
    assert pr["n_retained_subexposed"] == 1
    assert pr["retained_subexposed_correct"] == 1  # a1 acertó pero aparte


def test_min_exposure_es_tres():
    """El corte de Opus: <3 consumos en alguna celda vivida => sub-expuesto."""
    assert MIN_EXPOSURE == 3
