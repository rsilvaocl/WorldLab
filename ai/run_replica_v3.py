"""Réplica técnica del confirmatorio v3, con persistencia completa (D-038).

QUÉ ES Y QUÉ NO ES (encuadre de Terra, 15/08). Es una **réplica técnica**, no
una reparación retroactiva del confirmatorio original. Una corrida nueva puede
**validar** aquellos resultados; **no** convierte en crudos unos datos que nunca
se conservaron. Importa especialmente para `deepseek-v4-flash`, cuya versión
puede haber cambiado entre ambas corridas y no es verificable por digest.

Estado honesto de la corrida original (15/08, `confirmatorio_bankv3.json`):
  - Primario: recomputable desde las diferencias por ontología.
  - Secundarios: NO auditables independientemente (las filas por probe se
    descartaron tras calcular las componentes).
  - Nulos de `sin_memoria`: desconocidos, nunca se registraron.
  - Esta corrida: evidencia ADICIONAL, no sustitución silenciosa.

Qué corrige respecto de aquel script:
  1. Persiste **cada probe de ambos brazos** en JSONL append-only: respuesta
     cruda del modelo, si parseó, error, número de intentos, modelo y timestamp.
  2. Escribe en un **directorio nuevo**; no toca `confirmatorio_bankv3.json`.
  3. Los agregados se calculan **desde el JSONL**, no en paralelo — así la
     reconciliación crudo↔agregado es exacta por construcción y `--reconciliar`
     lo verifica.

Uso:
    python -m ai.run_replica_v3 --smoke              # 2 ontologías, 1 modelo
    python -m ai.run_replica_v3                      # los tres modelos
    python -m ai.run_replica_v3 --reconciliar        # verifica crudo vs agregado
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, ".")

from ai.world_state import WorldState
from ai.model_adapter import LLMClient, ModelError
from ai.llm_agent import LLMAgent
from ai.memory import IndexedMemory
from ai.fase_exposicion import exponer_agente
from ai.probe import _magnitude_level
from ai.banco_ontologias import (cargar, efectos, permutacion_unilateral,
                                 bootstrap_ic, CELDAS_VIVIDAS)
from ai.gate_lectura import tres_componentes
from ai.run_pilot import make_world_config, spawn_positions, world_geometry

BANCO = "data/banco/composicion_bank_v3.json"
SALIDA_DIR = "data/resultados/replica_v3"
MODELOS = [("deepseek-v4-flash", "openai", False),
           ("gemma2:9b", "ollama", None),
           ("llama3.1:8b", "ollama", None)]
SIMBOLOS = ("S1", "S2", "S4")
CONDICIONES = ("memoria_indexada", "sin_memoria")
N_AGENTES = 2
RETENIDA = ("B", 1)

# Esquema de cada línea del JSONL. Congelado antes de ejecutar: si la corrida
# escribe otra cosa, `verificar_esquema` lo detecta.
CAMPOS = ("ts", "modelo", "ontologia", "condicion", "agente", "rkind",
          "region", "phase", "viv", "predicho", "real", "nivel_predicho",
          "nivel_real", "correcto", "raw_content", "parse_ok", "error",
          "intentos")


def _ahora() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def probar(ag: LLMAgent, cli: LLMClient, rkind: str, real: float
           ) -> Dict[str, Any]:
    """Un probe, con TODO lo que la corrida original descartaba."""
    error: Optional[str] = None
    try:
        pred = ag.predict_effect(rkind, *RETENIDA)
    except (ModelError, Exception) as e:      # noqa: BLE001 — nada aborta la corrida
        pred, error = None, f"{type(e).__name__}: {e}"[:300]
    if error is None and getattr(cli, "last_error", None):
        error = cli.last_error
    nivel_pred = None if pred is None else _magnitude_level(pred)
    return {
        "predicho": pred,
        "real": real,
        "nivel_predicho": nivel_pred,
        "nivel_real": _magnitude_level(real),
        "correcto": bool(pred is not None and nivel_pred == _magnitude_level(real)),
        "raw_content": getattr(cli, "last_raw_content", None),
        "parse_ok": pred is not None,
        "error": error,
        "intentos": getattr(cli, "last_attempts", 0),
    }


def correr(modelos, banco, out_dir: str, n_ont: Optional[int] = None) -> str:
    """Ejecuta y persiste APPEND-ONLY. Devuelve la ruta del JSONL."""
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "probes_crudos.jsonl")
    ontologias = banco if n_ont is None else banco[:n_ont]

    with open(path, "a", encoding="utf-8") as f:      # append-only
        for model, backend, th in modelos:
            cli = LLMClient(backend=backend, model=model, temperature=0.0,
                            thinking=th, timeout=180)
            for k, spec in enumerate(ontologias):
                cfg = make_world_config(30)
                cfg.consume_effects = efectos(spec)
                for cond in CONDICIONES:
                    for i in range(N_AGENTES):
                        ents = spawn_positions([f"a{j}" for j in range(5)], cfg, 7)
                        w = WorldState(cfg, ents, seed=7)
                        mem = (IndexedMemory(max_items=200, label="memory")
                               if cond == "memoria_indexada" else None)
                        ag = LLMAgent("a0", cli, goal="s",
                                      geometry=world_geometry(cfg), memory=mem)
                        exponer_agente(w, "a0", ag, seed=900 + k * 10 + i)
                        for rk in SIMBOLOS:
                            fila = {
                                "ts": _ahora(), "modelo": model, "ontologia": k,
                                "condicion": cond, "agente": i, "rkind": rk,
                                "region": RETENIDA[0], "phase": RETENIDA[1],
                                # valores de las celdas VIVIDAS: sin esto no se
                                # puede recomputar "recuperación de valor vivido"
                                "viv": {f"{r}-{ph}": cfg.consume_effects[(rk, r, ph)]
                                        for r, ph in CELDAS_VIVIDAS},
                            }
                            fila.update(probar(ag, cli, rk,
                                               cfg.consume_effects[(rk, *RETENIDA)]))
                            f.write(json.dumps(fila, ensure_ascii=False) + "\n")
                            f.flush()          # cada probe en disco al instante
                if (k + 1) % 16 == 0:
                    print(f"  [{model}] {k + 1}/{len(ontologias)}", flush=True)
    return path


# ---------------------------------------------------------------------------
# Agregados: se calculan DESDE el crudo, nunca en paralelo

def agregar_desde_crudo(path: str) -> Dict[str, Any]:
    filas = [json.loads(l) for l in open(path, encoding="utf-8")]
    salida: Dict[str, Any] = {}
    for model in sorted({f["modelo"] for f in filas}):
        sub = [f for f in filas if f["modelo"] == model]
        onts = sorted({f["ontologia"] for f in sub})
        tasas = {c: [] for c in CONDICIONES}
        for c in CONDICIONES:
            for o in onts:
                celda = [f for f in sub if f["condicion"] == c and f["ontologia"] == o]
                tasas[c].append(sum(1 for f in celda if f["correcto"]) / len(celda)
                                if celda else 0.0)
        difs = [a - b for a, b in zip(tasas["memoria_indexada"], tasas["sin_memoria"])]
        comp = {}
        for c in CONDICIONES:      # las TRES componentes, en AMBOS brazos
            fc = [f for f in sub if f["condicion"] == c]
            comp[c] = tres_componentes(
                [{"predicho": f["predicho"], "correcto": f["correcto"],
                  "viv": f.get("viv", {})} for f in fc],
                lambda f, cl: f["viv"].get(cl, float("nan")))
            comp[c]["nulos"] = sum(1 for f in fc if not f["parse_ok"])
            comp[c]["reintentos_totales"] = sum(f["intentos"] - 1 for f in fc)
        salida[model] = {
            "n_ontologias": len(onts), "tasas": tasas, "difs": difs,
            "permutacion": permutacion_unilateral(difs) if len(difs) > 1 else None,
            "ic": bootstrap_ic(difs) if len(difs) > 1 else None,
            "componentes_por_condicion": comp,
        }
    return salida


def verificar_esquema(path: str) -> Dict[str, Any]:
    filas = [json.loads(l) for l in open(path, encoding="utf-8")]
    faltan = {c for f in filas for c in CAMPOS if c not in f}
    brazos = sorted({f["condicion"] for f in filas})
    return {"n_filas": len(filas), "campos_faltantes": sorted(faltan),
            "brazos_presentes": brazos,
            "ambos_brazos": set(brazos) == set(CONDICIONES),
            "ok": not faltan and set(brazos) == set(CONDICIONES)}


def reconciliar(path: str, agregado_path: str) -> Dict[str, Any]:
    """El agregado en disco DEBE recomputarse exacto desde el crudo."""
    recomputado = agregar_desde_crudo(path)
    guardado = json.load(open(agregado_path, encoding="utf-8"))
    difs = []
    for m in recomputado:
        a = recomputado[m]["difs"]
        b = guardado.get(m, {}).get("difs", [])
        if a != b:
            difs.append(m)
    return {"modelos": sorted(recomputado), "discrepan": difs,
            "reconcilia": not difs}


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(65536), b""):
            h.update(blk)
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser(description="Réplica técnica del confirmatorio v3")
    ap.add_argument("--smoke", action="store_true", help="2 ontologías, 1 modelo")
    ap.add_argument("--reconciliar", action="store_true",
                    help="solo verifica crudo vs agregado, sin llamar a modelos")
    ap.add_argument("--modelos", default=None,
                    help="lista separada por comas; por defecto los tres del "
                         "panel. Util cuando falta la API key de alguno.")
    ap.add_argument("--out", default=SALIDA_DIR)
    args = ap.parse_args()

    crudo = os.path.join(args.out, "probes_crudos.jsonl")
    agregado = os.path.join(args.out, "agregado.json")

    if args.reconciliar:
        print(json.dumps(verificar_esquema(crudo), ensure_ascii=False, indent=1))
        print(json.dumps(reconciliar(crudo, agregado), ensure_ascii=False, indent=1))
        return

    banco = cargar(BANCO)
    if args.modelos:
        pedidos = [m.strip() for m in args.modelos.split(",")]
        modelos = [m for m in MODELOS if m[0] in pedidos]
        faltan = set(pedidos) - {m[0] for m in modelos}
        if faltan:
            raise SystemExit(f"modelos fuera del panel preespecificado: {faltan}. "
                             f"El panel es {[m[0] for m in MODELOS]} y no se "
                             f"amplia despues de ver datos (D-037).")
    else:
        modelos = MODELOS
    if args.smoke and not args.modelos:
        modelos = modelos[:1]
    n_ont = 2 if args.smoke else None
    out = args.out + ("_smoke" if args.smoke else "")
    crudo = os.path.join(out, "probes_crudos.jsonl")
    agregado = os.path.join(out, "agregado.json")

    print(f"réplica técnica · banco v3 · {len(modelos)} modelo(s) · "
          f"{n_ont or len(banco)} ontologías · salida {out}", flush=True)
    correr(modelos, banco, out, n_ont)

    esq = verificar_esquema(crudo)
    print("\nesquema:", json.dumps(esq, ensure_ascii=False))
    json.dump(agregar_desde_crudo(crudo), open(agregado, "w"),
              ensure_ascii=False, indent=1)
    rec = reconciliar(crudo, agregado)
    print("reconciliación:", json.dumps(rec, ensure_ascii=False))
    print(f"\nsha256 crudo    : {sha256(crudo)}")
    print(f"sha256 agregado : {sha256(agregado)}")


if __name__ == "__main__":
    main()
