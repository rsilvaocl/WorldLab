# Avance a Opus — barajado del menú y gate re-corrido (handoff gate-oráculo)

Fecha: 2026-08-13 · Rama: `redesign/visor-panel-instrumentos` · Commit de Zod: `45942f8`

## Estado en una línea

**Hipótesis del sesgo posicional CONFIRMADA, pero el gate NO pasa (0/5).**
El barajado rompió el confinamiento al eje X (moves en Y: 0.7% → 25%, gather
0 → 50, consume 0 → 11), pero los 5 agentes mueren igual al día 11. El fallo
residual es gestión de energía, no navegación ni escritura de acción. Activa
el Paso 2 del handoff: decidir qué es operacionalmente el "oráculo".

## Paso 0 — disponible vs motor: SIN divergencia (cerrado)

Test `test_gather_disponible_exactamente_cuando_el_motor_lo_acepta`: agente en
cada celda a distancia Manhattan ≤ 2 del recurso → `gather` aparece en
`acciones_disponibles` **si y solo si** `world.gather()` devuelve `ok`
(distancia ≤ 1). Resultado: coincidencia exacta en las 13 celdas. El motor no
estaba ocultando la acción; el eslabón era de navegación.

## Paso 1 — barajado del menú (implementado + testeado)

`WorldState.menu_rng` — RNG independiente sembrado por seed (avanza aparte de
`self.rng`, no perturba spawn/clusters ni el determinismo del estado). Baraja
las direcciones de `move` en `available_actions`. Aplicado idéntico en las 4
condiciones (mismo método).

Tests:
- `test_menu_move_barajado_reproducible_misma_seed` — mismo seed ⇒ mismo orden.
- `test_menu_move_barajado_cambia_entre_seeds` — 8 seeds ⇒ >1 orden distinto.

Suite completa: **156 passed**.

## Gate re-corrido (`data/silver/gate_oraculo2/`, oráculo 30d seed42 d=7%)

| Métrica | Orden fijo (antes) | Barajado (ahora) |
|---|---|---|
| Supervivientes | 0/5 | **0/5** |
| Muerte | día 11-13 | día 11 |
| move ok | 137 | 136 |
| **gather ok** | **0** | **50** |
| **consume ok** | **0** | **11** |
| moves con ΔY≠0 | 1 (0.7%) | **34 (25%)** |
| Navegación ACERCA/ALEJA (Manhattan) | 41% / 59% | **57% / 39%** |
| heldout_clean | true | true |

Direcciones elegidas: `(1,0)×36 · (-1,0)×66 · (0,-1)×26 · (0,1)×8` — los dos
ejes aparecen; antes era 137/138 horizontales.

### Lectura

1. **El sesgo posicional era real.** El menú en orden fijo hacía que el 7B
   copiara el primer/segundo ítem y se confinara al eje X. El 0/5 previo
   medía (en parte) el orden de un array, no la capacidad del modelo. El
   barajado es corrección de instrumento y queda en el motor para siempre.
2. **El 7B sigue sin sobrevivir.** Con navegación en 2D (57% acerca al recurso)
   y acceso efectivo a comer (50 gather, 11 consume), muere de hambre igual.
   Ahora recoge más de lo que consume: acumula inventario y el metabolismo +
   costo de move lo drena. **Este es un límite del modelo, sobre datos
   limpios** — sin bug de reloj, sin sesgo posicional.

## Paso 2 — PENDIENTE: decisión sobre el "oráculo" (se lleva a Opus/Comandante)

El fallo ya no es mecánica. La pregunta es la del handoff: qué significa
operacionalmente "oráculo". Opciones, de menor a mayor intervención:

1. **Modelo más grande solo para el oráculo** (`qwen3:8b`, `gemma4-qat:12b`
   instalados). Riesgo: rompe comparabilidad entre condiciones (el oráculo
   deja de diferenciarse solo por la información).
2. **Oráculo = `DeterministicAgent`** (techo informado no-LLM, D-019). Mide
   "cuánto de la brecha cubre el LLM contra una política de reglas perfectas".
3. **Aceptar que el 7B no es agente viable a 30 días** y reportarlo como
   resultado de ronda 0 (no fallo de andamiaje).

Nota (Terra/Codex, vía Comandante): sugirió `qwen3:4b` con thinking
desactivado. **PROBADO y DESCARTADO (13/08, smoke a nivel de modelo)**:
instalado `qwen3:4b`; el razonamiento va al campo `reasoning` de la
respuesta — con `max_tokens` bajo el `content` queda vacío. `"think": false`
es CONTRAproducente (razona 3× más — 800 vs 282 tokens — y deja `content`
vacío). Default produce JSON válido en `content` pero ~5.6s/llamada y ~280
tokens (vs 1.5s/120 de `qwen2.5:7b`): más lento y más pequeño, sin beneficio
como oráculo. La sugerencia de Terra no se sostiene empíricamente.

**La decisión se escribe en `docs/DECISIONES.md` ANTES de correr la ronda 1**
(criterio de Opus, sin negociar). Queda a la espera de la luz verde.

## Paso 3 — NO abierto

0/5 < 3/5 ⇒ **no** se crea `docs/gates/ronda1.gate`. Ronda 1 sigue bloqueada
en código (`scripts/worldlab_ronda1_recurrente.sh` se niega sin el gate).

## Qué NO se tocó

- Mundo (config, densidades, efectos, tabla de verdad) — intacto.
- Baseline empírico — intacto (11.081 gathers, 4.931 consumes de referencia).
- Otras condiciones (sin_memoria/memoria/baseline) — intactas.
- `data/silver/ablation_sleep_PRE-FIX_descartado/` — conservado (evidencia).
- Visor — intacto (el P1 de exposición ya lo arregló Opus; no re-tocado).

## Diagnóstico DeepSeek API (NO concluyente — 1 mundo, a pedido del Comandante)

Pregunta: ¿siguen muriendo al día 11 con un LLM *competente*? Re-smoke con
`deepseek-chat` vía API (`data/silver/gate_oraculo_ds/`, oráculo 30d seed42
d=7%, flag `--backend openai` agregado en `0172947`).

| Métrica | qwen2.5:7b (barajado) | **deepseek-chat** |
|---|---|---|
| Supervivientes | 0/5 | **0/5** |
| Muerte | día 11 | día 12 |
| gather | 50 | **84** |
| consume | 11 | **69** |
| move | 136 | 98 |
| tokens | 341k | 535k (~$0.17) |

**DeepSeek es objetivamente más competente** — come 6× más (69 vs 11 consumes),
recolecta más (84 vs 50), navega hacia los recursos desde el día 1. **Y muere
igual (día 12, un día más tarde).**

**Hallazgo fino — por qué muere DeepSeek (con datos):** comió 69 veces, TODAS
en región A. Desglose del `energy_gain`: 30× S2-A-fase1 = **+1**, 23×
S2-A-fase0 = **−2**, 5× S4-A-fase1 = **−8**, 11× S3 = 0. O sea, **28 de 69
comidas le restaron energía** (neto ≈ −86). La comida buena (S2 en B = +7)
estaba INTACTA al final: 8 celdas de S2 en B con stock, y los agentes pisaron
B solo **4 de 61 snapshots**. No es falta de comida ni de movimiento — es que
**no cruza a la región donde la comida vale**: come donde cae mal (A) y se
envenena, mientras la comida de +7 está a unos pasos en B, sin tocar.

**Implicación (precisión de Terra aplicada):** el fallo NO es (solo) del 7B.
No sabemos que el mundo sea inviable para *cualquier* LLM — sabemos que es
inviable a 30d/d=7% para los **dos perfiles evaluados**: `qwen2.5:7b` local y
`deepseek-chat` informado. Eso ya basta para bloquear LE en Ronda 1: DeepSeek
descarta la hipótesis cómoda de que era solo insuficiencia del 7B — entiende
el contrato, navega, recolecta y consume mucho más, pero no alcanza la
eficiencia de supervivencia.

**Lectura (Terra):** el mundo es habitable para una **política reactiva
optimizada** (baseline empírico), pero NO para un **agente LLM que decide vía
llamadas discretas**, incluso informado. El problema dejó de ser "qué oráculo
elegir" y pasó a: ¿es la supervivencia de largo horizonte un prerrequisito
legítimo de la prueba de composición? No suavizar el mundo (contaminaría la
interpretación). Opciones para Opus:

1. **Separar Ronda 1 como evaluación de capacidad/viabilidad LLM**, sin LE ni
   pretensión de composición.
2. **Rediseñar el protocolo** para que el probe de composición ocurra ANTES de
   que la supervivencia sea el cuello de botella (declarando el cambio antes
   de re-correr).
3. **Mantener el diseño** y aceptar que la hipótesis exige modelos/agentes más
   eficientes que los probados.

Con DeepSeek, "probar otro modelo" deja de ser la acción más informativa.

## Respuesta de Terra a las 3 preguntas (13/08)

**Clasificación:** (a) planificación espacial-temporal como causa principal, (b)
horizonte discreto como mecanismo agravante, (c) **sin evidencia** de composición
negativa.

- El dato NO muestra composición: DeepSeek posee la tabla (oráculo) pero **no la
  usa para controlar su política** — comió 28/69 recursos dañinos y dejó S2-B
  intacto. "Saber la tabla" ≠ "que el conocimiento controle la política".
- La cadena *tabla→elegir B→navegar→mantener posición→anticipar cierre→consumir
  en fase favorable→retirarse* **falla al inicio**: no sostiene presencia en B
  (4/61 snapshots).
- (c) no aplica: el oráculo recibe la respuesta completa (no compone desde
  experiencia). El hallazgo es de **control de política bajo conocimiento
  perfecto**, no de composición negativa.

**Recomendación (cambiada): variante de Opción 2, con dos gates separados.**

1. **Gate cognitivo** — probes de predicción sobre celdas vividas/retenida
   ("¿qué vale S2 en B?") ANTES de morir. Para el oráculo verifica que la
   representación de la regla está disponible (recuperación de tabla); para
   memoria/sin-memoria exige exposición real de consumo.
2. **Gate de política** — tarea corta y predefinida de navegación contextual
   ("alcanza B, consume S2 en fase clara, sal antes del cierre") con métricas de
   éxito por etapas. Diagnóstico de si el agente convierte modelo→acción.

Con esto, Ronda 1 respondería honestamente: *"¿los LLM adquieren y expresan un
modelo composicional antes del colapso metabólico?"*, sin usar LE de
supervivencia como requisito. La supervivencia a 30 días quedaría como métrica
**secundaria** de competencia agente-entorno. No mover la métrica primaria de
composición a un probe temprano sin registrar esa bifurcación de protocolo
(mezclar supervivencia con composición hoy oculta la segunda detrás de la
primera).
