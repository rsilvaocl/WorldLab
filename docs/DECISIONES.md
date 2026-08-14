# WorldLab — Registro de Decisiones de Diseño

Formato: fecha · decisión · quién la tomó · estado

## D-032 · 2026-08-14 · Geometría de las regiones EXPLÍCITA, común a las 4 condiciones (Opus, revisada por Terra) · Aprobada
- **Problema.** El oráculo sabe que S2 en B vale +7 (clara) y +10 (oscura) y no
  puede encontrar B. Tras D-029 cada entidad visible trae su región, pero el
  radio de visión es 6: un agente en x=4 no ve ninguna entidad de B y no tiene
  de dónde inferir hacia qué lado queda. El probe lo mide exactamente así —
  `deepseek-v4-flash` acierta el rumbo **3/3 donde la información está** y
  **0/9 donde no está**, que es la conducta correcta de un agente que no
  inventa lo que no ve.
- **Evidencia del gate `gate_oraculo4` (30d, seed42, d=7%, v4-flash).** Los
  arreglos de instrumento mejoraron COMER y no movieron NADA en llegar a B:

  | | `gate_oraculo_ds` (13/08) | `gate4` (14/08) |
  |---|---|---|
  | supervivientes | 0/5 | 0/5 |
  | días de muerte | todos ~12 | 12, 14, 15, 15, **27** |
  | consumos | 69 | **131** |
  | comidas negativas | 28 (41%) | 41 (**31%**) |
  | **energía neta de comer** | **−86** | **+86** |
  | **cruces de frontera** | **1** | **1** |
  | presencia en B | 6,6% | 2,4% |
  | S2 en B intacta al final | sí | **sí, 8 celdas** |

  Dejó de envenenarse (−86 → +86) y la muerte se corrió del día 12 al 27 en el
  mejor agente. Cruzó la frontera **una vez en 30 días**, igual que antes.
- **Decisión (revisada tras consulta a Terra).** La geometría va en la
  **MECÁNICA base, idéntica en las 4 condiciones** — `world_geometry(cfg)`,
  generada de la config: *"El mundo mide 30x30. La región A es la mitad OESTE
  (x < 15) y la región B es la mitad ESTE (x ≥ 15); tu campo `position` es
  [x, y]."* **NO** va en `system_rules`.
- **Por qué la primera versión estaba mal.** La redacté solo para el oráculo.
  Eso arregla el techo y deja las condiciones experimentales rotas: un oráculo
  que llega a B contra un `memoria`/`sin_memoria` que estructuralmente no
  puede no es una diferencia de grado sino de tipo, y el denominador de LE
  deja de ser comparable. Peor: el probe de composición exige haber vivido
  B-clara para componer B-oscura, y en el piloto **ni la política reactiva
  optimizada la vive** (165 de 4931 consumos, 3,3%). Sin exposición, B-oscura
  no es composición: es adivinanza.
- **Por qué es percepción legítima (criterio de Terra).** Se limita a una regla
  espacial neutral. No presta efectos, valores ni predicciones. Separa dos
  tareas hoy confundidas: **localizar el contexto** y **aprender/componer su
  efecto**. Misma naturaleza que `acciones_disponibles` (D-026) y las etiquetas
  de región de D-029, coherente con D-012.
- **Qué cambia el experimento, declarado y no disimulado.** Deja de medir
  cartografía y exploración a ciegas. Es deseable si la hipótesis principal es
  la composición de (símbolo, región, fase), que es lo que el diseño afirma
  medir. Invariante permanente (`tests/test_geometria_comun.py`): las tres
  condiciones LLM reciben la MISMA geometría, y la diferencia exacta entre el
  prompt del oráculo y el de las otras sigue siendo su bloque de tabla — nada
  más.
- **Gate de exposición (punto 2 de Terra): YA EXISTE.** `MIN_EXPOSURE = 3` en
  `analyze_pilot.py`, con `exposure_per_cell` / `exposure_summary` (D-025):
  excluye del score de composición a los agentes sub-expuestos y reporta
  cobertura. No hay que construirlo, sí hay que **reportarlo siempre** junto
  al probe, nunca el promedio solo.
- **D-023 / D-017 no se tocan todavía** (criterio de Terra): no son
  autofrustrantes por sí mismas — nacer en B da exposición y la expulsión
  protege el held-out. Y la expulsión ya deja a los agentes en x≈14, **a un
  paso** de la frontera: el problema medido no es distancia física sino que no
  representan ni persiguen la frontera. Se revisan solo si tras la geometría
  común sigue sin haber exposición a B-clara.
- **Qué NO se hace.** No se amplía el radio de visión (cambia el mundo para
  las 4 condiciones). No se mueve la frontera ni se suaviza la barrera. No se
  toca la tabla de efectos.
- **Criterio de lectura tras aplicarla.** Si el oráculo cruza a B y sobrevive,
  el cuello era la localización de la frontera. Si cruza y muere igual, el
  cuello es metabólico y ahí sí aplica la bifurcación de protocolo que propuso
  Terra. Si NO cruza teniendo la frontera escrita, el fallo es de control de
  política con conocimiento perfecto — y eso sería el primer hallazgo
  cognitivo genuino de toda la serie, no un cuarto bug de instrumento.

## D-031 · 2026-08-14 · `deepseek-v4-flash` SIN razonamiento, en dos brazos (Opus) · Comandante · Aprobada
- **Decisión.** Las tres condiciones LLM corren con **`deepseek-v4-flash` y el
  modo de razonamiento DESACTIVADO** (`thinking: {"type": "disabled"}`).
  Reemplaza la elección de `gemma2:9b` de D-030, que se hizo con un criterio
  insuficiente. `baseline_empirico` no usa LLM (D-019) y no cambia.
- **Por qué cae `gemma2:9b`.** El banco de D-030 mide un solo brazo. Hay DOS:
  - **estático** — región y fase en el TEXTO de la pregunta. Es la condición
    de `predict_effect` (D-010, métrica primaria).
  - **contextual** — región y fase solo en la observación; el modelo tiene que
    ligar "aquí". Es la condición del BUCLE DE ACCIÓN, donde el agente vive.

  No ordenan igual, y ahí estuvo el error:

  | modelo | estático | contextual Q2 | Q3 (deducible) |
  |---|---|---|---|
  | **deepseek-v4-flash sin razonar** | **1.0** | **1.0** | **3/3** |
  | deepseek-v4-flash razonando | 1.0 | 1.0 | 2/3 |
  | qwen3:4b | 1.0 | 1.0 | 0/3 |
  | gemma2:9b | 1.0 | **0.083** | 0/3 |
  | llama3.1:8b | 0.875 | 0.75 | 2/3 |
  | hermes3:8b | 0.812 | 0.417 | 0/3 |
  | qwen2.5:7b | 0.688 | 0.0 | 0/3 |

  `gemma2:9b` no "maximiza": cita la etiqueta de una celda con el valor de otra
  dos filas abajo ("región A … fase 0 (clara): +7", línea que NO existe en el
  prompt). Confirmado en conducta: su smoke dio **0 consumos**, 20 moves, 17 de
  ellos al oeste. El "5/5 supervivientes a 5 días" era luz verde falsa — con
  ~100 de energía inicial y 0.3/tick todavía no necesitaban comer.
- **Por qué el razonamiento va apagado.** Los v4 razonan por defecto. Sobre el
  prompt real del agente (~1870 tokens) eso cuesta **58,5 s y 5076 tokens de
  salida por decisión**, contra **1,2 s y 29 tokens** sin razonar: 49× el
  tiempo y 175× la salida, y encima mide PEOR en Q3 (2/3 vs 3/3). El
  `deepseek-chat` con el que se corrió `gate_oraculo_ds` era exactamente este
  modo — la doc dice que los nombres viejos mapean a non-thinking/thinking de
  `deepseek-v4-flash`.
- **Costo y tiempo (medido, no estimado).** ~1,2 s/decisión ⇒ **≈3 h** de ronda 1
  secuencial. Consumo por decisión: **1613 tok de input con cache HIT, 204 de
  cache MISS, 30 de output** — 88,8% de tasa de acierto de caché, porque el
  system prompt (mecánica + tabla del oráculo) es estable y domina el prompt.
  Ronda 1 completa = 24 mundos (8 seeds × 3 condiciones LLM):

  | escenario | hoy | valle (desde 16/08) | pico (desde 16/08) |
  |---|---|---|---|
  | mueren ~día 12 | $0.35 | **$0.64** | $1.28 |
  | sobreviven 30 días | $0.90 | **$1.64** | $3.29 |

  **CORRECCIÓN a una afirmación previa mía**: escribí que los descuentos por
  horario habían terminado el 2025-09-05 y que el precio de v4 era plano. Era
  cierto hasta ahora y deja de serlo: DeepSeek **reintroduce facturación
  pico/valle el 16/08/2026 a las 16:00 UTC**, con el valle a la mitad del pico.
  Flash pasa de $0.14/$0.0028/$0.28 (in/cache/out) a $0.22/$0.0070/$0.66 en
  valle y $0.44/$0.014/$1.32 en pico.
  - **Pico**: 01:00–04:00 y 06:00–10:00 UTC = **21:00–00:00 y 02:00–06:00 en
    Chile** (UTC−4 en agosto). O sea el pico cae de noche: correr en horario
    laboral chileno ya es valle.
  - La palanca que más pesa sigue siendo el **cache hit**: mantener el system
    prompt estable byte a byte. Cualquier cambio que lo rompa (p. ej. meter la
    fecha o el seed en el system) multiplica el costo por ~5.
- **Nombres.** `deepseek-chat` y `deepseek-reasoner` se descontinúan; el default
  de `model_adapter` pasa a `deepseek-v4-flash`.
- **Lo que NO resuelve.** El rumbo a B solo es deducible dentro del radio de
  visión 6: en 9 de 12 muestras del probe no hay ninguna entidad de la otra
  región a la vista, y ahí ningún modelo puede inferir nada. `q3_heading_acc`
  = 1.0 sobre lo deducible y 0.25 sobre todo lo confirma. Queda ABIERTO y se
  decide antes del gate.

## D-030 · 2026-08-13 · `gemma2:9b` + tabla plana: el oráculo tiene que poder leer su oráculo (Opus) · Comandante · Aprobada · **SUPERSEDIDA por D-031 en la elección de modelo**
- Vigente: la tabla plana generada del motor y el criterio de las dos
  dimensiones. Caduca: `gemma2:9b` como modelo (ver D-031).
- **Decisión.** Las tres condiciones LLM (`sin_memoria`, `memoria`, `oraculo`)
  pasan de `qwen2.5:7b` a **`gemma2:9b`**, y la tabla del oráculo pasa al
  formato plano (16 líneas, un hecho por celda). `baseline_empirico` no usa
  LLM (D-019) y queda igual. Las dos mitades van juntas: `gemma2:9b` con la
  tabla ACTUAL da 0.812, con la plana da 1.0.
- **Por qué se reabre el Paso 2 del handoff, que yo mismo había cerrado.**
  El cierre anterior ("no cambies de modelo, rompe la comparabilidad") era un
  argumento sobre competencia de SUPERVIVENCIA y sigue en pie para eso. Este
  es otro: un modelo que no liga una de las dos dimensiones experimentales no
  produce medición interpretable en NINGUNA condición. Y la comparabilidad se
  preserva intacta si el cambio va a las tres condiciones LLM a la vez —
  la restricción es entre condiciones dentro de la ronda, no entre rondas.
- **Evidencia** (`ai/bench_oraculo.py`, 16 celdas = 4 símbolos × 2 regiones ×
  2 fases, calentamiento excluido). Azar de referencia para `level_acc`:
  **0.375** (estrategia trivial "contestar siempre el nivel modal"; 0.167
  uniforme). Con tabla plana:

  | modelo | nivel | región A/B | fase 0/1 | B-oscura | s/decisión |
  |---|---|---|---|---|---|
  | **gemma2:9b** | **1.0** | 1.0 / 1.0 | 1.0 / 1.0 | **1.0** | 7.17 |
  | llama3.1:8b | 0.875 | .88 / .88 | 1.0 / .75 | 0.75 | 3.22 |
  | hermes3:8b | 0.812 | .63 / 1.0 | .88 / .75 | 1.0 | 3.15 |
  | qwen2.5:7b (actual) | 0.688 | .63 / .75 | .88 / .50 | 0.75 | 3.27 |

  `gemma2:9b` es el único con 1.0 en las dos dimensiones Y en la celda
  retenida, estable en 3 pasadas (48 llamadas). Con la tabla ACTUAL,
  `qwen2.5:7b` marca 0.50 contra un azar de 0.375: **el oráculo vigente está
  en la estrategia trivial**, y `granite3.3:8b` cae exactamente en el azar.
- **Por qué importa más allá del brazo oráculo.** La fase es una de las dos
  dimensiones de D-014 y el probe de composición (D-005/D-010) pregunta por
  B-oscura, que exige componer región Y fase. Con `qwen2.5:7b` un 0% en
  B-oscura no es interpretable: no se distingue "no compuso" de "no puede
  indexar por fase". Eso contamina la métrica primaria en las cuatro
  condiciones, no solo en el techo.
- **La tabla plana NO agrega información**: los mismos 16 hechos de
  ORACLE_RULES, una línea por celda, sin indexación posicional. Es
  legibilidad, de la misma clase que el barajado del menú (D-029). Test
  permanente (`test_la_tabla_plana_no_agrega_informacion`) que falla si algún
  día se le cuela un hecho que ORACLE_RULES no tiene — si eso pasara dejaría
  de ser comparable y pasaría a ser intervención sobre el experimento.
- **Costo.** 7.17 s/decisión contra 3.27 del actual (medido con el prompt de
  producción, ~1870 tokens, carga en frío excluida). Ronda 1: **16,7 h** si
  los agentes mueren hacia el día 12 como hasta ahora, **43 h** como cota alta
  si sobreviven los 30 días. Contra las ~70 h que ya tomó el piloto y con la
  infra recurrente construida, es asumible. `gemma2:9b` ocupa 5,4 GB y entra
  holgado en los 16 GB del M2.
- **Plan B declarado: `hermes3:8b`** (3.15 s/decisión, mismo costo que hoy).
  Nivel 0.812 — peor promedio que llama3.1:8b — pero **12/12 en B-oscura**,
  donde llama falla 3/12. Si hay que aceptar un techo con fugas, conviene que
  las fugas queden lejos de la celda que mide la métrica primaria. Invocarlo
  obliga a declarar en la bitácora que el techo tiene error propio.
  Restituir: `OLLAMA_HOST=127.0.0.1:11434 ollama pull hermes3:8b`.
- **Descartado y por qué.** `gemma4-qat:12b-64k`: 1.0 pero 26.79 s/decisión
  (62-160 h de ronda) — inviable, y mi cifra previa de 23.2 s estaba inflada
  por incluir la carga en frío. `granite3.3:8b`: en el azar. `qwen3:8b`:
  9/12 inconsistente. `qwen2.5:7b-instruct-q8_0`: 0.562, la cuantización no
  era la causa. `hermes3:8b` con tabla actual: 0.312, **bajo el azar** — su
  especialización en tool-calling/JSON es ortogonal al fallo, que es de
  indexación y no de formato de salida (los cuatro modelos entregan 0 JSON
  malformados sobre el prompt real).
- **Lo que esta decisión NO resuelve.** El hueco de `visible_to` (D-029) sigue
  abierto: `gemma2:9b` sabe la tabla y sigue sin poder ver dónde queda B. Son
  huecos independientes y los dos se cierran ANTES de gastar el gate.

## D-029 · 2026-08-13 · La región es OBSERVABLE solo bajo los pies: tercer bug de instrumento (Opus) · Comandante · Aprobada
- **Hallazgo.** El oráculo recibe la tabla indexada por (símbolo, REGIÓN, fase),
  pero su observación reporta `region` SOLO de la celda donde está parado.
  Las entidades visibles (`visible_to`, radio 6) traen `dx, dy, rkind` y NINGUNA
  etiqueta de región. La frontera (`x >= int(width*region_split)`) no aparece en
  ninguna parte del prompt ni de la observación. Y el oráculo corre con
  `memory=None` (run_pilot.py:123): cada decisión es una llamada sin estado.
  **Consecuencia formal: desde una sola observación no existe función que lleve
  de `position` a "B queda al este".** El agente no puede deducir el rumbo aunque
  sepa la tabla de memoria. No es que no use el conocimiento — es que el
  conocimiento está indexado por una variable que no puede localizar.
- **Evidencia (corrida `gate_oraculo_ds`, deepseek-chat, seed42).**
  3 de 5 agentes NACEN en B (a2 x=18, a3 x=21, a4 x=23; D-023 funcionando).
  En la primera fase oscura (día 1, tick 12) la barrera los expulsa a x=13-14
  (D-017 funcionando). **Nunca vuelven**: 1 solo cruce de frontera en toda la
  corrida (a2, día 2, x=14→15, reexpulsado). Tras la expulsión derivan hacia el
  oeste hasta congelarse (a3: 21→14→13→12→11→10; a4: 23→13→12→11→10).
  Direcciones de move: (0,-1)×44, (0,1)×34, (-1,0)×13, **(1,0)×5** — se alejan de
  B 2.6× más de lo que se acercan, estando a UN paso. Los 69 consumos: 100% en A.
  El "4/61 snapshots en B" de Terra no es "no cruza a B": es "fue expulsado de B
  y no tiene con qué volver".
- **Reinterpretación.** La lectura de Terra ("posee la tabla pero no la usa para
  controlar su política") NO está sostenida por estos datos. La cadena
  tabla→elegir B→navegar no falla en el eslabón cognitivo: falla porque el
  eslabón de navegación pide información ausente de la observación. Es la misma
  clase de defecto que el reloj y que el orden fijo del menú — el tercero.
- **Decisión.** Ronda 1 sigue bloqueada. NO se rediseña el protocolo, NO se
  suaviza el mundo y NO se cambia de modelo hasta cerrar la observabilidad:
  1. Correr `ai/probe_observability.py` sobre las trazas reales (replay de
     observaciones vividas, 3 preguntas sin estado: región actual / valor aquí /
     rumbo a B). Firma esperada si el diagnóstico es correcto: Q1 y Q2 altas,
     Q3 en el azar (0.25).
  2. Si se confirma, exponer la región como PERCEPCIÓN (no como world model):
     etiquetar con su región cada entidad visible en `visible_to`. Es coherente
     con D-012 (identidad visible, propiedades ocultas) y con D-020 (no se
     presta ningún efecto: dónde estás no es qué pasa si comes). Aplicado
     idéntico en las 4 condiciones. Re-correr el gate.
  3. Recién con el gate re-corrido sobre instrumento limpio se decide si la
     supervivencia a 30 días es un prerrequisito legítimo del probe de
     composición (los dos gates de Terra quedan en espera, no descartados).
- **Paso 2 del handoff (qué es el oráculo) queda CERRADO sin cambiar de modelo.**
  El oráculo sigue siendo `qwen2.5:7b`: cambiarlo rompe la comparabilidad entre
  condiciones, que es lo único que el diseño mide. `DeterministicAgent` se corre
  en paralelo como techo informado no-LLM (D-019), nunca como "el oráculo".
  `qwen3:4b` ya fue descartado empíricamente (13/08).
- **Secundario a verificar.** `can_move` (world_state.py:337) no valida
  |dx|+|dy| ≤ 1 mientras el system prompt afirma "pasos de UNA casilla": el
  motor aceptó 2 saltos multi-celda ((1,-2) y (-3,-5)) fuera del menú. Impacto
  medido bajo (2/98 moves), pero el contrato dice una cosa y el motor otra.

## D-028 · 2026-08-13 · El visor distingue lo medido de lo derivado · Comandante · Aprobada
- `viewer.html` deja de ser reproductor y pasa a panel de instrumentos: anunciadores
  en verde (medido por el motor) vs ámbar (derivado por el visor: fase inferida,
  barrera supuesta, sin probe, sin trazas, sub-expuesto, filtro activo).
- Motivo: el visor anterior permitía una conclusión falsa — escondía los intentos
  rechazados por defecto (`okOnly` arrancaba en true) y presentaba la frontera
  cerrada como hecho medido. Un revisor podía leer una corrida sana donde había
  91-96% de rechazos. Ahora los fallos se ven por defecto y filtrar enciende lámpara.
- Abre lo que existía en disco sin superficie: `<exp>_seed<N>_traces.jsonl`
  (decisión del modelo) y `<exp>_probes.jsonl` (resultado del experimento; OJO:
  probes NO lleva sufijo `_seed<N>`). Cuadrante 2x2 región × fase con la celda
  retenida rayada, y el exit probe como calibración (predicho vs verdad del motor).
- El visor NO entra al experimento: es instrumento de auditoría, coherente con
  D-001 (alias legibles solo en el visor, nunca en el prompt).

## D-022 · 2026-08-13 · Requisito de discriminación de niveles en el probe (Opus, spec v1.1) · Aprobada
- La celda retenida debe caer en un nivel de magnitud DISTINTO al de las tres vividas.
- La primera tabla fallaba en 3 de 4 símbolos: S1 empataba con B-clara; S3 y S4
  tenían las 4 celdas iguales. Solo S2 exigía composición real.
- Valores recalibrados: S1(+8,-9,-4), S2(-2,+9,+3), S3(0,0,0) control (fuera del
  score), S4(+1,+6,-9). Test permanente: falla si una edición rompe la separación
  de niveles. S3 queda EXCLUIDO del score de composición (material, no alimento).

## D-023 · 2026-08-13 · Nacimiento repartido entre regiones (Opus, spec v1.1) · Aprobada
- Los 5 agentes nacen repartidos (2 en una región, 3 en la otra; lado por seed),
  NUNCA todos en la misma. El piloto mostró el costo: 92% sub-expuesto con 0
  consumos en B-clara.
- La causa de fondo es una TRAMPA DE EXPLOTACIÓN (no falta de días): una política
  que aprende descubre que S2 es malo en A y deja de probarlo; pero S2 solo revela
  su valor en B. Nacer repartido entrega experiencia de ambas regiones por
  construcción. Efecto lateral deseable: asimetría para posible intercambio.

## D-024 · 2026-08-13 · Probe de salida al iniciar la inanición (Opus, spec v1.1) · Aprobada
- Además de las rondas periódicas, se dispara un probe cuando la energía llega a 0
  y arranca el contador de inanición — antes de que el agente desaparezca. Captura
  su estado de conocimiento final en vez de perderlo con él.

## D-025 · 2026-08-13 · Corte de exposición ≥3 consumos por celda (Opus, spec v1.1) · Aprobada
- Un agente con <3 consumos en alguna celda vivida queda marcado sub-expuesto y su
  probe retenido se reporta APARTE, fuera del score de composición.
- Sin el corte, el 0/41 del baseline en la retenida es ambiguo: no era que B-oscura
  fuese incomponible — nunca había consumido en B. Respondía desde la única región
  que conocía. La exposición se calcula post-hoc desde el JSONL (los eventos consume
  ya registran region y phase).

## D-026 · 2026-08-13 · Acciones disponibles en la observación (Opus, spec v1.1) · Aprobada
- La observación incluye la lista de acciones EJECUTABLES en este instante, con
  argumentos ya rellenados ({"action":"gather","args":{"target_eid":"e_0447",...}}).
- NO es prestar world model: se dicen los botones que existen, no qué hacen. La
  decisión sigue siendo del agente; lo que se elimina es el ruido de saber escribir
  la API del motor (91-96% de rechazos LLM: gather lejano + consume sin rkind).
- Se aplica idéntico en las 4 condiciones, o se convierte en ventaja diferencial.

## D-027 · 2026-08-12 · Piloto completo (96 mundos, ~70 h) · Comandante · CUMPLIDA
Se mantiene el piloto a 100 días con las 3 densidades (12/7/4%) × 4 condiciones
× 8 seeds. Sin límite de tiempo: la Mac queda dedicada al experimento (no se
apagará ni se usará para trabajos pesados). Los mundos baseline_empirico (24)
son instantáneos; los 72 LLM a qwen2.5:7b local ~58 min/mundo. El proceso corre
como huérfano (PPID 1) con checkpoint por mundo + job recurrente cada 2 h como
respaldo.

## D-001 · 2026-08-11 · Ontología abstracta (crítica #1 de Claude) · Aprobada
- Recursos con IDs opacos (S1..S4 en el mundo experimental; nombres bonitos solo en el visor).
- Recetas de crafting arbitrarias, definidas en `WorldConfig.recipes` y validadas en el motor.
- **Test anti-fuga semántica**: `tests/test_semantic_isolation.py` falla si cualquier cadena
  semántica (food/water/comida/...) entra al payload de percepción. Verificado: 0 fugas.

## D-002 · 2026-08-11 · Primitivas físicas, no semánticas (crítica #2 de Claude) · Aprobada
- NO existe `trade()`. Existen: move, gather, consume, drop, pickup, give, build, talk.
- Si emerge intercambio condicionado a valor, se construye desde drop/pickup/give.

## D-003 · 2026-08-11 · Percepción explícita (decisión de Opus) · Aprobada
- El agente distingue el tipo de recurso a distancia (`rkind` en percepción).
- eids SIEMPRE opacos (`e_0001`, `r_0`, `b_hut_...`), el tipo nunca viaja en el id.
- No se revelan cantidades exactas de recursos (solo existencia).
- El agente percibe su `region` y la `phase` actual (condición necesaria para world modeling).

## D-004 · 2026-08-11 · Interdependencia: 3 + 4 (Opus corrigió a Zod) · Aprobada
- **Cúmulos como forma del mundo** (constante estructural, NO variable): los recursos
  vienen agrupados por región. El reparto uniforme no es neutro — con radio de visión
  limitado, uniforme significa que todos tienen todo cerca y nunca hay asimetría.
- **Densidad de recursos como parámetro barrido** (2-3 niveles en el piloto: holgado/justo/hambre).
- Descartada la especialización dura (crítica #3: mediríamos nuestro propio diseño).

## D-005 · 2026-08-11 · Condiciones cruzadas: DOS con cruce retenido (Opus) · Aprobada
- Dos condiciones independientes: Dónde (región A/B) × Cuándo (fase clara/oscura) = 4 situaciones.
- El agente solo vive 3: región B inaccesible durante fase oscura (barrera del mundo).
- La pregunta retenida ("▲ en B-oscura") solo se responde componiendo las dos reglas;
  imposible por memoria → diferencia entre condicionamiento y world modeling.
- Predicción con respuesta correcta objetiva generada por el motor (sin codificación subjetiva).
- Infraestructura implementada: `phase_ticks`, `phase_barriers`, `consume_effects`,
  percepción con region+phase (tests en `test_crossed_conditions.py`).
- Mitigación del riesgo (mundo difícil → planos): el piloto verifica primero que el agente
  aprende la regla simple (una condición saliente); solo entonces la composición es interpretable.

## D-006 · 2026-08-11 · Métrica primaria: LE normalizada (Opus) · Aprobada
- LE = (memoria − sin_memoria) / (oráculo − sin_memoria), medida en mundo de física contrafactual.
- Adimensional, comparable entre mundos. Pre-especificada, única (sin comparaciones múltiples).

## D-008 · 2026-08-11 · Comunicación: CANAL SIMBÓLICO (decisión del Comandante, opción 1 de Opus) · Aprobada
- talk() emite SOLO símbolos del alfabeto del mundo (`k1..k9`), sin significado asignado.
- El lenguaje natural queda PROHIBIDO en el canal (reintroduciría la semántica humana).
- Los agentes dentro de `hear_radius` reciben el mensaje en su inbox; la percepción
  incluye `heard` (últimos 5 mensajes oídos).
- Medición de emergencia: información mutua entre símbolo emitido y estado/acción
  posterior — sin interpretación humana.
- El visor puede traducir ("a2 emitió k7 y a4 se movió") SIN que esa lectura entre al experimento.

## D-009 · 2026-08-11 · Efectos SEPARABLES (Opus) · Aprobada
- `consume_effects` se genera con `build_separable_effects(base, δ_región, δ_fase)`:
  efecto(r, región, fase) = base(r) + δ_región(r, región) + δ_fase(r, fase).
- La celda retenida (B-oscura) es DERIVABLE: B-oscura = A-oscura + (B-clara − A-clara).
- Invariante de separabilidad testeado permanentemente (`separable_invariant_holds`).
- La fase tiene efecto propio (δ_fase ≠ 0 en ≥2 recursos) — si no, B-oscura == B-clara.

## D-010 · 2026-08-11 · Probe con MAGNITUD (Opus) · Aprobada
- El probe pide el cambio de energía y evalúa en 6 niveles de magnitud
  (0=pérdida grande ... 5=ganancia grande); el azar cae a ~17%.
- Se registran predicted_level, truth_level, level_correct + sign_correct (secundaria).

## D-011 · 2026-08-11 · Forma del mundo: escasez espacial (cúmulos) · Comandante
- Los recursos vienen en cúmulos (8, radio 3, 4 por región); la densidad es la
  única variable de presión barrida (12/7/4%).
- El agrupamiento es CONSTANTE ESTRUCTURAL, no una variable (corrección de Opus).

## D-012 · 2026-08-11 · Percepción: identidad visible, propiedades ocultas · Comandante
- El agente distingue el tipo de recurso a distancia (rkind opaco); no ve cantidades exactas.
- eids siempre opacos; hear_radius (6) > visión (4): un agente oye a quien no ve.

## D-013 · 2026-08-11 · Regla del mundo: propiedades condicionadas por contexto · Comandante
- El efecto de consumo depende de (símbolo, región, fase), no de recetas ni aniquilación.

## D-014 · 2026-08-11 · Dos condiciones ortogonales con cruce retenido · Comandante
- Región × fase = 4 celdas; el agente vive 3; B-oscura solo se responde componiendo.

## D-015 · 2026-08-11 · Ontología concreta (4 símbolos, separables, 8 cúmulos) · Opus + Comandante
- S1(+8,-11,-4), S2(-2,+9,+3), S3(0,0,0), S4(+1,0,-1); efectos generados con
  build_separable_effects; invariante permanente. Spec: docs/superpowers/specs/.

## D-016 · 2026-08-11 · Agentes con utilidad idéntica (sobrevivir) · Opus + Comandante
- Sin perfiles diferenciados: cualquier asimetría dictada por config sería una
  explicación alternativa de lo observado. La heterogeneidad viene de la geografía.

## D-017 · 2026-08-11 · Expulsión de B al comenzar la fase oscura + invariante · Opus + Comandante
- Al entrar la fase oscura, los agentes en B son EXPULSADOS a la celda libre más
  cercana en región no bloqueada (búsqueda en espiral) — nadie puede vivir B-oscura.
- Red de detección permanente: `no_heldout_consumption()` — ningún consume ok en
  celda bloqueada. Test falla si se contamina el held-out por cualquier vía.
- Alfabeto simbólico reducido a 4 (`k1..k4`): el estimador de MI está sesgado al
  alza con alfabeto grande y pocos datos.
- Emergencia de señalización se mide con MI contra NULO POR PERMUTACIÓN (no contra cero).

## D-018 · 2026-08-11 · El agente elige su propio horizonte de despertar · Opus + Comandante
- Junto con su acción declara sleep_ticks; el motor lo respeta salvo emergencia (hambre).
- Ataca la crítica #13 (el trigger de evento ES la decisión); el horizonte es métrica
  (un agente que entendió el ciclo debería despertar antes de que cierre la frontera).
- Registrado en el trace como sleep_ticks.

## D-019 · 2026-08-11 · Baseline EMPÍRICO (corrección de Opus: oráculo encubierto) · Aprobada
- El baseline de COMPARACIÓN es EmpiricalAgent: tabla de efecto promedio
  OBSERVADO por (símbolo, región, fase), poblada por sus propios consumos
  (hook record_outcome, misma vía que el LLM). Sin datos: default 0.0 —
  se envenena las primeras veces, como el LLM. NO lee cfg.consume_effects.
- DeterministicAgent queda como techo INFORMADO (oráculo determinista):
  informativo (si el LLM no le gana a un greedy con reglas perfectas, eso
  dice algo), pero no es el baseline de la condición 3 de emergencia.
- Params óptimos empírico (grid search, ontología v1): eat 30, build 4,
  explore 0.15, score 112.0 (vs 114.7 del informado: para sobrevivir casi
  empatan; la diferencia real aparece en el probe retenido — el greedy no compone).

## D-020 · 2026-08-11 · World model NO prestado al agente (corrección de Opus) · Aprobada
- _make_prediction SALIÓ del prompt y del trace: si le damos predicciones
  nuestras, después no podemos preguntarnos si lo construyó él (crítica #5/#12).
- Donde se mide su predicción es en predict_effect() (forced-choice: preguntar
  sin decir) — esa asimetría es lo que hace que el probe signifique algo.
- Bug confirmado en el bloque eliminado: v["kind"] es "resource" (categoría de
  entidad), nunca "food" — el expected_energy_gain era un número inventado.

## D-021 · 2026-08-11 · Recetas dinámicas en el baseline (corrección de Opus) · Aprobada
- El baseline construía "hut" hardcodeado (baseline.py:85); la receta es
  "struct_a". Ahora itera sobre world.config.recipes — cualquier receta del
  mundo participa. Efecto medido: la demo pasó de 0 a 8 estructuras.




## D-007 · 2026-08-11 · Orden de operaciones (Opus) · Aprobada
- Pre-registro DESPUÉS del piloto, no antes. El N sale de σ entre mundos (cálculo de potencia).
- Baseline determinista parametrizado y OPTIMIZADO (re-optimizado tras fixes de mecánica: D-001).
- Oráculo recibe las reglas del mundo (ground truth), no una traza reconstruida.
- Mundos de desarrollo vs reservado; condiciones intercaladas en misma ventana temporal.
