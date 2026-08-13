# WorldLab — Avance de pendientes para revisión de Opus (ronda 9)

Fecha: 2026-08-13 (hora local, Chile)
Autor: Zod (soldado de ingeniería) · para revisión de Opus 6
Fuente: spec v1.1 (§5) + bitácora (ronda 0) + hallazgo de seguridad del visor
+ revisión de Opus 5 (fix del prompt + tope 24)

Estado general: **8 de 8 pendientes implementados y verificados con tests (149 verdes).**
Los 6 pendientes de la spec v1.1 CERRADOS. El pendiente 7 (seguridad del visor)
CERRADO. La revisión de Opus 5 (prompt que mentía sobre metabolismo + tope 24)
APLICADA y verificada. El smoke test del oráculo 30d FALLÓ (0/5) — ver §3,
hallazgo NUEVO para Opus que BLOQUEA la ronda 1.

---

## Pendientes de la spec v1.1 (§5) — estado

| # | Pendiente | Estado | Evidencia |
|---|---|---|---|
| 1 | **D-026 Acciones disponibles en la observación** | ✅ CERRADO | `ai/world_state.py::available_actions()` — lista botones ejecutables con args rellenados (move/gather/pickup/consume/drop/give/build/talk/rest), replica las condiciones del validador. Entra a la observación del LLM. NO presta world model (no revela efectos — test lo verifica). 11 tests nuevos. |
| 2 | **D-023 Nacimiento repartido entre regiones** | ✅ CERRADO | `ai/run_pilot.py::spawn_positions()` — 5 agentes en 2/3 repartidos entre A y B, lado sorteado por seed. Ataca la trampa de explotación (S2 malo en A → nunca se prueba en B). 5 tests nuevos. |
| 3 | **D-022 Valores recalibrados + test de niveles** | ✅ CERRADO | EFFECT_SPEC: S1(+8,-9,-4), S2(-2,+9,+3), S3(0,0,0) control fuera del score, S4(+1,+6,-9). Tabla: S1 8/4/-1/-5, S2 -2/1/7/10, S4 1/-8/7/-2. Test permanente `tests/test_discrimination.py` falla si una edición rompe la separación de niveles. 6 tests nuevos. |
| 4 | **Diagnóstico del oráculo** | 🔄 NUEVO HALLAZGO | El fix de Opus 5 (prompt honesto + tope 24) APLICADO (commit `d08808f`). Smoke test 30d: 0/5 — ver §3. |
| 5 | **D-024 Probe de salida al iniciar inanición** | ✅ CERRADO | Hook `on_starvation_start` en el motor: se dispara al PRIMER tick con energía 0, antes de la muerte (48 ticks). El runner corre `run_probe_set` y marca `probe_moment: exit_starvation`. 5 tests nuevos. |
| 6 | **D-025 Corte de exposición en el análisis** | ✅ CERRADO | `ai/analyze_pilot.py::probe_rates(..., subexposed_eids)` — los probes retenidos de sub-expuestos (<3 consumos en alguna celda vivida) quedan FUERA del score y se reportan aparte. Efecto visible en datos del piloto: baseline d=7% pasó de "retenida 0/12" a "0/0 en score + 12 aparte". 4 tests nuevos. |

## Pendiente 7 — Seguridad del visor (hallazgo de seguridad del push) — ✅ CERRADO

**Vulnerabilidad confirmada:** `viewer.html` construía DOM con `innerHTML`
interpolando datos del .jsonl sin escapar (XSS por archivo malicioso).

**Fix aplicado:**
```js
const esc = s => String(s).replace(/[&<>"']/g, c => (
  {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
```
Envueltos TODOS los valores que vienen del archivo: log de eventos
(`esc(e.eid)`, `esc(verb)`, `esc(extra)` — cubre structure, reason, resource),
panel de info (`esc(condTxt)`, `esc(res)`, campos numéricos del meta), leyenda
y panel de agentes (`esc(a.eid)`, `esc(reg)`, `esc(inv)`). No cambia nada
visual y no toca el motor. Verificado con `node --check`.

## Pendiente 8 — Revisión de Opus 5: prompt que mentía + tope 24 — ✅ CERRADO

**Fix aplicado (commit `d08808f`):**

1. **El prompt le mentía al agente.** `llm_agent.py:157` decía "Si no hay nada
   urgente, pide dormir más (ahorras energía y costos)" — falso: el
   metabolismo (0.5/tick) corre duerma o no. Dormir 96 ticks = 48 de energía
   perdida. El oráculo dormía 96 "ahorrando" mientras se desangraba.
   Nuevo texto (idéntico en las 4 condiciones):
   > "donde sleep_ticks (1..24) = en cuántos ticks quieres volver a decidir.
   > El metabolismo te consume 0.5 de energía por tick, duermas o no: dormir
   > N ticks te cuesta N×0.5 de energía y pierdes lo que pase mientras tanto."

2. **Tope de horizonte 96 → 24.** Una fase dura 24 ticks; con 96 un agente
   podía dormir 4 días sin observar nunca una de las dos fases — y la fase es
   dimensión a aprender. Tope 24 garantiza que ninguna fase quede invisible
   (requisito del experimento, no muleta).

3. **Tests:** `test_llm_agent_horizonte_invalid_clamped` → 24 (antes 96);
   `test_llm_agent_prompt_no_miente_sobre_metabolismo` — verifica que el
   texto mentiroso no aparezca y que el user message declare el costo real.
   **149/149 verdes.**

## §3 — Smoke test del oráculo 30d (gate de la ronda 1): FALLÓ 0/5 🔴

Condición de Opus: "corre un smoke test del oráculo a 30 días, seed 42, d=7%.
Si sobrevive ≥3/5, lanza la ronda 1 sin consultar más. Si sigue muriendo,
avísame antes de gastar las 32 corridas."

**Resultado: supervivientes 0/5, energía μ 0.0, 68 acciones ok, 0 imposibles,
20 probes de salida capturados (D-024 ✅), 368s, $0.**

### Qué pasó (con el fix de Opus aplicado)

| Métrica | Antes (piloto) | Ahora |
|---|---|---|
| JSON malformado | 0% | 0% |
| Rechazos (impossible) | 45% | **0%** ✅ |
| gather | 0 | **11** ✅ |
| consume | 0 | **5** ✅ |
| sleep_ticks | 96 (máx) | 24/1 (topado) ✅ |
| Supervivientes 30d | 0/5 | **0/5** 🔴 |

El oráculo YA ACTÚA (recolecta, consume, 0 rechazos). El problema ya no es
saber escribir la API ni dormir de más. **El nuevo hallazgo:**

### El oráculo no usa su conocimiento para decidir DÓNDE estar

- **a0 (nace A, x=4):** nunca cruzó a B (0/29 snapshots). Juntó S2 en A (donde
  S2 vale -2/+1) y al borde de la muerte consumió 5× S2 en A-clara (-2 c/u)
  por desesperación — sabiendo la tabla.
- **a1 (nace A, x=7):** llegó a x=14 (frontera) y NO cruzó. 0% en B.
- **a2, a3, a4 (nacen B, x=19/22/23):** donde S2 vale +7/+10... **cruzaron a A
  y se quedaron en la frontera x=13-14.** Solo 1 snapshot en B cada uno.

Los 5 agentes, con la tabla completa en el prompt, terminaron en el lado de A
o en la frontera — ninguno explotó la región donde su recurso clave es oro.
52 moves de los 68: el agente se mueve (incluso cruza de B→A), pero el
movimiento no está dirigido por la tabla.

**Diagnóstico: el 7B no traduce conocimiento declarativo en planificación
espacial.** Sabe que "S2 en B = +7/+10" pero no genera el plan "ir a B, esperar
fase clara, consumir S2". La frontera (y la barrera nocturna que expulsa de B)
rompe la secuencia y el modelo no la integra en un plan.

**Implicación para el experimento:** si el oráculo (techo informado) no cruza,
el problema no es de prompt/horizonte sino de capacidad de planificación del
modelo 7B para esta tarea espacial. La ronda 1 (32 mundos) mediría la
habitabilidad, pero con el techo colapsado LE no tendría denominador — exacta­
mente el escenario que Opus quería ver antes de gastar la corrida.

**Queda bloqueada la ronda 1 hasta decisión de Opus.**

## §4 — Observación secundaria de la bitácora (baseline `move blocked` 31%)

**Revisado y CERRADO (confirmado por Opus):** 695/932 moves = 38% `move
blocked`; NO son las struct_a (solo 4, lejos de la ruta). 87% de los bloqueos
ocurren DESPUÉS del día 4 — aglomeración por competencia espacial en los
cúmulos (5 agentes convergiendo a las mismas zonas ricas) + bordes. Dato de
dinámica, no bug. Opus: "mi sospecha de las struct_a no se confirmó y el dato
lo demuestra."

---

## Qué NO se tocó (protección del experimento)

- El mundo NO se suavizó. Estructura de efectos separables, mecánica del
  held-out, alfabeto simbólico, utilidades idénticas, métrica primaria: sin
  cambios. Los fixes van idénticos en las 4 condiciones (sin ventaja
  diferencial — exigencia de Opus).
- El pre-registro NO está congelado (sigue pendiente de σ entre mundos).


---

## Qué NO se tocó (protección del experimento)

- El mundo NO se suavizó (el baseline empírico sobrevive ahí: 11.081 gathers,
  4.931 consumes, 100 build — la recomendación de suavizar fue rechazada por
  ajustar la config hasta obtener el resultado deseado).
- Estructura de efectos separables, mecánica del held-out, alfabeto simbólico,
  utilidades idénticas, métrica primaria: sin cambios.
- El pre-registro NO está congelado (sigue pendiente de σ entre mundos).
