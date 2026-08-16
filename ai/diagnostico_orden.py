"""WorldLab — diagnóstico de la asimetría del gate de lectura (TAREA 2 de Opus).

El gate sobre el banco (32 ontologías, gemma2:9b) dio:
    A-clara 0.52 · A-oscura 0.49 · B-clara 0.98
El modelo lee UNA celda casi perfecto y las otras dos al azar, con la misma
información delante y en el mismo formato. Hipótesis a descartar PRIMERO:
efecto de posición — el `render()` de `IndexedMemory` ordena por
(símbolo, región, fase), así que B-clara queda como la ÚLTIMA fila de cada
bloque, y la recencia la favorece.

Test: `IndexedMemoryInvertida` invierte el orden de las filas del render
(B-clara pasa a primera). Mismo contenido, única diferencia el orden.
8 ontologías, comparando orden normal vs invertido, mismo seed.

Lectura (fijada ANTES de correr):
  - Si el patrón SE INVIERTE (A-clara sube a ~0.98 y B-clara cae): es artefacto
    de formato → tiene arreglo → el gate se re-corre con el render corregido.
  - Si NO se mueve: no es posición; es algo del contenido de la pregunta o del
    binding región×fase → va a Terra como hallazgo.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.banco_ontologias import cargar, efectos
from ai.fase_exposicion import exponer_agente
from ai.gate_lectura import agregar_gate, correr_gate_lectura
from ai.llm_agent import LLMAgent
from ai.memory import IndexedMemory
from ai.model_adapter import LLMClient
from ai.run_pilot import make_world_config
from ai.world_state import Entity, WorldState

BANCO_PATH = Path(__file__).resolve().parent.parent / "data" / "banco" / "composicion_bank_v1.json"
GOAL = "sobrevivir y maximizar energía"


class IndexedMemoryInvertida(IndexedMemory):
    """Mismo contenido que IndexedMemory, filas del render en orden inverso.

    La única diferencia es el orden: B-clara (última en el orden normal) pasa a
    primera. Si el patrón de acierto se invierte, la asimetría es de posición.
    """

    def render(self) -> List[Dict[str, Any]]:
        filas = super().render()
        filas.reverse()
        return filas


def construir_mundo(spec, seed: int) -> WorldState:
    cfg = make_world_config(days=30)
    cfg.consume_effects = efectos(spec)
    ents = [Entity(eid="a0", kind="agent", x=2, y=15)]
    return WorldState(cfg, ents, seed=seed)


def correr_par(client: LLMClient, spec, idx: int, seed: int) -> Dict[str, Any]:
    """Gate de lectura con orden normal vs invertido, MISMA memoria poblada."""
    # Poblar la memoria UNA sola vez vía Fase E (idéntica en ambos brazos).
    mundo = construir_mundo(spec, seed=seed)
    mem_normal = IndexedMemory(max_items=200, label="memory")
    ag_normal = LLMAgent("a0", client, goal=GOAL, memory=mem_normal)
    exponer_agente(mundo, "a0", ag_normal, seed=seed)

    # La invertida comparte EXACTAMENTE el mismo contenido: copiamos los items.
    mem_inv = IndexedMemoryInvertida(max_items=200, label="memory")
    mem_inv.items = [dict(it) for it in mem_normal.items]
    ag_inv = LLMAgent("a0", client, goal=GOAL, memory=mem_inv)

    verdad = efectos(spec)
    g_normal = correr_gate_lectura(ag_normal, verdad)
    g_inv = correr_gate_lectura(ag_inv, verdad)
    return {"ontologia": idx, "normal": g_normal, "invertido": g_inv}


def main() -> None:
    ap = argparse.ArgumentParser(description="Diagnóstico de orden del gate de lectura")
    ap.add_argument("--model", default="gemma2:9b")
    ap.add_argument("--backend", default="ollama", choices=["ollama", "openai"])
    ap.add_argument("--ontologias", type=int, default=8,
                    help="cuántas ontologías comparar (default 8)")
    ap.add_argument("--out", default="data/silver/diagnostico_orden.json")
    args = ap.parse_args()

    banco = cargar(str(BANCO_PATH))
    idxs = list(range(min(args.ontologias, len(banco))))
    client = LLMClient(backend=args.backend, model=args.model, temperature=0.0)

    filas = []
    t0 = time.time()
    for idx in idxs:
        filas.append(correr_par(client, banco[idx], idx, seed=20260814 + idx))
        print(f"[onto {idx}] normal B-0={filas[-1]['normal']['por_celda']['B-0']} "
              f"inv B-0={filas[-1]['invertido']['por_celda']['B-0']} "
              f"en {time.time()-t0:.0f}s", flush=True)

    agregado = {
        "n_ontologias": len(filas),
        "normal": agregar_gate([f["normal"] for f in filas]),
        "invertido": agregar_gate([f["invertido"] for f in filas]),
        "por_ontologia": filas,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(agregado, ensure_ascii=False, indent=2))
    print("\n=== AGREGADO ===")
    print(json.dumps({k: v for k, v in agregado.items() if k != "por_ontologia"},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
