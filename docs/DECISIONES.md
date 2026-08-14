# WorldLab — Registro de Decisiones de Diseño

Formato: fecha · decisión · quién la tomó · estado

## D-029 · 2026-08-13 · La región es OBSERVABLE solo bajo los pies: tercer bug de instrumento (Opus) · PROPUESTA
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
