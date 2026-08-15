"""WorldLab — ronda de composición, familia `composicion-bank-v2` (D-033 + D-034 + D-035).

Protocolo (Terra, aprobado por el Comandante):
  1. Fase E — exposición DIRIGIDA (`fase_exposicion.exponer_agente`): el motor
     garantiza experiencias REALES de consumo en las 3 celdas vividas (A-clara,
     A-oscura, B-clara) para cada símbolo puntuado. NO usa LLM.
  2. Fase P — probe retenido (`LLMAgent.predict_effect` sobre B-oscura) para los
     3 símbolos evaluados (S1, S2, S4). Aquí vive la métrica de composición.

Tres condiciones:
  - `memoria_indexada`         — experiencias propias agrupadas por celda.
  - `memoria_indexada_corrupta`— mismo índice/volumen, outcomes permutados
                                 (separa "el contenido importó" de "importó tener
                                 algo estructurado delante"). NO entra en el
                                 contraste primario.
  - `sin_memoria`              — control negativo: mismas experiencias, sin retención.

Unidad inferencial = ONTOLOGÍA (32 del banco congelado), no el seed ni el agente.

PRECONDICIÓN (la corre Opus y entrega el número): el gate de lectura de
`memoria_indexada` sobre el banco debe pasar (≥0.75 agregado y ≥0.60 por celda).
Si no pasa, esta ronda NO se corre: se reporta como fallo de accesibilidad del
recuerdo, que es un resultado, no un fracaso.

Análisis (fijado ANTES de ver datos):
  - Outcome por ontología: proporción de probes B-oscura correctos por nivel de
    magnitud.
  - Contraste pareado `memoria_indexada − sin_memoria`.
  - Prueba principal: `permutacion_pareada()` sobre las 32 diferencias.
  - Intervalo: `bootstrap_ic()`, remuestreando ontologías.
  - Azar de referencia: `azar_constante()` del banco v2 (0.188), NO 1/6.

Qué NO hacer: no tocar el banco congelado, no cambiar temperature, no excluir
ontologías por rendir mal. Reportar SIEMPRE la cobertura de exposición.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.banco_ontologias import (
    CELDA_RETENIDA, EVALUADOS, azar_constante, bootstrap_ic, cargar, efectos,
    permutacion_pareada,
)
from ai.fase_exposicion import SIMBOLOS_PUNTUADOS, cobertura, exponer_agente
from ai.llm_agent import LLMAgent
from ai.memory import IndexedMemory
from ai.model_adapter import LLMClient
from ai.probe import _magnitude_level
from ai.run_pilot import make_world_config
from ai.world_state import Entity, WorldState

CONDICIONES: Tuple[str, ...] = (
    "memoria_indexada", "memoria_indexada_corrupta", "sin_memoria")
BANCO_PATH = Path(__file__).resolve().parent.parent / "data" / "banco" / "composicion_bank_v2.json"
GATE_DEFAULT = "data/silver/gate_lectura_bancoV2_indexada_prosa.json"
GOAL = "sobrevivir y maximizar energía"


# ---------------------------------------------------------------------------
# Precondición (guard duro)

def verificar_gate(path: str) -> Dict[str, Any]:
    """Precondición de D-034: exige un archivo de gate de lectura con pasa=true.

    Sin esto, cualquiera lanza 1728 llamadas saltándose el gate. Aborta con
    SystemExit y mensaje claro si el archivo no existe, no es JSON, o tiene
    pasa=false. La representación que la ronda va a correr es memoria_indexada,
    así que el gate debe corresponder a ella.
    """
    p = Path(path)
    if not p.exists():
        raise SystemExit(
            f"GATE FALTANTE: no existe '{path}'. La ronda de composición exige "
            f"un gate de lectura de memoria_indexada con pasa=true (D-034). "
            f"Córrelo primero y vuelve a intentar con --gate-file.")
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        raise SystemExit(f"GATE INVÁLIDO: '{path}' no se pudo leer como JSON: {e}")
    pasa = d.get("pasa")
    if pasa is not True:
        agg = d.get("exactitud_agregada")
        cells = d.get("por_celda", {})
        raise SystemExit(
            f"GATE NO PASÓ: '{path}' tiene pasa={pasa!r}. Ronda BLOQUEADA por "
            f"D-034: la representación de memoria no supera el gate de lectura "
            f"(exactitud agregada {agg}, por celda {cells}; umbrales >=0.75 "
            f"agregado y >=0.60 por celda). Se reporta como fallo de "
            f"accesibilidad del recuerdo — no se corre la ronda.")
    return d


# ---------------------------------------------------------------------------
# Runner

def construir_mundo(spec, seed: int) -> WorldState:
    """Mundo de una ontología del banco: geometría/barreras de make_world_config
    + `consume_effects` de la ontología. Un solo agente por mundo (la Fase P no
    depende de la posición: predict_effect pregunta un (símbolo, región, fase)
    y lee la memoria, no el tablero)."""
    cfg = make_world_config(days=30)
    cfg.consume_effects = efectos(spec)   # ontología del banco, única fuente
    ents = [Entity(eid="a0", kind="agent", x=2, y=15)]
    return WorldState(cfg, ents, seed=seed)


def construir_agente(eid: str, client: LLMClient, model_name: str,
                     memoria) -> LLMAgent:
    return LLMAgent(eid, client, goal=GOAL, think_every=8,
                    hunger_threshold=30.0, model_name=model_name,
                    memory=memoria, geometry="")


def correr_fase_p(agente: LLMAgent, mundo: WorldState) -> List[Dict[str, Any]]:
    """Probe retenido: predict_effect sobre B-oscura para S1, S2, S4."""
    filas: List[Dict[str, Any]] = []
    for s in EVALUADOS:
        pred = agente.predict_effect(s, *CELDA_RETENIDA)
        real = mundo.ground_truth_effect(s, *CELDA_RETENIDA)
        ok = (pred is not None
              and _magnitude_level(pred) == _magnitude_level(real))
        filas.append({
            "rkind": s, "region": CELDA_RETENIDA[0], "phase": CELDA_RETENIDA[1],
            "predicho": pred, "real": real,
            "correcto": bool(ok),
            "nivel_predicho": _magnitude_level(pred) if pred is not None else None,
            "nivel_real": _magnitude_level(real),
        })
    return filas


def correr_ontologia(spec, idx: int, client: LLMClient, model_name: str,
                     n_agents: int, seed_base: int, out_dir: Path,
                     prefix: str) -> Dict[str, Any]:
    """Fase E + Fase P para una ontología, en las 3 condiciones.

    Devuelve el resumen por condición: proporción de B-oscura correctos,
    cobertura de exposición, llamadas y filas (para el análisis fino).
    """
    out: Dict[str, Any] = {"ontologia": idx}
    probes_path = out_dir / f"{prefix}_probes.jsonl"

    for cond in CONDICIONES:
        correctos = 0
        total = 0
        none_count = 0
        filas_cond = []
        cobertura_total = {"consumos_totales": 0, "agentes": 0,
                           "agentes_con_cobertura_completa": 0}

        for i in range(n_agents):
            seed = seed_base * 1000 + idx * 100 + i
            mundo = construir_mundo(spec, seed=seed)
            eid = "a0"

            if cond == "memoria_indexada":
                mem = IndexedMemory(max_items=200, label="memory")
                ag = construir_agente(eid, client, model_name, mem)
                reg = exponer_agente(mundo, eid, ag, seed=seed)
                filas = correr_fase_p(ag, mundo)

            elif cond == "memoria_indexada_corrupta":
                # fuente: misma memoria indexada, poblada por la Fase E real
                mem = IndexedMemory(max_items=200, label="memory")
                ag_fuente = construir_agente(eid, client, model_name, mem)
                reg = exponer_agente(mundo, eid, ag_fuente, seed=seed)
                mem_corrupta = IndexedMemory.corrupta_desde(mem, seed=seed)
                ag = construir_agente(eid, client, model_name, mem_corrupta)
                filas = correr_fase_p(ag, mundo)

            else:  # sin_memoria
                ag = construir_agente(eid, client, model_name, None)
                reg = exponer_agente(mundo, eid, ag, seed=seed)
                filas = correr_fase_p(ag, mundo)

            cov = cobertura(reg)
            cobertura_total["consumos_totales"] += cov["consumos_totales"]
            cobertura_total["agentes"] += cov["agentes"]
            cobertura_total["agentes_con_cobertura_completa"] += (
                cov["agentes_con_cobertura_completa"])
            cobertura_total["cobertura_completa"] = cov["cobertura_completa"]

            for f in filas:
                f["condicion"] = cond
                f["ontologia"] = idx
                f["agente"] = i
                f["llamadas"] = ag.total_calls
                total += 1
                if f["correcto"]:
                    correctos += 1
                if f["predicho"] is None:
                    none_count += 1
                filas_cond.append(f)
                with open(probes_path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(f, ensure_ascii=False, sort_keys=True) + "\n")

        prop = round(correctos / total, 4) if total else 0.0
        out[cond] = {
            "proporcion_boscura_correctos": prop,
            "correctos": correctos,
            "total": total,
            "sin_respuesta": none_count,
            "cobertura": cobertura_total,
        }

    return out


# ---------------------------------------------------------------------------
# Análisis

def analizar(resultados: List[Dict[str, Any]], banco) -> Dict[str, Any]:
    """Contraste pareado memoria_indexada − sin_memoria + corrupta aparte."""
    difs = []
    for r in resultados:
        idx = r.get("memoria_indexada", {}).get("proporcion_boscura_correctos", 0.0)
        sin = r.get("sin_memoria", {}).get("proporcion_boscura_correctos", 0.0)
        difs.append(round(idx - sin, 4))

    return {
        "n_ontologias": len(resultados),
        "azar_constante": azar_constante(banco),
        "diferencia_media_memoria_minus_sin": round(sum(difs) / len(difs), 4)
        if difs else None,
        "permutacion_pareada": permutacion_pareada(difs),
        "bootstrap_ic": bootstrap_ic(difs),
        "proporcion_media_por_condicion": {
            c: round(sum(r.get(c, {}).get("proporcion_boscura_correctos", 0.0)
                         for r in resultados) / len(resultados), 4)
            for c in CONDICIONES
        },
        "corrupta_vs_indexada": round(
            sum(r.get("memoria_indexada_corrupta", {}).get("proporcion_boscura_correctos", 0.0)
                for r in resultados) / len(resultados) -
            sum(r.get("memoria_indexada", {}).get("proporcion_boscura_correctos", 0.0)
                for r in resultados) / len(resultados), 4),
    }


# ---------------------------------------------------------------------------
# CLI

def main() -> None:
    ap = argparse.ArgumentParser(description="Ronda de composición (composicion-bank-v2)")
    ap.add_argument("--model", default="gemma2:9b")
    ap.add_argument("--backend", default="ollama", choices=["ollama", "openai"])
    ap.add_argument("--agents", type=int, default=6,
                    help="agentes (réplicas) por condición y ontología")
    ap.add_argument("--ontologias", default="", help="índices 0-based, p.ej. '0,1,2'")
    ap.add_argument("--out-dir", default="data/silver/composicion_bank_v2")
    ap.add_argument("--prefix", default="composicion")
    ap.add_argument("--seed-base", type=int, default=20260814)
    ap.add_argument("--smoke", action="store_true",
                    help="solo la primera ontología (verificación del instrumento)")
    ap.add_argument("--gate-file", default=GATE_DEFAULT,
                    help="archivo JSON del gate de lectura (pasa=true) que "
                         "habilita la ronda. Requerido por D-034.")
    ap.add_argument("--resume", action="store_true",
                    help="salta ontologías ya registradas en el summary")
    args = ap.parse_args()

    # PRECONDICIÓN (D-034): sin gate con pasa=true no se corre la ronda.
    # Guard duro: aborta antes de tocar el banco o gastar una sola llamada.
    verificar_gate(args.gate_file)

    banco = cargar(str(BANCO_PATH))
    if args.ontologias:
        idxs = [int(x) for x in args.ontologias.split(",") if x.strip()]
    else:
        idxs = list(range(len(banco)))
    if args.smoke:
        idxs = idxs[:1]

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    # temperatura FIJA en 0: subirla fabrica varianza de decoding (Terra la
    # descartó). No se expone como flag para que nadie la suba.
    client = LLMClient(backend=args.backend, model=args.model, temperature=0.0)

    summary_path = out_dir / f"{args.prefix}_summary.json"
    resultados: List[Dict[str, Any]] = []
    done: set = set()
    if args.resume and summary_path.exists():
        try:
            prev = json.loads(summary_path.read_text())
            resultados = prev.get("resultados_por_ontologia", [])
            done = {r["ontologia"] for r in resultados}
            print(f"RESUME: {len(done)} ontologías ya completadas", flush=True)
        except json.JSONDecodeError:
            pass

    t0 = time.time()
    for idx in idxs:
        if idx in done:
            continue
        r = correr_ontologia(banco[idx], idx, client, args.model,
                             args.agents, args.seed_base, out_dir, args.prefix)
        resultados.append(r)
        resultados.sort(key=lambda x: x["ontologia"])
        # checkpoint por ontología
        summary_path.write_text(json.dumps({
            "familia": "composicion-bank-v1",
            "modelo": f"{args.backend}:{args.model}",
            "temperature": 0.0,
            "n_agentes": args.agents,
            "condiciones": list(CONDICIONES),
            "resultados_por_ontologia": resultados,
            "analisis": analizar(resultados, banco),
        }, ensure_ascii=False, indent=2))
        mi = r.get("memoria_indexada", {}).get("proporcion_boscura_correctos", 0.0)
        si = r.get("sin_memoria", {}).get("proporcion_boscura_correctos", 0.0)
        print(f"[onto {idx:2d}] memoria_indexada={mi:.3f} "
              f"sin_memoria={si:.3f} "
              f"corrupta={r.get('memoria_indexada_corrupta', {}).get('proporcion_boscura_correctos', 0.0):.3f} "
              f"en {time.time()-t0:.0f}s", flush=True)

    print(f"\nResumen: {summary_path}")
    print(json.dumps(analizar(resultados, banco), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
