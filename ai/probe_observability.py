"""WorldLab — probe de OBSERVABILIDAD (diagnóstico de instrumento, no experimento).

Pregunta que responde: de lo que el agente necesita saber para usar la tabla
del oráculo, ¿qué está realmente presente en su observación?

El oráculo recibe la tabla indexada por (símbolo, REGIÓN, fase). Para
convertir eso en política necesita tres cosas distintas:

  Q1 región actual  — ¿lee el campo `region` de su observación?
  Q2 valor aquí     — ¿recupera la fila correcta de la tabla dado el contexto?
  Q3 rumbo a B      — ¿sabe hacia dónde queda la región donde la comida vale?

Q1 y Q2 son controles: si fallan, el problema es de lectura/recuperación.
Q3 es el diagnóstico: si falla mientras Q1 y Q2 aciertan, el agente sabe la
regla, sabe dónde está, y NO tiene cómo llegar — eso es un hueco del
instrumento (información ausente de la observación), no un límite cognitivo.

Diseño (para que el resultado signifique algo):
- Se REPLAYAN observaciones REALES tomadas del trace de una corrida; no se
  reconstruye un estado sintético. Lo que ve el probe es exactamente lo que
  vio el agente en ese instante.
- Mismo system prompt que la condición evaluada (mecánica + reglas del
  oráculo). No se agrega ni se quita contexto.
- Una llamada independiente por pregunta: preguntas sin estado, para que
  responder Q1 no le regale a Q3 el haber dicho "estoy en A" hace un instante
  (el oráculo corre con memory=None; el probe respeta esa condición).
- Forced-choice y ground truth calculado aparte, como en CompositionProbe.

Uso:
    python -m ai.probe_observability \\
        --traces data/silver/gate_oraculo_ds/gateds_oraculo_7_s42_seed42_traces.jsonl \\
        --backend openai --model deepseek-chat --n 12

    python -m ai.probe_observability --traces ... --backend ollama --model qwen2.5:7b
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
from typing import Any, Dict, List, Optional, Tuple

from .model_adapter import LLMClient, ModelError


# Tabla del oráculo (misma fuente que ORACLE_RULES en run_pilot).
TRUTH: Dict[Tuple[str, str, int], float] = {
    ("S1", "A", 0): +8, ("S1", "A", 1): +4, ("S1", "B", 0): -1, ("S1", "B", 1): -5,
    ("S2", "A", 0): -2, ("S2", "A", 1): +1, ("S2", "B", 0): +7, ("S2", "B", 1): +10,
    ("S3", "A", 0): 0,  ("S3", "A", 1): 0,  ("S3", "B", 0): 0,  ("S3", "B", 1): 0,
    ("S4", "A", 0): +1, ("S4", "A", 1): -8, ("S4", "B", 0): +7, ("S4", "B", 1): -2,
}


# ----------------------------------------------------------------------
# Ground truth

def region_of(x: int, split_x: int) -> str:
    return "A" if x < split_x else "B"


def truth_step_to_B(x: int, split_x: int) -> Optional[int]:
    """dx correcto de un paso para acercarse a la región B.

    B es el semiplano x >= split_x. Si ya estás en B, no hay rumbo que
    corregir (devuelve None y la pregunta no se puntúa como navegación).
    """
    return +1 if x < split_x else None


# ----------------------------------------------------------------------
# Preguntas

def q_region(_obs: Dict[str, Any]) -> Tuple[str, str, str]:
    """Control de lectura: ¿en qué región estás?"""
    return (
        "region_actual",
        'Responde SOLO con JSON: {"region": "A" o "B", "reason": "..."}',
        "PREGUNTA (no es una acción): según tu observación de arriba, "
        "¿en qué región estás AHORA mismo?",
    )


def q_value(_obs: Dict[str, Any], rkind: str) -> Tuple[str, str, str]:
    """Control de recuperación: ¿qué te daría consumir rkind AQUÍ?"""
    return (
        "valor_aqui",
        'Responde SOLO con JSON: {"energy_change": <número con signo>, "reason": "..."}',
        f"PREGUNTA HIPOTÉTICA (no es una acción): si consumieras 1 unidad de "
        f"'{rkind}' aquí y ahora, en tu posición y fase actuales, ¿cuánto "
        f"cambiaría tu energía? Da el número con signo.",
    )


def q_heading(_obs: Dict[str, Any]) -> Tuple[str, str, str]:
    """Diagnóstico: ¿hacia dónde queda B?"""
    return (
        "rumbo_a_B",
        'Responde SOLO con JSON: {"dx": <-1,0,1>, "dy": <-1,0,1>, "reason": "..."}',
        "PREGUNTA (no es una acción): si quisieras llegar a la región B, "
        "¿qué paso de UNA casilla te acercaría? Da dx y dy. Si ya estás en la "
        "región B, responde dx=0, dy=0.",
    )


# ----------------------------------------------------------------------

def _ask(client: LLMClient, system_prompt: str, obs: Dict[str, Any],
         schema: str, question: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """Una llamada sin estado: mismo system prompt + observación real + pregunta."""
    user = (
        "Estado actual:\n" + json.dumps(obs, ensure_ascii=False) +
        "\n\n" + question + "\n" + schema
    )
    try:
        raw = client.chat_json([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user},
        ])
        return raw, ""
    except (ModelError, Exception) as e:  # noqa: BLE001 — el probe no debe abortar
        return None, f"{type(e).__name__}: {e}"


def _num(v: Any) -> Optional[float]:
    """Número de una respuesta, sin confundir el índice de un símbolo con un valor.

    El lookbehind es el punto: `re.search(r"[-+]?\\d+", "S2: -2")` devuelve
    **2** (el dígito de 'S2'), no −2. Un modelo que contesta "S2: -2" tenía
    razón y quedaba registrado como equivocado. Se exige que el número no
    venga pegado a una letra o a otro dígito.
    """
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        m = re.search(r"(?<![A-Za-z0-9])[-+]?\d+(?:\.\d+)?", v)
        if m:
            return float(m.group())
    return None


def load_observations(traces_path: str, n: int, seed: int,
                      skip_first_day: bool) -> List[Dict[str, Any]]:
    """Toma observaciones reales del trace, repartidas entre agentes y días."""
    rows: List[Dict[str, Any]] = []
    with open(traces_path, encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            if rec.get("type") != "trace" or "observation" not in rec:
                continue
            if skip_first_day and rec.get("day", 0) <= 1:
                continue
            rows.append(rec)
    if not rows:
        raise SystemExit(f"sin traces utilizables en {traces_path}")

    # reparto: agrupar por (eid) y tomar en round-robin para no sesgar a un agente
    by_eid: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        by_eid.setdefault(r.get("eid", "?"), []).append(r)
    rng = random.Random(seed)
    for lst in by_eid.values():
        rng.shuffle(lst)

    picked: List[Dict[str, Any]] = []
    eids = sorted(by_eid)
    i = 0
    while len(picked) < n and any(by_eid[e] for e in eids):
        e = eids[i % len(eids)]
        if by_eid[e]:
            picked.append(by_eid[e].pop())
        i += 1
    return picked


def run(traces_path: str, client: LLMClient, system_prompt: str, n: int,
        seed: int, split_x: int, rkind: str, out_path: str,
        skip_first_day: bool) -> Dict[str, Any]:
    samples = load_observations(traces_path, n, seed, skip_first_day)
    results: List[Dict[str, Any]] = []

    for rec in samples:
        obs = rec["observation"]
        pos = obs.get("position", [0, 0])
        x = int(pos[0])
        true_region = region_of(x, split_x)
        true_phase = int(obs.get("phase", 0))
        true_value = TRUTH.get((rkind, true_region, true_phase))
        true_dx = truth_step_to_B(x, split_x)

        row: Dict[str, Any] = {
            "eid": rec.get("eid"), "day": rec.get("day"), "tick": rec.get("tick"),
            "position": pos, "true_region": true_region, "phase": true_phase,
            "rkind": rkind, "distance_to_B": max(0, split_x - x),
        }

        # Q1 — región actual (control de lectura)
        _, schema, question = q_region(obs)
        raw, err = _ask(client, system_prompt, obs, schema, question)
        said = (raw or {}).get("region")
        row["q1_region_said"] = said
        row["q1_correct"] = (str(said).strip().upper() == true_region) if raw else None
        row["q1_error"] = err or None
        row["q1_raw"] = raw

        # Q2 — valor aquí (control de recuperación de la tabla)
        _, schema, question = q_value(obs, rkind)
        raw, err = _ask(client, system_prompt, obs, schema, question)
        row["q2_raw"] = raw
        said_v = _num((raw or {}).get("energy_change"))
        row["q2_value_said"] = said_v
        row["q2_value_truth"] = true_value
        row["q2_correct"] = (said_v == true_value) if said_v is not None else None
        row["q2_sign_correct"] = (
            None if said_v is None or true_value is None
            else (said_v > 0) == (true_value > 0) or (said_v == 0 and true_value == 0)
        )
        row["q2_error"] = err or None

        # Q3 — rumbo a B (el diagnóstico)
        _, schema, question = q_heading(obs)
        raw, err = _ask(client, system_prompt, obs, schema, question)
        row["q3_raw"] = raw
        said_dx = _num((raw or {}).get("dx"))
        said_dy = _num((raw or {}).get("dy"))
        row["q3_dx_said"] = said_dx
        row["q3_dy_said"] = said_dy
        row["q3_dx_truth"] = true_dx
        if true_dx is None:
            # ya estaba en B: no se puntúa como navegación
            row["q3_correct"] = None
            row["q3_scored"] = False
        else:
            row["q3_correct"] = (said_dx is not None and said_dx > 0)
            row["q3_scored"] = True
        row["q3_error"] = err or None
        row["q3_reason"] = (raw or {}).get("reason")

        results.append(row)
        print(f"  {row['eid']} d{row['day']} t{row['tick']} pos={pos} "
              f"[{true_region}/f{true_phase}] "
              f"Q1={row['q1_correct']} Q2={row['q2_correct']} Q3={row['q3_correct']}")

    def rate(key: str) -> Optional[float]:
        vals = [r[key] for r in results if r.get(key) is not None]
        return round(sum(1 for v in vals if v) / len(vals), 3) if vals else None

    summary = {
        "traces": traces_path,
        "model": client.describe(),
        "n_sampled": len(results),
        "split_x": split_x,
        "rkind": rkind,
        "q1_region_acc": rate("q1_correct"),
        "q2_value_acc": rate("q2_correct"),
        "q2_sign_acc": rate("q2_sign_correct"),
        "q3_heading_acc": rate("q3_correct"),
        "q3_scored_n": sum(1 for r in results if r.get("q3_scored")),
        "chance_q1": 0.5,
        "chance_q3": 0.25,
    }

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    with open(out_path.replace(".jsonl", "_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description="Probe de observabilidad (diagnóstico)")
    ap.add_argument("--traces", required=True, help="ruta al *_traces.jsonl de la corrida")
    ap.add_argument("--backend", default="openai", choices=["ollama", "openai"])
    ap.add_argument("--model", default=None)
    ap.add_argument("--n", type=int, default=12, help="observaciones muestreadas")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--rkind", default="S2", help="símbolo para la pregunta de valor")
    ap.add_argument("--width", type=int, default=30)
    ap.add_argument("--region-split", type=float, default=0.5)
    ap.add_argument("--condition", default="oraculo",
                    choices=["oraculo", "sin_memoria"],
                    help="qué system prompt replicar")
    ap.add_argument("--include-day1", action="store_true",
                    help="incluir el día 1 (por defecto se salta: los agentes "
                         "aún no fueron expulsados de B)")
    ap.add_argument("--out", default="data/silver/probe_observabilidad/probe.jsonl")
    args = ap.parse_args()

    from .llm_agent import LLMAgent
    from .run_pilot import ORACLE_RULES

    client = LLMClient(backend=args.backend, model=args.model,
                       temperature=0.0, max_tokens=400)
    rules = ORACLE_RULES if args.condition == "oraculo" else ""
    stub = LLMAgent("probe", client, goal="sobrevivir y maximizar energía",
                    system_rules=rules)
    system_prompt = stub._system_prompt()

    split_x = int(args.width * args.region_split)
    print(f"probe de observabilidad · {client.describe()} · condición={args.condition} "
          f"· frontera B en x>={split_x}")
    summary = run(args.traces, client, system_prompt, args.n, args.seed,
                  split_x, args.rkind, args.out, not args.include_day1)
    print("\n" + json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\nLectura: si q1 y q2 son altos y q3_heading_acc ≈ azar (0.25), el "
          f"agente sabe la regla y sabe dónde está, pero no tiene en la "
          f"observación de dónde deducir hacia dónde queda B.")


if __name__ == "__main__":
    main()
