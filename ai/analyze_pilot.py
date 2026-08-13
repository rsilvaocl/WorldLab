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


def probe_rates(out_dir: Path, condition: str, density: float, seed: int,
                subexposed_eids: Optional[set] = None) -> Dict[str, Any]:
    """Tasa de acierto (level_correct) separando celdas vividas de la retenida.

    D-025 (corte de exposición): los probes retenidos de agentes SUB-EXPONENTES
    (<3 consumos en alguna celda vivida) se reportan APARTE, fuera del score
    de composición — un agente sin experiencia en una celda vivida no tiene de
    dónde componer, y su fallo diría 'faltaban datos', no 'no compuso'.
    """
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
    subexposed_eids = subexposed_eids or set()

    # D-025: los probes de salida (exit_starvation) de agentes sub-expuestos
    # NO entran al score de composición. Los del momento "final" de un agente
    # bien expuesto SÍ.
    lived = [r for r in probes if not r["never_lived"]]
    retained_all = [r for r in probes if r["never_lived"]]
    retained = [r for r in retained_all
                if r["eid"] not in subexposed_eids]
    retained_sub = [r for r in retained_all
                    if r["eid"] in subexposed_eids]
    lived_correct = sum(1 for r in lived if r["level_correct"]) if lived else 0
    retained_correct = sum(1 for r in retained if r["level_correct"]) if retained else 0
    return {
        "n_lived": len(lived),
        "lived_rate": lived_correct / len(lived) if lived else None,
        "n_retained": len(retained),
        "retained_rate": retained_correct / len(retained) if retained else None,
        "n_retained_subexposed": len(retained_sub),
        "retained_subexposed_correct": sum(1 for r in retained_sub if r["level_correct"]),
    }


# Corte de Opus: < 3 consumos en alguna celda vivida => sub-expuesto
MIN_EXPOSURE = 3


def exposure_per_cell(events_path: Path, eid: str) -> Dict[Any, int]:
    """Consumos OK del agente en cada celda vivida (A-clara, A-oscura, B-clara).
    Sale del JSONL post-hoc — los eventos consume ya registran region y phase."""
    counts: Dict[Any, int] = {("A", 0): 0, ("A", 1): 0, ("B", 0): 0}
    if not events_path.exists():
        return counts
    with open(events_path) as f:
        for line in f:
            if not line.strip():
                continue
            obj = json.loads(line)
            if obj.get("type") != "event" or obj.get("eid") != eid:
                continue
            if obj.get("action") != "consume" or obj.get("outcome") != "ok":
                continue
            key = (obj["detail"].get("region"), obj["detail"].get("phase"))
            if key in counts:
                counts[key] += 1
    return counts


def exposure_summary(results: List[Dict[str, Any]], out_dir: Path) -> Dict[str, Any]:
    """¿Cuántos agentes estuvieron SUB-EXPONENTES (<3 consumos) en alguna celda
    vivida? Su probe retenido no dice nada sobre modelado: dice que les faltaban
    datos (Opus: la diferencia entre 'no compuso' y 'no tenía qué componer')."""
    subexposed = []
    total_agents = 0
    for r in results:
        # el Simulator nombra los eventos: {exp_id}_seed{seed}.jsonl
        events_path = out_dir / (f"piloto_{r['condition']}_{int(r['density']*100)}_s{r['seed']}"
                                 f"_seed{r['seed']}.jsonl")
        # exponer: los probes de este mundo ya corrieron; reconstruimos por eid
        prefix = f"piloto_{r['condition']}_{int(r['density']*100)}_s{r['seed']}"
        probes_path = out_dir / f"{prefix}_probes.jsonl"
        if not probes_path.exists():
            continue
        eids = set()
        with open(probes_path) as f:
            for line in f:
                if line.strip():
                    eids.add(json.loads(line)["eid"])
        for eid in sorted(eids):
            total_agents += 1
            cells = exposure_per_cell(events_path, eid)
            low = {f"{reg}-{phase}": n for (reg, phase), n in cells.items() if n < MIN_EXPOSURE}
            if low:
                subexposed.append({
                    "condition": r["condition"], "density": r["density"],
                    "seed": r["seed"], "eid": eid,
                    "exposure": {f"{reg}-{phase}": n for (reg, phase), n in cells.items()},
                    "low_cells": low,
                })
    frac = len(subexposed) / total_agents if total_agents else 0.0
    # D-025: claves (condition, density, seed, eid) de sub-expuestos, para
    # excluir SUS probes retenidos del score de composición
    subexposed_keys = {(s["condition"], s["density"], s["seed"], s["eid"])
                       for s in subexposed}
    return {"total_agents": total_agents, "subexposed": subexposed,
            "frac_subexposed": round(frac, 3),
            "subexposed_keys": subexposed_keys}


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
    # D-025: la exposición se calcula PRIMERO — los probes retenidos de
    # agentes sub-expuestos quedan FUERA del score de composición.
    print("\n2b) EXPOSICIÓN POR CELDA (consumos OK por agente en A-clara/A-oscura/B-clara)")
    expo = exposure_summary(results, out_dir)
    if expo["total_agents"] == 0:
        print("  (sin probes todavía)")
    else:
        print(f"  agentes: {expo['total_agents']} | sub-expuestos (<{MIN_EXPOSURE} "
              f"consumos en alguna celda vivida): {len(expo['subexposed'])} "
              f"({expo['frac_subexposed']*100:.0f}%)")
        for se in expo["subexposed"][:15]:
            low_txt = ", ".join(f"{k}={v}" for k, v in se["low_cells"].items())
            print(f"    {se['condition']:12s} d={se['density']:.0%} s={se['seed']} "
                  f"{se['eid']} — celdas bajas: {low_txt}")
        if len(expo["subexposed"]) > 15:
            print(f"    ... y {len(expo['subexposed'])-15} más (detalle en piloto_analysis.json)")
        if expo["frac_subexposed"] > 0.5:
            print("  ⚠️ MAYORÍA SUB-EXPONENTE: el hallazgo del piloto no es sobre "
                  "modelado — es que 30 días no alcanzan para recorrer el mundo.")

    print("\n2) SUB-CHECK: tasa de acierto en CELDAS VIVIDAS (si falla, mundo difícil)")
    print("3) COMPOSICIÓN: tasa de acierto en el probe RETENIDO vs azar ~17% "
          "(solo agentes bien expuestos; los sub-expuestos van aparte, D-025)")
    subkeys = expo.get("subexposed_keys", set())
    for (cond, dens), rs in sorted(groups.items()):
        lived_rates, retained_rates = [], []
        n_retained_total, n_retained_ok = 0, 0
        n_sub, n_sub_ok = 0, 0
        for r in rs:
            sub_eids = {eid for (c, d, s, eid) in subkeys
                        if c == cond and d == dens and s == r["seed"]}
            pr = probe_rates(out_dir, cond, dens, r["seed"], subexposed_eids=sub_eids)
            if not pr:
                continue
            if pr.get("lived_rate") is not None:
                lived_rates.append(pr["lived_rate"])
            if pr.get("retained_rate") is not None:
                retained_rates.append(pr["retained_rate"])
                n_retained_total += pr["n_retained"]
                n_retained_ok += round(pr["retained_rate"] * pr["n_retained"])
            n_sub += pr.get("n_retained_subexposed", 0)
            n_sub_ok += pr.get("retained_subexposed_correct", 0)
        lr = statistics.mean(lived_rates) if lived_rates else float("nan")
        rr = n_retained_ok / n_retained_total if n_retained_total else float("nan")
        sub_txt = f" | sub-expuestos aparte: {n_sub_ok}/{n_sub}" if n_sub else ""
        print(f"  {cond:11s} d={dens:.0%} | vividas: {lr*100:5.1f}% | retenida: {rr*100:5.1f}% "
              f"({n_retained_ok}/{n_retained_total}){sub_txt}")

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
    if dirty:
        print(f"  mundos con contaminación: {len(dirty)}/{len(results)} — SEEDS:")
        for r in dirty:
            print(f"    condición={r['condition']} densidad={r['density']:.0%} "
                  f"seed={r['seed']}  ← REPORTAR (dato sobre la expulsión, no se descarta)")
    else:
        print(f"  mundos con contaminación: 0/{len(results)} ✅ limpio")

    # guardar análisis
    report = {
        "n_mundos": len(results),
        "sigma_energia": {f"{k[0]}_{k[1]}": round(statistics.stdev([r['avg_energy'] for r in rs]), 2)
                          for k, rs in groups.items() if len(rs) > 1},
        "mundos_contaminados": len(dirty),
        "exposicion": {
            "total_agentes": expo["total_agents"],
            "subexpuestos": expo["subexposed"],
            "fraccion_subexpuestos": expo["frac_subexposed"],
        },
    }
    (out_dir / "piloto_analysis.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print("\nAnálisis guardado: data/silver/piloto/piloto_analysis.json")


if __name__ == "__main__":
    main()
