"""WorldLab — análisis del piloto (lo que Opus necesita para congelar el pre-registro).

Procesa data/silver/piloto/piloto_summary.json + los *_probes.jsonl y produce:

1. σ del desempeño entre mundos, por condición y densidad (métrica: energía promedio
   de supervivientes — proxy de desempeño; también survivors)
2. tasa de acierto en probes de CELDAS VIVIDAS (sub-check de Opus: si fallan aquí,
   el mundo quedó demasiado difícil y nada más es interpretable)
3. tasa de acierto en el probe RETENIDO (B-oscura) vs azar ~17%
4. costo real en tokens (y $ si API; local = $0) por mundo
5. cuántos mundos activaron no_heldout_consumption() == False (contaminación)
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any, Dict, List


def load_results(out_dir: Path) -> List[Dict[str, Any]]:
    with open(out_dir / "piloto_summary.json") as f:
        return json.load(f)


def probe_rates(out_dir: Path, condition: str, density: float, seed: int) -> Dict[str, Any]:
    """Tasa de acierto (level_correct) separando celdas vividas de la retenida."""
    prefix = f"piloto_{condition}_{int(density*100)}_s{seed}"
    probes = []
    p = out_dir / f"{prefix}_probes.jsonl"
    if not p.exists():
        return {}
    with open(p) as f:
        for line in f:
            if line.strip():
                probes.append(json.loads(line))
    if not probes:
        return {}

    lived = [r for r in probes if not r["never_lived"]]
    retained = [r for r in probes if r["never_lived"]]
    lived_correct = sum(1 for r in lived if r["level_correct"]) if lived else 0
    retained_correct = sum(1 for r in retained if r["level_correct"]) if retained else 0
    return {
        "n_lived": len(lived),
        "lived_rate": lived_correct / len(lived) if lived else None,
        "n_retained": len(retained),
        "retained_rate": retained_correct / len(retained) if retained else None,
    }


def main() -> None:
    out_dir = Path("data/silver/piloto")
    results = load_results(out_dir)
    if not results:
        print("Sin resultados todavía — corre el piloto primero (ai/run_pilot.py).")
        return

    print("=" * 78)
    print("PILOTO WORLDLAB — resumen para congelar el pre-registro")
    print("=" * 78)

    # 1. σ del desempeño entre mundos, por condición × densidad
    print("\n1) DESEMPEÑO (supervivientes, energía promedio) y σ entre mundos")
    groups = {}
    for r in results:
        key = (r["condition"], r["density"])
        groups.setdefault(key, []).append(r)

    for (cond, dens), rs in sorted(groups.items()):
        energies = [r["avg_energy"] for r in rs]
        surv = [r["survivors"] for r in rs]
        sigma_e = statistics.stdev(energies) if len(energies) > 1 else 0.0
        mean_e = statistics.mean(energies)
        print(f"  {cond:11s} d={dens:.0%} | n={len(rs)} | energía μ={mean_e:6.1f} σ={sigma_e:5.1f} "
              f"| supervivientes μ={statistics.mean(surv):.1f}")

    # 2+3. probes: celdas vividas (sub-check) y retenida (composición)
    print("\n2) SUB-CHECK: tasa de acierto en CELDAS VIVIDAS (si falla, mundo difícil)")
    print("3) COMPOSICIÓN: tasa de acierto en el probe RETENIDO vs azar ~17%")
    for (cond, dens), rs in sorted(groups.items()):
        lived_rates, retained_rates = [], []
        n_retained_total, n_retained_ok = 0, 0
        for r in rs:
            pr = probe_rates(out_dir, cond, dens, r["seed"])
            if not pr:
                continue
            if pr.get("lived_rate") is not None:
                lived_rates.append(pr["lived_rate"])
            if pr.get("retained_rate") is not None:
                retained_rates.append(pr["retained_rate"])
                n_retained_total += pr["n_retained"]
                n_retained_ok += round(pr["retained_rate"] * pr["n_retained"])
        lr = statistics.mean(lived_rates) if lived_rates else float("nan")
        rr = n_retained_ok / n_retained_total if n_retained_total else float("nan")
        print(f"  {cond:11s} d={dens:.0%} | vividas: {lr*100:5.1f}% | retenida: {rr*100:5.1f}% "
              f"({n_retained_ok}/{n_retained_total})")

    # 4. costo real
    print("\n4) COSTO")
    for (cond, dens), rs in sorted(groups.items()):
        tokens = [r["tokens"] for r in rs]
        calls = [r["llm_calls"] for r in rs]
        secs = [r["elapsed_s"] for r in rs]
        print(f"  {cond:11s} d={dens:.0%} | tokens/mundo μ={statistics.mean(tokens):,.0f} "
              f"| llamadas μ={statistics.mean(calls):,.0f} | tiempo μ={statistics.mean(secs):.0f}s "
              f"(local: $0)")

    # 5. red de detección
    print("\n5) INTEGRIDAD DEL HELD-OUT (no_heldout_consumption)")
    dirty = [r for r in results if not r["heldout_clean"]]
    print(f"  mundos con contaminación: {len(dirty)}/{len(results)}",
          "⚠️ REVISAR" if dirty else "✅ limpio")

    # guardar análisis
    report = {
        "n_mundos": len(results),
        "sigma_energia": {f"{k[0]}_{k[1]}": round(statistics.stdev([r['avg_energy'] for r in rs]), 2)
                          for k, rs in groups.items() if len(rs) > 1},
        "mundos_contaminados": len(dirty),
    }
    (out_dir / "piloto_analysis.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print("\nAnálisis guardado: data/silver/piloto/piloto_analysis.json")


if __name__ == "__main__":
    main()
