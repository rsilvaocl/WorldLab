"""WorldLab — banco de selección del modelo del oráculo.

Por qué existe: el oráculo es el TECHO informado. Si no puede recuperar la
regla que se le entregó, la condición "oráculo" no es una condición y el
probe de composición (D-010) no tiene denominador. Antes de gastar una ronda
hay que saber qué modelos ligan los tres índices — símbolo, región y fase —
y a qué velocidad.

Qué mide: la pregunta REAL del probe de composición (`predict_effect`), con
la tabla completa en el system prompt, sobre las 16 celdas del mundo
(4 símbolos × 2 regiones × 2 fases). No es un test de supervivencia ni de
aprendizaje: con la tabla delante, acertar es copiar la fila correcta.

Por qué las 16 celdas y no las observaciones del trace: en el trace los
5 agentes están en región A, así que un banco basado en observaciones no
testea el binding de REGIÓN. Las 16 celdas cubren las dos dimensiones y la
celda retenida (B-oscura), que es donde se juega la métrica primaria.

Desagregado por dimensión, porque el promedio esconde el hallazgo: qwen2.5:7b
liga símbolo y región y colapsa la FASE — el promedio decía 6/12, el corte
decía 6/6 y 0/6.

Uso:
    python -m ai.bench_oraculo --models qwen2.5:7b,gemma2:9b,llama3.1:8b
    python -m ai.bench_oraculo --models mistral-nemo:12b --repeats 2
"""

from __future__ import annotations

import argparse
import json
import os
import time
from typing import Any, Dict, List, Optional

from .model_adapter import LLMClient, ModelError
from .probe import _magnitude_level
from .probe_observability import TRUTH, _num

SYMBOLS = ("S1", "S2", "S3", "S4")
REGIONS = ("A", "B")
PHASES = (0, 1)
PHASE_NAME = {0: "clara", 1: "oscura"}


def cells() -> List[tuple]:
    return [(s, r, p) for s in SYMBOLS for r in REGIONS for p in PHASES]


def ask_cell(client: LLMClient, system: str, rkind: str, region: str,
             phase: int) -> tuple:
    """Misma pregunta que LLMAgent.predict_effect (D-010), palabra por palabra."""
    sys_p = (
        "Eres un agente autónomo en un mundo 2D. "
        'Responde SOLO con JSON: {"energy_change": <número con signo>, "reason": "..."}'
    )
    user = (
        f"PREGUNTA HIPOTÉTICA (no es una acción, solo responde):\n"
        f"Si consumieras 1 unidad del recurso '{rkind}' estando en la región "
        f"{region} durante la fase {PHASE_NAME[phase]}, "
        f"¿cuánto cambiaría tu energía? Da el número con signo (+ sube, - baja, 0 nada)."
    )
    try:
        raw = client.chat_json([
            {"role": "system", "content": system + "\n" + sys_p},
            {"role": "user", "content": user},
        ])
    except (ModelError, Exception) as e:  # noqa: BLE001 — el banco no debe abortar
        return None, {"_error": f"{type(e).__name__}: {e}"[:160]}
    return _num(raw.get("energy_change")), raw


def bench_model(model: str, backend: str, system: str, repeats: int,
                timeout: float) -> Dict[str, Any]:
    client = LLMClient(backend=backend, model=model, temperature=0.0,
                       max_tokens=700, timeout=timeout)

    # calentamiento FUERA del cronómetro: la primera llamada carga el modelo a
    # memoria y en un 12B eso son decenas de segundos que no se pagan en
    # producción (el modelo queda residente durante la corrida).
    t_load = time.time()
    ask_cell(client, system, "S1", "A", 0)
    load_s = time.time() - t_load

    rows: List[Dict[str, Any]] = []
    t0 = time.time()
    for _ in range(repeats):
        for rkind, region, phase in cells():
            truth = TRUTH[(rkind, region, phase)]
            said, raw = ask_cell(client, system, rkind, region, phase)
            rows.append({
                "rkind": rkind, "region": region, "phase": phase,
                "truth": truth, "said": said,
                "exact": said == truth,
                "level_correct": (None if said is None
                                  else _magnitude_level(said) == _magnitude_level(truth)),
                "raw": raw,
            })
    elapsed = time.time() - t0
    n = len(rows)

    def acc(sub: List[Dict[str, Any]], key: str = "exact") -> Optional[float]:
        vals = [r[key] for r in sub if r[key] is not None]
        return round(sum(1 for v in vals if v) / len(vals), 3) if vals else None

    held = [r for r in rows if r["region"] == "B" and r["phase"] == 1]
    return {
        "model": model,
        "n": n,
        "exact_acc": acc(rows),
        "level_acc": acc(rows, "level_correct"),
        "por_region": {r: acc([x for x in rows if x["region"] == r]) for r in REGIONS},
        "por_fase": {str(p): acc([x for x in rows if x["phase"] == p]) for p in PHASES},
        "celda_retenida_B_oscura": acc(held),
        "sin_respuesta": sum(1 for r in rows if r["said"] is None),
        "s_por_llamada": round(elapsed / n, 2),
        "carga_inicial_s": round(load_s, 1),
        "rows": rows,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Banco de selección del oráculo")
    ap.add_argument("--models", required=True, help="lista separada por comas")
    ap.add_argument("--backend", default="ollama", choices=["ollama", "openai"])
    ap.add_argument("--repeats", type=int, default=1, help="pasadas sobre las 16 celdas")
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--out", default="data/silver/bench_oraculo/bench.json")
    args = ap.parse_args()

    from .llm_agent import LLMAgent
    from .run_pilot import ORACLE_RULES

    stub = LLMAgent("bench", LLMClient(backend="ollama", model="x"),
                    goal="sobrevivir y maximizar energía", system_rules=ORACLE_RULES)
    system = stub._system_prompt()

    results = []
    print(f"{'modelo':26} {'exacto':>7} {'nivel':>6} {'regA':>5} {'regB':>5} "
          f"{'f0':>5} {'f1':>5} {'B-osc':>6} {'s/llam':>7} {'carga':>6}")
    for model in [m.strip() for m in args.models.split(",") if m.strip()]:
        try:
            r = bench_model(model, args.backend, system, args.repeats, args.timeout)
        except Exception as e:  # noqa: BLE001
            print(f"{model:26} ERROR: {type(e).__name__}: {str(e)[:60]}")
            continue
        results.append(r)
        print(f"{r['model']:26} {str(r['exact_acc']):>7} {str(r['level_acc']):>6} "
              f"{str(r['por_region']['A']):>5} {str(r['por_region']['B']):>5} "
              f"{str(r['por_fase']['0']):>5} {str(r['por_fase']['1']):>5} "
              f"{str(r['celda_retenida_B_oscura']):>6} {r['s_por_llamada']:>7} "
              f"{r['carga_inicial_s']:>6}")

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nescrito: {args.out}")
    print("Criterio: un oráculo utilizable necesita las DOS dimensiones "
          "(regA≈regB y f0≈f1) y la celda retenida; el promedio solo no basta.")


if __name__ == "__main__":
    main()
