"""Repetibilidad de probes bajo `temperature=0` — artefacto auditable (D-039).

POR QUÉ EXISTE. La medición de repetibilidad se hizo ad hoc y su resultado
quedó solo como tabla en la bitácora: sin claves seleccionadas, respuestas
originales y nuevas, timestamps ni comparación fila a fila. Terra lo marcó como
el único hueco de auditoría que quedaba. Este runner lo cierra.

QUÉ MIDE Y QUÉ NO. Re-ejecuta probes YA persistidos en la réplica y compara
contra el crudo. Eso mide **repetibilidad empírica en este entorno**, no
determinismo como propiedad del modelo.

Sobre el n: **no se amplía**. Cuatro discordancias bastan para refutar
determinismo en este entorno; diez casos NO bastan para estimar una "tasa de
inestabilidad", y el resultado no debe presentarse de esa forma.

Selección DETERMINISTA y congelada antes de ejecutar: `random.Random(SEED)`
sobre las claves del crudo ordenadas, `N_POR_MODELO` por modelo. Cualquiera
puede reproducir exactamente qué probes se eligieron.

Uso:
    python -m ai.run_repetibilidad
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import random
import sys
from typing import Any, Dict, List, Tuple

sys.path.insert(0, ".")

from ai.world_state import WorldState
from ai.model_adapter import LLMClient, ModelError
from ai.llm_agent import LLMAgent
from ai.memory import IndexedMemory
from ai.fase_exposicion import exponer_agente
from ai.banco_ontologias import cargar, efectos
from ai.run_pilot import make_world_config, spawn_positions, world_geometry
from ai.run_replica_v3 import BANCO, MODELOS, CLAVE, RETENIDA

CRUDO_REPLICA = "data/resultados/replica_v3/probes_crudos.jsonl"
SALIDA = "data/resultados/repetibilidad/comparaciones.jsonl"
SEED = 7                 # congelada
N_POR_MODELO = 10        # congelado — NO se amplía (ver docstring)


def seleccionar(crudo: str, seed: int = SEED,
                n: int = N_POR_MODELO) -> Dict[str, List[tuple]]:
    """Selección determinista y reproducible de qué probes re-ejecutar."""
    filas = [json.loads(l) for l in open(crudo, encoding="utf-8")]
    por_modelo: Dict[str, List[tuple]] = {}
    for m in sorted({f["modelo"] for f in filas}):
        claves = sorted(tuple(f[c] for c in CLAVE) for f in filas if f["modelo"] == m)
        por_modelo[m] = random.Random(seed).sample(claves, min(n, len(claves)))
    return por_modelo


def _reejecutar(cli: LLMClient, banco, clave) -> Tuple[Any, Any, str]:
    _m, k, cond, i, rk = clave
    cfg = make_world_config(30)
    cfg.consume_effects = efectos(banco[k])
    w = WorldState(cfg, spawn_positions([f"a{j}" for j in range(5)], cfg, 7), seed=7)
    mem = IndexedMemory(max_items=200, label="memory") if cond == "memoria_indexada" else None
    ag = LLMAgent("a0", cli, goal="s", geometry=world_geometry(cfg), memory=mem)
    exponer_agente(w, "a0", ag, seed=900 + k * 10 + i)
    err = ""
    try:
        pred = ag.predict_effect(rk, *RETENIDA)
    except (ModelError, Exception) as e:      # noqa: BLE001
        pred, err = None, f"{type(e).__name__}: {e}"[:200]
    return pred, getattr(cli, "last_raw_content", None), err


def correr(out: str = SALIDA, crudo: str = CRUDO_REPLICA) -> str:
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    banco = cargar(BANCO)
    orig = {tuple(f[c] for c in CLAVE): f
            for f in (json.loads(l) for l in open(crudo, encoding="utf-8"))}
    seleccion = seleccionar(crudo)

    with open(out, "a", encoding="utf-8") as f:          # append-only
        for model, backend, th in MODELOS:
            if model not in seleccion:
                continue
            cli = LLMClient(backend=backend, model=model, temperature=0.0,
                            thinking=th, timeout=180)
            for clave in seleccion[model]:
                o = orig[clave]
                pred, raw, err = _reejecutar(cli, banco, clave)
                f.write(json.dumps({
                    "ts_comparacion": _dt.datetime.now(_dt.timezone.utc)
                                        .isoformat(timespec="seconds"),
                    "clave": {c: v for c, v in zip(CLAVE, clave)},
                    "ts_original": o["ts"],
                    "predicho_original": o["predicho"],
                    "predicho_nuevo": pred,
                    "raw_original": o["raw_content"],
                    "raw_nuevo": raw,
                    "error_nuevo": err or None,
                    "identico_predicho": pred == o["predicho"],
                    "identico_raw": raw == o["raw_content"],
                    "identico": (pred == o["predicho"] and raw == o["raw_content"]),
                }, ensure_ascii=False) + "\n")
                f.flush()
            print(f"  [{model}] {len(seleccion[model])} comparaciones", flush=True)
    return out


def resumir(path: str = SALIDA) -> Dict[str, Any]:
    filas = [json.loads(l) for l in open(path, encoding="utf-8")]
    out: Dict[str, Any] = {}
    for m in sorted({f["clave"]["modelo"] for f in filas}):
        sub = [f for f in filas if f["clave"]["modelo"] == m]
        ident = sum(1 for f in sub if f["identico"])
        out[m] = {"n": len(sub), "identicos": ident,
                  "discordantes": len(sub) - ident,
                  # Frase de Terra: se describe lo observado, no se afirma
                  # determinismo ni se estima una tasa con n=10.
                  "lectura": (f"{ident}/{len(sub)} idénticos; "
                              + ("no se observaron discordancias"
                                 if ident == len(sub)
                                 else f"{len(sub)-ident} discordancias observadas"))}
    return out


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for blk in iter(lambda: fh.read(65536), b""):
            h.update(blk)
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser(description="Repetibilidad bajo temperature=0")
    ap.add_argument("--solo-resumir", action="store_true")
    ap.add_argument("--out", default=SALIDA)
    args = ap.parse_args()
    if not args.solo_resumir:
        sel = seleccionar(CRUDO_REPLICA)
        print(f"selección congelada (seed={SEED}, {N_POR_MODELO}/modelo): "
              f"{ {m: len(v) for m, v in sel.items()} }", flush=True)
        correr(args.out)
    print("\n" + json.dumps(resumir(args.out), ensure_ascii=False, indent=1))
    print(f"\nsha256: {sha256(args.out)}")


if __name__ == "__main__":
    main()
