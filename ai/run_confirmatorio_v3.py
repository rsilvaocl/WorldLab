"""Script EXACTO que produjo el confirmatorio v3 — versionado a posteriori.

HONESTIDAD SOBRE QUÉ ES ESTO. La corrida del 15/08 NO usó
`ai/run_composicion.py` (el runner de Zod): se ejecutó como heredoc en línea,
sin quedar versionada. Terra lo detectó al auditar el protocolo y tiene razón
en llamarlo brecha de reproducibilidad: los blobs publicados no permitían
reconstruir la ejecución.

Este archivo es la **transcripción literal** de ese heredoc, guardada DESPUÉS de
la corrida para cerrar la brecha. No es el artefacto congelado antes de los
datos — decir lo contrario sería falsificar la cadena de custodia. Lo que aporta
es que la ejecución quede reconstruible; lo que NO aporta es anterioridad.

Por qué `run_composicion.py` no sirve como registro de esta corrida (auditoría
de Terra): apunta al banco **v2**, corre **tres** condiciones, usa permutación
**bilateral** por defecto y **no pasa `thinking=False`** (y el adaptador omite
el campo cuando recibe `None`). Es decir, ejecutarlo NO reproduce el v3.

Diferencias declaradas de esta corrida respecto de la de Zod sobre v2:
  - 2 condiciones (`memoria_indexada`, `sin_memoria`), no 3: `corrupta` es
    control mecanístico secundario y no entra en el contraste primario.
  - 2 agentes por ontología, no 6: la unidad es la ontología; con exposición
    determinista y temperature=0 los agentes son réplicas técnicas.
  - permutación UNILATERAL (dirección declarada en D-036).

LIMITACIÓN DE LOS DATOS QUE ESTE SCRIPT PERSISTE: guarda proporciones por
ontología y métricas derivadas, NO respuestas por probe, errores, reintentos ni
timestamps. Las `filas` por probe se usan para calcular las tres componentes y
se descartan. Por eso `data/resultados/confirmatorio_bankv3.json` es un
**resultado agregado**, no crudo, y los secundarios no son recomputables desde
disco. Corregir esto exige re-correr con persistencia por probe.

Comando exacto de la ejecución original:
    set -a && . ./.env && set +a
    .venv/bin/python - <<'PY'   # ← el contenido de este archivo
"""

from __future__ import annotations

import json
import sys

sys.path.insert(0, ".")

from ai.world_state import WorldState
from ai.model_adapter import LLMClient
from ai.llm_agent import LLMAgent
from ai.memory import IndexedMemory
from ai.fase_exposicion import exponer_agente
from ai.probe import _magnitude_level
from ai.banco_ontologias import (cargar, efectos, permutacion_unilateral,
                                 bootstrap_ic, CELDAS_VIVIDAS)
from ai.gate_lectura import tres_componentes
from ai.run_pilot import make_world_config, spawn_positions, world_geometry

BANCO = "data/banco/composicion_bank_v3.json"
MODELOS = [("deepseek-v4-flash", "openai", False),
           ("gemma2:9b", "ollama", None),
           ("llama3.1:8b", "ollama", None)]
SIM = ("S1", "S2", "S4")
NAG = 2
SALIDA = "data/resultados/confirmatorio_bankv3.json"


def main() -> None:
    banco = cargar(BANCO)
    salida = {}
    for model, backend, th in MODELOS:
        cli = LLMClient(backend=backend, model=model, temperature=0.0,
                        thinking=th, timeout=180)
        tasas = {"memoria_indexada": [], "sin_memoria": []}
        filas = []
        for k, spec in enumerate(banco):
            cfg = make_world_config(30)
            cfg.consume_effects = efectos(spec)
            for cond in ("memoria_indexada", "sin_memoria"):
                ok = []
                for i in range(NAG):
                    ents = spawn_positions([f"a{j}" for j in range(5)], cfg, 7)
                    w = WorldState(cfg, ents, seed=7)
                    mem = (IndexedMemory(max_items=200, label="memory")
                           if cond == "memoria_indexada" else None)
                    ag = LLMAgent("a0", cli, goal="s",
                                  geometry=world_geometry(cfg), memory=mem)
                    exponer_agente(w, "a0", ag, seed=900 + k * 10 + i)
                    for rk in SIM:
                        pr = ag.predict_effect(rk, "B", 1)
                        real = cfg.consume_effects[(rk, "B", 1)]
                        corr = (pr is not None
                                and _magnitude_level(pr) == _magnitude_level(real))
                        ok.append(corr)
                        if cond == "memoria_indexada":
                            filas.append({
                                "predicho": pr, "correcto": corr,
                                "viv": {f"{r}-{p}": cfg.consume_effects[(rk, r, p)]
                                        for r, p in CELDAS_VIVIDAS}})
                tasas[cond].append(sum(ok) / len(ok))
            if (k + 1) % 16 == 0:
                print(f"  [{model}] {k + 1}/64", flush=True)
        difs = [a - b for a, b in zip(tasas["memoria_indexada"],
                                      tasas["sin_memoria"])]
        comp = tres_componentes(filas, lambda f, c: f["viv"][c])
        salida[model] = {"tasas": tasas, "difs": difs,
                         "permutacion": permutacion_unilateral(difs),
                         "ic": bootstrap_ic(difs), "componentes": comp}
        print(f"\n== {model}: indexada={sum(tasas['memoria_indexada'])/64:.3f} "
              f"sin_memoria={sum(tasas['sin_memoria'])/64:.3f} "
              f"delta={sum(difs)/64:+.4f} "
              f"p={salida[model]['permutacion']['p_valor']} "
              f"IC={salida[model]['ic']['ic_bajo']},{salida[model]['ic']['ic_alto']}",
              flush=True)
        print(f"   componentes: {json.dumps(comp, ensure_ascii=False)}", flush=True)
    json.dump(salida, open(SALIDA, "w"), ensure_ascii=False, indent=1)
    print(f"\nescrito {SALIDA}")


if __name__ == "__main__":
    main()
