# WorldLab — resultado de la ronda de composición (banco v2, D-035)

Fecha: 2026-08-15. Rama: `zod/gate-guard-diagnostico`.

Ronda corrida por Zod tras el gate V2 (pasa=true, 0.955). Banco
`composicion_bank_v2.json` (32 ontologías, seed 20260815, disjunto del v1).
Modelo gemma2:9b local, temperature=0, 6 agentes por condición y ontología.

Evidencia en disco: `data/silver/composicion_bank_v2/composicion_summary.json`
+ `data/silver/composicion_bank_v2/composicion_probes.jsonl` (576 probes por
condición).

---

## Cobertura de exposición (obligatorio)

192/192 agentes con cobertura completa en las tres condiciones (5.184 consumos
por condición). La Fase E entregó las 3 celdas × 3 símbolos × 3 repeticiones a
todos. El probe es interpretable.

## Resultado del contraste primario

`memoria_indexada − sin_memoria`, pareado por ontología (32 diferencias).

| condición | correctos | proporción | sin_respuesta |
|---|---|---|---|
| `memoria_indexada` | 12/576 | **0.021** | 66 (11%) |
| `memoria_indexada_corrupta` | 49/576 | 0.085 | 223 (39%) |
| `sin_memoria` | 108/576 | **0.188** | 0 |

- **diferencia media: −0.167**
- **permutación pareada: p = 0.0004** (n=32)
- **bootstrap IC95%: [−0.25, −0.09]** (no cruza cero)
- azar de referencia del banco v2: **0.188** (mejor estrategia constante)

`sin_memoria` rinde 0.188 — clavado en el azar, como debe un control sin
información. `memoria_indexada` rinde 0.021 — **diez veces por debajo del
azar**, y la diferencia es estadísticamente significativa.

## Lectura

La experiencia accesible **no ayuda a componer B-oscura: interfiere**. Con su
memoria indexada delante (que el gate confirma legible a 0.955), el agente
acierta el 2% de la celda retenida, contra 18.8% sin memoria y 18.8% de azar.

Mecanismo plausible y coherente con el diseño: B-oscura nunca está en la
memoria, y por D-022 su nivel de magnitud es distinto al de las tres vividas.
El agente recupera un valor vivido y lo responde en vez de componer → cae en el
nivel equivocado. Sin memoria, responde su prior, que coincide con la
estrategia constante del banco. Distribución por ontología: `memoria_indexada`
da 0.000 en 30/32 y 0.333 en 2/32; `sin_memoria` reparte 0.0/0.333/0.667.

Es el resultado "en contra de la hipótesis" que se anticipó antes de correr: la
memoria accesible no se traduce en composición. Es publicable y es exactamente
lo que este andamiaje existe para poder afirmar sin que un bug decida la
respuesta.

## Matiz a evaluar por Terra (no lo afirmo, lo dejo)

- `sin_respuesta`: `memoria_indexada` 66, `corrupta` 223 (39%), `sin_memoria` 0.
  La corrupción hace que el modelo falle en devolver `energy_change` parseable
  mucho más que las otras. La proporción se calcula conservadora (None = no
  correcto), así que el 0.021 no se infla; pero la asimetría de sin_respuesta
  entre corrupta (39%) e indexada (11%) es un dato para entender el mecanismo.
- `memoria_indexada_corrupta` (0.085) queda entre indexada (0.021) y sin_memoria
  (0.188): el contenido permutado "daña" menos que el contenido verdadero — que
  es coherente con que la interferencia venga del CONTENIDO, no de la estructura.

## Qué NO se tocó

- Banco v2 intacto, seed no regenerada.
- Renderer prosa congelado (D-035).
- temperature=0 fija.
- v1 intacto (calibración, no inferencia).
- Ninguna ontología excluida.
