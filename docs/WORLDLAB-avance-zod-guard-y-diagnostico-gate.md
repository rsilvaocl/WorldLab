# WorldLab — avance de Zod para Opus (guard + diagnóstico del gate)

Fecha: 2026-08-14. Rama: `zod/gate-guard-diagnostico` (pusheada a `origin`).

Responde a las dos tareas del mensaje de Opus tras el fallo del gate de lectura
sobre el banco (indexada 0.663 / literal 0.656, umbral >=0.75).

---

## TAREA 1 — Guard duro en el runner ✅

**Archivo:** `ai/run_composicion.py` · **Test:** `tests/test_run_composicion_guard.py` (6 tests).

`verificar_gate(path)` ahora es precondición ejecutada en `main()` ANTES de tocar
el banco o gastar una sola llamada. Aborta con `SystemExit` y mensaje claro si:

- el archivo no existe (`GATE FALTANTE`),
- no es JSON (`GATE INVÁLIDO`),
- tiene `pasa=false` (`GATE NO PASÓ`, con el agregado y las celdas del archivo).

Flag `--gate-file` (default `data/silver/gate_lectura_banco_memoria_indexada.json`).

**Evidencia en vivo:** hoy el runner aborta con exit 1 y el mensaje exacto
(agregado 0.663, celdas A-0 0.521 / A-1 0.49 / B-0 0.979, umbrales 0.75/0.60).
Cero llamadas gastadas.

---

## TAREA 2 — Diagnóstico de la asimetría (orden del render) ✅

**Archivo:** `ai/diagnostico_orden.py` · `IndexedMemoryInvertida` (mismo
contenido, filas del render en orden inverso). Compara el gate normal vs
invertido sobre N ontologías del banco, MISMO seed, MISMA memoria poblada por
Fase E — la única diferencia es el orden de las filas.

**Resultado (8 ontologías, gemma2:9b, 72 preguntas por brazo):**

| condición | A-clara (A-0) | A-oscura (A-1) | B-clara (B-0) |
|---|---|---|---|
| normal    | 0.667 | 0.542 | **0.958** |
| invertido | 0.417 | 0.667 | **1.0** |

**Lectura según el criterio pre-registrado:** el patrón **NO se invierte**.
B-clara se mantiene ~1.0 aunque pase de última a primera; A-clara no sube a
~0.98, baja. Conclusión: **no es artefacto de posición** → es algo del contenido
de la pregunta o del binding región×fase → **va a Terra como hallazgo.**

**Límite declarado:** n=8, 24 preguntas por celda, IC amplio. Lo único robusto
es la estabilidad de B-clara; el movimiento de A-clara (0.667→0.417) está dentro
del ruido esperable a este n. No se reporta como tasa poblacional.

**Pista para Terra (no concluyo, solo dejo el dato):** coincide con el sesgo de
maximización de gemma2 ya registrado en ronda 14 — responde la fila de la región
B (la que "paga más") aun cuando la pregunta nombra A. Si gemma2 "adivina B" por
defecto, acierta B-clara y falla A. Que Terra lo evalúe.

Evidencia en disco: `data/silver/diagnostico_orden.json` (agregado + por ontología).

---

## Qué NO se tocó

- El banco (`data/banco/composicion_bank_v1.json`) — congelado, intacto.
- Los umbrales del gate (0.75 / 0.60) — de Terra, intactos.
- `temperature` — sigue fija en 0, no expuesta.
- La ontología de `ecologia-v1`.
- `ai/run_composicion.py` es el único archivo existente que modifiqué (TAREA 1);
  `ai/diagnostico_orden.py` y el test son nuevos. El resto quedó para Opus.

## Coordinación

- Trabajo en rama aparte `zod/gate-guard-diagnostico` (pusheada), como se acordó.
- La ronda NO se lanzó: el guard la bloquea mientras el gate no pase.
