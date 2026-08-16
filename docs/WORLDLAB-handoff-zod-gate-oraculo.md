# Handoff a Zod — abrir el gate del oráculo y recién ahí correr la ronda 1

Fecha: 2026-08-13 · Rama: `redesign/visor-panel-instrumentos` · Último commit: `4a419fd`

## Estado en una línea

**La ronda 1 NO se lanza todavía.** El gate del oráculo se volvió a correr con el
motor arreglado y falló otra vez: **0/5**. Pero falló de una forma nueva y mucho
más localizada, y eso es lo que hay que resolver.

## Qué cambió desde tu último reporte

**1. Bug del motor: el horizonte congelaba a los agentes de por vida.**
`ai/simulate.py` guardaba `next_think = world.tick + horizonte` contra un
`world.tick` que se reinicia a 0 cada día (`world_state.py:585-588`). Cualquier
horizonte que cruzara la medianoche daba un valor inalcanzable: el agente **no
volvía a decidir nunca**, salvo que su energía cayera bajo 15 (moribundo).
Arreglado con reloj absoluto + test permanente (`tests/test_simulate.py`).

Esto explica tu hallazgo anterior sin necesidad de invocar la capacidad del
modelo: el oráculo que "solo caminó" (1.202 move, 0 consume) es exactamente lo
que produce un agente congelado que despierta moribundo. Y explica por qué solo
el baseline sobrevivía: `EmpiricalAgent` no devuelve horizonte, nunca se
congelaba. **Ninguna conclusión sobre supervivencia de las condiciones LLM en la
ronda 0 sobrevive a este bug.** El andamiaje sí se mantiene.

**2. El prompt seguía mintiendo.** Decía `0.5` de metabolismo hardcodeado
mientras `run_pilot` corre el mundo a `0.3`. Ahora se lee de
`world.config.energy_per_tick`.

**3. `--force-sleep N`**: ablation que fija el horizonte e ignora el del modelo
(idéntico en las 3 condiciones LLM). El trace conserva `sleep_ticks_modelo`.
Marca los datos como `ablation_no_confirmatorio`.

**4. Dos P1 del análisis de Codex, arreglados.** El visor calculaba exposición
por ticks vividos en vez de ≥3 consumos ok (D-025) — contradecía a
`analyze_pilot`. Y el bloqueo de la ronda 1 vivía solo en la bitácora: ahora
`scripts/worldlab_ronda1_recurrente.sh` exige `docs/gates/ronda1.gate`.

## El gate re-corrido (motor arreglado): 0/5

`data/silver/gate_oraculo/` — oráculo, 30d, seed 42, d=7%, 537s, 228k tokens.

| Dato | Valor |
|---|---|
| Supervivientes | **0/5**, todos muertos al día 11 |
| Acciones ok | 137 `move`, 16 `talk` — **0 `gather`, 0 `consume`** |
| Rechazos | 1 (la mecánica ya no es el problema) |
| Decisiones tomadas | 165 (antes 68: el fix del reloj sí devolvió turnos) |
| Decisiones con `gather` disponible | **0 de 165** |
| Distancia mínima alcanzada a un recurso | 2, 3, 4, 4, 4 — **todas el día 1** |

Traducción: nacieron a 2-4 celdas de comida, se movieron 137 veces y **ninguno se
acercó más que su posición de nacimiento**. Y sí la veían: la primera observación
de a0 incluye `{"dx": 1, "dy": -2, "rkind": "S2", "kind": "resource"}`.

Con el motor arreglado, el fallo ya no es "no tuvo turnos" ni "no supo escribir la
acción". Es **navegación local hacia un objetivo visible a 2 pasos**.

## Tu tarea

### Paso 0 — Descartar que el motor no le ofrezca la acción (30 min)

Antes de culpar al modelo hay que cerrar la puerta del motor. `gather` solo entra
en `acciones_disponibles` si hay recurso adyacente; si `available_actions()`
tuviera un criterio de adyacencia más estrecho que el de `world.gather()`, el
agente jamás vería la opción por más bien que navegue.

Test a escribir en `tests/test_available_actions.py`: agente colocado en cada una
de las 8 celdas vecinas a un recurso (y encima de él) → `gather` debe aparecer
exactamente cuando `world.gather()` lo aceptaría. Si divergen, ese es el bug y no
hay nada que discutir sobre el modelo.

### Paso 1 — RESUELTO: el agente solo se mueve en el eje X

Corrido sobre los 138 moves del gate (todos con recurso a la vista, ninguno a
ciegas):

| Métrica (Manhattan al recurso más cercano) | Valor |
|---|---|
| Se ACERCA | 57 (41%) |
| Se ALEJA | **81 (59%)** |
| Move óptimo elegido | 41% |
| **Direcciones elegidas** | **(1,0)×74 · (-1,0)×63 · (0,1)×1 · (0,-1)×0** |

**137 de 138 movimientos son horizontales.** El agente oscila izquierda-derecha
(74 vs 63, una caminata aleatoria en un eje) y prácticamente **nunca usa el eje
Y**. Los 5 agentes nacen en `y=15` y murieron en `y=15`. Cualquier recurso que
exija cambiar de fila —como el que a0 veía en `dy=-2` desde el tick 0— es
inalcanzable por construcción.

**Hipótesis principal: sesgo posicional inducido por D-026.**
`world_state.py:761` construye el menú siempre en el mismo orden:
`((1,0), (-1,0), (0,1), (0,-1))`. La distribución observada es exactamente la de
un modelo que copia el primer o segundo ítem de la lista y casi nunca el tercero
o cuarto. El menú de acciones arregló los rechazos (91-96% → ~0) e introdujo, sin
que nadie lo notara, un sesgo que confina a los agentes a una línea.

**Test decisivo, barato y sin tocar el mundo:** barajar el orden del menú con el
RNG del mundo (determinista por seed) y volver a correr el gate. Es corrección de
instrumento, no de dificultad: el orden de una lista no debe ser información, y
hoy lo es. Si al barajar aparecen movimientos en Y, la hipótesis queda confirmada
y el 0/5 previo mide el orden de un array, no la capacidad del modelo.

Si al barajar el patrón NO cambia (sigue moviéndose en un solo eje, ahora otro),
entonces sí es el modelo, y aplica el Paso 2.

Ojo con la métrica: Chebyshev da 71% de "igual" y enmascara todo — moverse en un
eje hacia un objetivo diagonal no cambia esa distancia. Usa Manhattan.

<details>
<summary>Comando del análisis (por si hay que repetirlo sobre otra corrida)</summary>

```bash
.venv/bin/python - <<'PY'
import json
p='data/silver/gate_oraculo/gate_oraculo_7_s42_seed42_traces.jsonl'
ts=[json.loads(l) for l in open(p).read().splitlines()[1:]]
acerca=aleja=igual=sinrec=0
for t in ts:
    if t['proposed_action']['action']!='move': continue
    res=[v for v in t['observation'].get('visible',[]) if v.get('kind')=='resource']
    if not res: sinrec+=1; continue
    d0=min(max(abs(v['dx']),abs(v['dy'])) for v in res)
    a=t['proposed_action']['args']; dx=a.get('dx',0); dy=a.get('dy',0)
    d1=min(max(abs(v['dx']-dx),abs(v['dy']-dy)) for v in res)
    acerca+=d1<d0; aleja+=d1>d0; igual+=d1==d0
tot=acerca+aleja+igual
print(f'moves con recurso visible: {tot}')
print(f'  ACERCA {acerca} ({acerca/tot:.0%}) | ALEJA {aleja} ({aleja/tot:.0%}) | IGUAL {igual} ({igual/tot:.0%})')
print(f'moves sin recurso visible: {sinrec}')
PY
```
</details>

**Tu primera tarea concreta:** implementar el barajado del menú (RNG del mundo,
por seed, idéntico en las 4 condiciones), test que verifique que el orden cambia
entre seeds pero es reproducible con la misma seed, y re-correr el gate. Ese es
el camino más corto a un techo que mida algo.

### Paso 2 — Decidir con evidencia, y dejarlo escrito

Según el paso 1, la pregunta para el Comandante y Opus es **una sola**: qué
significa operacionalmente "oráculo". Si es el techo informado que da denominador
a LE, tiene que ser competente en navegación. Las salidas posibles, en orden de
menor a mayor intervención:

1. **Modelo más grande solo para el oráculo** (`qwen3:8b`, `gemma4-qat:12b-64k`
   están instalados). Riesgo: rompe la comparabilidad entre condiciones — el
   oráculo dejaría de diferenciarse solo por la información recibida.
2. **Oráculo = `DeterministicAgent`** (techo informado no-LLM, D-019 ya lo
   contempla como techo). Mide "cuánto de la brecha cubre el LLM contra una
   política con reglas perfectas", que es lo que LE quiere decir.
3. **Aceptar que el 7B no es agente viable en este mundo** y reportarlo como
   resultado de la ronda 0, no como fallo de andamiaje.

**Decidir esto DESPUÉS de ver los resultados es exactamente lo que la bitácora
existe para impedir.** Escribe la decisión en `docs/DECISIONES.md` con su
evidencia ANTES de correr la ronda 1, no después.

### Paso 3 — Abrir el gate y lanzar (solo si el smoke pasa)

Criterio de Opus, sin negociar: **≥3/5 supervivientes a 30 días**.

```bash
# re-correr el gate con lo que se haya decidido
.venv/bin/python -m ai.run_pilot --seeds 42 --days 30 --model <modelo> \
  --density 7 --conditions oraculo \
  --out-dir data/silver/gate_oraculo2 --exp-prefix gate2
```

Si pasa:

```bash
mkdir -p docs/gates
cat > docs/gates/ronda1.gate <<'EOF'
Desbloqueo de la ronda 1
Fecha: <YYYY-MM-DD>
Decidió: <quién>
Evidencia: gate del oráculo <N>/5 supervivientes a 30 días (data/silver/gate_oraculo2/)
Decisión de diseño asociada: D-0XX en docs/DECISIONES.md
EOF
git add docs/gates/ronda1.gate && git commit -m "gate: ronda 1 desbloqueada — oráculo <N>/5"
```

Recién ahí se agenda `scripts/worldlab_ronda1_recurrente.sh` cada 2 h (mecánica
del piloto: el bash sale en segundos, el python queda huérfano, `--resume` por
checkpoint; guard anti-doble-instancia ya arreglado). Meta 32 mundos, ~24 h.

## Prohibido

- **No suavices el mundo** para que sobrevivan. El baseline empírico vive ahí:
  11.081 gathers, 4.931 consumes. Si el LLM no vive, el resultado es sobre el LLM.
- **No apliques un fix a una sola condición.** Todo va idéntico en las 4, o se
  convierte en ventaja diferencial.
- **No lances la ronda 1 sin el gate.** El script ya se niega; no lo rodees.
- **No borres** `data/silver/ablation_sleep_PRE-FIX_descartado/` (datos del motor
  con el bug, se conservan como evidencia del hallazgo).

## Verificación

```bash
.venv/bin/python -m pytest tests/ -q     # 153 verdes
bash scripts/worldlab_ronda1_recurrente.sh   # debe decir RONDA 1 BLOQUEADA
```
