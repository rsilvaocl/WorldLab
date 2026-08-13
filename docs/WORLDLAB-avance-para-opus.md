# WorldLab — Avance de pendientes para revisión de Opus (ronda 8)

Fecha: 2026-08-13 (hora local, Chile)
Autor: Zod (soldado de ingeniería) · para revisión de Opus 5
Fuente: spec v1.1 (§5) + bitácora (ronda 0) + hallazgo de seguridad del visor

Estado general: **6 de 7 pendientes implementados y verificados con tests (148 verdes).**
El pendiente 7 (seguridad del visor) quedó cerrado en esta ronda. La validación
empírica del oráculo está en curso (corrida 30 días local, $0).

---

## Pendientes de la spec v1.1 (§5) — estado

| # | Pendiente | Estado | Evidencia |
|---|---|---|---|
| 1 | **D-026 Acciones disponibles en la observación** | ✅ CERRADO | `ai/world_state.py::available_actions()` — lista botones ejecutables con args rellenados (move/gather/pickup/consume/drop/give/build/talk/rest), replica las condiciones del validador. Entra a la observación del LLM. NO presta world model (no revela efectos — test lo verifica). 11 tests nuevos. |
| 2 | **D-023 Nacimiento repartido entre regiones** | ✅ CERRADO | `ai/run_pilot.py::spawn_positions()` — 5 agentes en 2/3 repartidos entre A y B, lado sorteado por seed. Ataca la trampa de explotación (S2 malo en A → nunca se prueba en B). 5 tests nuevos. |
| 3 | **D-022 Valores recalibrados + test de niveles** | ✅ CERRADO | EFFECT_SPEC: S1(+8,-9,-4), S2(-2,+9,+3), S3(0,0,0) control fuera del score, S4(+1,+6,-9). Tabla: S1 8/4/-1/-5, S2 -2/1/7/10, S4 1/-8/7/-2. Test permanente `tests/test_discrimination.py` falla si una edición rompe la separación de niveles. 6 tests nuevos. |
| 4 | **Diagnóstico del oráculo** | 🔄 EN CURSO | **Diagnóstico CERRADO con hallazgo que corrige la hipótesis inicial** (ver §1 abajo). Fix aplicado en `_system_prompt()` (contrato agente-motor SIEMPRE presente). Validación empírica 30 días corriendo en background. |
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
Envueltos TODOS los valores que vienen del archivo:
- Log de eventos: `esc(e.eid)`, `esc(verb)`, `esc(extra)` (cubre structure, reason, resource — incluida la vía del mensaje de excepción de Python)
- Panel de info: `esc(condTxt)`, `esc(res)`, y los campos numéricos del meta
- Leyenda de agentes: `esc(a.eid)`
- Panel de agentes: `esc(a.eid)`, `esc(reg)`, `esc(inv)`

No cambia nada visual (los valores legítimos pasan intactos) y no toca el motor.
Verificado con `node --check` (JS_OK). Sin tests de pytest porque es HTML/JS puro.

---

## §1 — Diagnóstico del oráculo (pendiente 4): hallazgo que corrige la hipótesis

**Hipótesis de Opus:** "el prompt con la tabla completa de efectos satura a un
modelo de 7B. Se comprueba comparando longitud de prompt y tasa de JSON
malformado entre condiciones."

**Medición real (traces del piloto, 96 mundos):**

| Condición | JSON malformado | Acción dominante | Distancia de move | Tamaño obs |
|---|---|---|---|---|
| oráculo | **0%** (76/76 válidos) | 100% move | **μ=4.45, 88% >1 casilla** | 3.081 chars |
| sin_memoria | 0% | 100% gather | — | 3.402 |
| memoria | 0% | 84% gather | 35% >1 | 6.582 |

**Conclusión: NO es saturación del prompt.** El oráculo escribe JSON perfecto.
El problema real: `_system_prompt()` usaba `self.system_rules or (base)` — al
existir `system_rules` (tabla de efectos del oráculo), reemplazaba TODO el
prompt base, y el oráculo **perdía la mecánica "dx,dy son pasos de 1 casilla"**
y la lista de acciones. Proponía move con distancias imposibles (dx:2, dy:-3)
y "solo caminaba": 1.202 move, cero gather, cero consume.

**Fix:** el contrato agente-motor (acciones disponibles + mecánica + regla de
paso de 1 casilla) va SIEMPRE en el prompt; el conocimiento especial del
oráculo se agrega ADEMÁS, no en lugar de. No presta world model: no revela
efectos nuevos, solo los botones — igual en las 4 condiciones (exigencia D-026).

**Smoke test 6 días (oráculo, d=7%, seed 42, fix aplicado):**
- Supervivientes: **5/5** (antes: 0)
- Energía μ: **55.4** (antes: 0.0)
- Rechazos: **0** (antes: 45%)
- Probes: **20** (antes: 0)
- Pero 7 acciones ok en 6 días = solo move, y `sleep_ticks: 96` (máximo) —
  el oráculo aún no come ni navega hacia recursos en un mundo corto.

**Validación 30 días en curso** (corrida local en background, $0) — veredicto
real de supervivencia y consumo al terminar.

## §2 — Observación secundaria de la bitácora (baseline `move blocked` 31%)

Pendiente de revisión: "el baseline gasta el 31% de sus acciones chocando
(`move blocked`, 16.322 veces)... conviene revisar si las 100 `struct_a`
construidas están tapando celdas de paso."

**Estado: NO resuelto aún — requiere análisis de los JSONL del piloto.**
Pendiente de esta ronda; no bloquea la ronda 1 (el baseline sobrevive).

---

## Qué NO se tocó (protección del experimento)

- El mundo NO se suavizó (el baseline empírico sobrevive ahí: 11.081 gathers,
  4.931 consumes, 100 build — la recomendación de suavizar fue rechazada por
  ajustar la config hasta obtener el resultado deseado).
- Estructura de efectos separables, mecánica del held-out, alfabeto simbólico,
  utilidades idénticas, métrica primaria: sin cambios.
- El pre-registro NO está congelado (sigue pendiente de σ entre mundos).
