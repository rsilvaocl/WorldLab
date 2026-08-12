"""WorldLab — extensión del piloto a 100 días (decisión de Opus, 12/08).

σ a 30 días NO predice σ a 100 días: las trayectorias divergen (los mundos se
separan conforme los agentes acumulan aciertos y errores). Para no calibrar el
N de la confirmatoria con varianza equivocada: 2-3 seeds × condición a 100 días
(mismas siembras que el piloto) y comparar cómo escala σ.

Corre en directorio APARTE (data/silver/piloto100d/) para no sobrescribir los
archivos del piloto de 30 días (mismos seeds + condiciones = mismos nombres).
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.run_pilot import run_world, make_world_config
from ai.model_adapter import LLMClient

OUT100 = Path("data/silver/piloto100d")
CONDS = ["sin_memoria", "memoria", "oraculo"]
SEEDS = [1, 2, 3]
DAYS = 100


def run_extension(model_name: str = "qwen2.5:7b") -> List[Dict[str, Any]]:
    OUT100.mkdir(parents=True, exist_ok=True)
    client = LLMClient(backend="ollama", model=model_name)
    results = []
    for cond in CONDS:
        for seed in SEEDS:
            # densidad justa (7%) — la presión media es donde más se ve σ
            r = run_world(cond, 0.07, seed, DAYS, model_name, client, OUT100)
            r["elapsed_s"] = round(time.time(), 0)
            results.append(r)
            print(f"[100d | {cond} | s{seed}] superv={r['survivors']} "
                  f"tokens={r['tokens']} heldout={r['heldout_clean']}", flush=True)
    (OUT100 / "piloto100d_summary.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2))
    return results


def compare_sigma() -> Dict[str, Any]:
    """Compara σ entre 30 días (piloto) y 100 días (extensión), por condición."""
    p30 = Path("data/silver/piloto/piloto_summary.json")
    p100 = OUT100 / "piloto100d_summary.json"
    rows30 = json.loads(p30.read_text()) if p30.exists() else []
    rows100 = json.loads(p100.read_text()) if p100.exists() else []
    # filtrar densidad justa (0.07) para comparar los mismos mundos
    e30 = {r["condition"]: [x["avg_energy"] for x in rows30
                            if x["condition"] == r["condition"] and x["density"] == 0.07]
           for r in rows30}
    e100 = {r["condition"]: [x["avg_energy"] for x in rows100
                             if x["condition"] == r["condition"]]
            for r in rows100}

    table = []
    for cond in CONDS:
        v30, v100 = e30.get(cond, []), e100.get(cond, [])
        s30 = statistics.stdev(v30) if len(v30) > 1 else 0.0
        s100 = statistics.stdev(v100) if len(v100) > 1 else 0.0
        ratio = s100 / s30 if s30 > 0 else None
        table.append({
            "condicion": cond, "n30": len(v30), "n100": len(v100),
            "media30": round(statistics.mean(v30), 1) if v30 else None,
            "media100": round(statistics.mean(v100), 1) if v100 else None,
            "sigma30": round(s30, 2), "sigma100": round(s100, 2),
            "ratio_sigma_100_30": round(ratio, 2) if ratio else None,
        })

    print(f"\n{'condición':14s} {'n30':>4s} {'n100':>4s} {'media30':>8s} {'media100':>8s} "
          f"{'σ30':>6s} {'σ100':>6s} {'σ100/σ30':>8s}")
    for t in table:
        print(f"{t['condicion']:14s} {t['n30']:4d} {t['n100']:4d} "
              f"{str(t['media30']):>8s} {str(t['media100']):>8s} "
              f"{t['sigma30']:6.2f} {t['sigma100']:6.2f} "
              f"{str(t['ratio_sigma_100_30']):>8s}")

    out = {"tabla": table,
           "nota": "si σ100/σ30 >> 1, la varianza crece con la duración: el N "
                   "calculado con σ de 30 días quedaría mal calibrado para una "
                   "confirmatoria de 100 días (usar la opción 1 de Opus: "
                   "confirmatoria a 30 días, o N recalibrado)"}
    (OUT100 / "comparativa_sigma.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print("\nComparativa guardada: data/silver/piloto100d/comparativa_sigma.json")
    return out


if __name__ == "__main__":
    model = sys.argv[1] if len(sys.argv) > 1 else "qwen2.5:7b"
    t0 = time.time()
    run_extension(model)
    compare_sigma()
    print(f"\nTotal: {(time.time()-t0)/60:.1f} min")
