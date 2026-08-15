# WorldLab — Bitácora de rondas

Registro fechado de cada ronda experimental: qué se corrió, qué salió, qué se cambió
después y **qué se decidió no cambiar**.

## Por qué existe este documento

Cuando llegue el pre-registro, la pregunta legítima de cualquier escéptico —incluidos
nosotros mismos dentro de unos meses— será: *¿cuántas veces tocaron el mundo hasta que
dio el resultado que querían?*

La única defensa posible es un registro fechado de cada modificación, su razón y la
evidencia que la motivó, escrito **antes** de que exista el pre-registro. Sin eso, el
pre-registro es decorativo: nada impide haber ajustado el mundo hasta que el resultado
saliera bonito y presentar solo la última configuración.

El contenido más valioso de cada entrada no es la lista de arreglos. Es la sección
**"Qué NO se cambió"**: una negativa documentada con el dato que la respalda vale más
que todos los ajustes juntos.

**Estado actual: el pre-registro NO está congelado.** Todas las rondas hasta ahora son
de desarrollo y sus datos están marcados `desarrollo_no_confirmatorio`. Ninguna sostiene
ninguna afirmación.

---

## Ronda 0 — Piloto de desarrollo

**Fecha:** 2026-08-12
**Estado de los datos:** `desarrollo_no_confirmatorio`
**Motor:** commit `5817680` · **Análisis:** `6e9e1a8` · **Spec vigente entonces:** v1.0 (`7400606`)

### Pregunta que debía responder

Estimar la varianza entre mundos para poder calcular cuántas seeds necesita la corrida
confirmatoria. En segundo plano: verificar que el andamiaje completo —mundo, agentes,
probes, red de detección— funciona de punta a punta.

### Configuración

| Parámetro | Valor |
|---|---|
| Condiciones | 4 (sin_memoria / memoria / oráculo / baseline_empírico) |
| Densidades | 12% / 7% / 4% |
| Seeds | 8 → **96 mundos** |
| Días | 30 (720 ticks) |
| Modelo | qwen2.5:7b local |
| Costo | $0 |
| Intercalado | Sí — condición rotada en cada mundo, orden por seed |

### Resultados crudos

| Condición | Eventos | Rechazo | Fallo dominante | Acciones exitosas |
|---|---|---|---|---|
| sin_memoria | 6.117 | 96% | `gather not_adjacent` (5.243) | gather 229, move 37, **consume 0** |
| memoria | 11.144 | 91% | `gather not_adjacent` (8.554) | gather 647, move 369, **consume 6** |
| oráculo | 2.192 | 45% | `move blocked` (764) | **solo move (1.202)** |
| baseline empírico | 52.032 | 51% | `move blocked` (16.322) | gather 11.081, consume 4.931, build 100 |

- Supervivientes LLM: **0** en las 9 combinaciones (3 condiciones × 3 densidades).
- Baseline empírico: sobrevive; acierta 46–64% en celdas vividas, **0/41 en la celda retenida**.
- Agentes sub-expuestos: **92%** (37/40), con **cero consumos en B-clara**.
- Red de detección de held-out: **0 activaciones** — ningún consumo en B-oscura.
- Fugas semánticas en los datos: **0**.

### Qué midió realmente

**No midió composición. Midió el contrato entre el agente y el motor.** Sin supervivientes
LLM no hubo probes que analizar, así que la métrica primaria (LE) quedó sin calcular.

### Qué se cambió, y con qué evidencia

| Cambio | Evidencia que lo motivó |
|---|---|
| **D-026** — Acciones disponibles en la observación, con argumentos ya rellenados | 91–96% de rechazos en las condiciones LLM. Los agentes recolectaban (647 veces) y morían de hambre con el inventario lleno: `consume` exitoso 0 y 6. Rechazos con `consume() missing 'rkind'` confirman que el fallo era formular la acción, no elegirla |
| **D-023** — Nacimiento repartido entre regiones | 92% sub-expuestos con cero consumos en B-clara. Causa de fondo: trampa de explotación — la política descubre que S2 es malo (lo es, en A) y deja de probarlo, pero S2 solo revela su valor en B. Más días no lo arreglan |
| **D-022** — Requisito de discriminación de niveles + valores recalibrados | Al cruzar los valores del spec con los umbrales del probe, 3 de los 4 símbolos tenían la celda retenida en el mismo nivel de magnitud que una celda vivida. Solo S2 exigía componer; en el resto, memorizar bastaba |
| **D-024** — Probe de salida al iniciar la inanición | Los agentes morían sin dejar registro de su estado de conocimiento final |
| **D-025** — Corte de exposición (≥3 consumos por celda) | El 0/41 del baseline en la celda retenida está *por debajo* del azar (~17% esperado). No prueba que B-oscura sea incomponible: el agente nunca vivió B y respondía desde la única región que conocía |

### Qué NO se cambió, y por qué

**El mundo no se tocó.** La recomendación inicial tras el piloto fue suavizarlo —más energía
inicial, consumo más barato— para que los agentes LLM sobrevivieran. Se rechazó.

La razón está en la última fila de la tabla: **el baseline empírico sobrevive en ese mismo
mundo**, con 11.081 recolecciones, 4.931 consumos y 100 estructuras construidas. Si una
política greedy de tres parámetros vive ahí, el mundo es habitable; lo que no funciona es el
agente LLM.

Suavizar el metabolismo no habría arreglado nada —los agentes seguirían sin poder formular
`consume`, solo tardarían más en morir— y habría significado ajustar la configuración del
mundo hasta obtener el resultado deseado. Eso es exactamente el "jardín de senderos que se
bifurcan" que el protocolo se comprometió a evitar.

**Tampoco se cambió:** la estructura de efectos separables, la mecánica del held-out, el
alfabeto simbólico, las utilidades idénticas de los agentes, ni la definición de la métrica
primaria.

### Pendiente sin resolver

**El oráculo colapsó de una forma distinta al resto: solo caminó.** Cero `gather`, cero
`consume`, 1.202 `move`, y una cuarta parte de los eventos de las otras condiciones.

Es el agente con más información del experimento y el que menos hizo. Importa porque el
oráculo es el techo de la métrica primaria: si no funciona, LE no tiene denominador.
Sospecha a verificar: el prompt que carga la tabla completa de efectos satura a un modelo
de 7B. Se comprueba comparando longitud de prompt y tasa de JSON malformado entre
condiciones.

**Observación secundaria:** el baseline gasta el 31% de sus acciones chocando
(`move blocked`, 16.322 veces). No le impide sobrevivir, pero conviene revisar si las 100
`struct_a` construidas están tapando celdas de paso.

### Qué pregunta responde la ronda 1

¿Sobreviven y cruzan? Es decir: con el menú de acciones disponibles y el nacimiento
repartido, ¿los agentes LLM llegan vivos al final y acumulan experiencia en ambas regiones?

Hasta que la respuesta sea sí, no tiene sentido barrer densidades ni hablar de composición.
Por eso la ronda 1 corre a densidad única (7%) — el barrido vuelve cuando haya agentes que
midan.

### Lección de la ronda

El piloto costó $0 y encontró cuatro defectos —tres de ellos en el diseño, no en el código—
cuando todavía no existía ningún pre-registro que los congelara. Si hubieran aparecido
después de la corrida confirmatoria, el gasto habría servido para medir la habilidad de
qwen2.5:7b para escribir JSON.

---

## Instrumentación — visor reconstruido (2026-08-13)

Antes de gastar la ronda 1 se rehízo `viewer.html` (D-028). No es cosmética: el visor
anterior escondía los intentos rechazados por defecto y presentaba como medido lo que
él mismo derivaba (fase, barrera). Con esa superficie, la corrida del piloto —91-96%
de rechazos— se leía como sana. Además, el resultado del experimento (`_probes.jsonl`)
y la decisión del modelo (`_traces.jsonl`) existían en disco sin que nada los abriera.

Ahora: fallos visibles por defecto, anunciadores verde (medido) vs ámbar (derivado),
cuadrante 2x2 de exposición región × fase con la retenida rayada, y el exit probe como
calibración predicho-vs-motor. El instrumento que va a auditar la ronda 1 ya no puede
producir la conclusión falsa.

---

## Hallazgo que afecta a la ronda 0 (2026-08-13, posterior al cierre)

**El motor congelaba a los agentes que elegían su horizonte de despertar.**
`next_think = world.tick + horizonte`, contra un `world.tick` que se reinicia a 0
cada día. Todo horizonte que cruzara la medianoche daba un valor inalcanzable: el
agente no volvía a decidir **nunca**, salvo que su energía cayera bajo 15 —
moribundo. Fix en `ai/simulate.py` (reloj absoluto) + test permanente.

Qué implica para lo ya registrado, sin adornos:

- La asimetría **"el baseline sobrevive y los LLM no"** tiene una causa mecánica.
  `EmpiricalAgent` no devuelve horizonte, así que nunca se congelaba. Comparábamos
  un agente que actuaba 1.440 veces contra agentes congelados.
- **"El oráculo solo caminó"** (1.202 `move`, 0 `consume`) es el síntoma exacto de
  un agente que decide una vez, se duerme para siempre y despierta moribundo.
- El diagnóstico **"el 7B no traduce la tabla en planificación espacial"** se apoya
  en corridas donde el agente no tuvo turnos. No es falsable con esos datos —
  puede ser cierto, pero está sin medir.

Los 96 mundos del piloto y los dos smokes siguen siendo válidos como validación de
andamiaje. **Ninguna conclusión sobre supervivencia o composición de las
condiciones LLM sobrevive a este hallazgo.** Se re-mide con el motor arreglado.

Cómo se encontró: no por leer el código, sino por contrastar el presupuesto físico
(1.440 ticks × 0,3 de metabolismo ⇒ ~83 acciones mínimas para no morir) contra las
acciones observadas (68 entre 5 agentes). La brecha no la explicaba ninguna
hipótesis sobre el modelo.

---

## Tercer bug de instrumento — la región no es observable a distancia (2026-08-13)

**El oráculo recibe la tabla indexada por una variable que no puede localizar.**
Las reglas le dicen qué vale cada símbolo en (región, fase); su observación reporta
`region` **solo de la celda donde está parado**. `visible_to` (radio 6) devuelve
`dx, dy, rkind` sin etiqueta de región, y la frontera —`x >= int(width*region_split)`—
no aparece ni en el prompt ni en la observación. Como el oráculo corre con
`memory=None`, cada decisión es una llamada sin estado: **desde una sola observación
no existe función que lleve de `position` a "B queda al este"**. No es que el agente
no use el conocimiento; es que el conocimiento está indexado por algo que no puede ver.

Evidencia en `data/silver/gate_oraculo_ds` (deepseek-chat, 30d, seed42, d=7%):

- **3 de 5 agentes nacen en B** (a2 x=18, a3 x=21, a4 x=23) — D-023 funcionando.
- La primera fase oscura (día 1, tick 12) los expulsa a x=13-14 — D-017 funcionando.
- **Nunca vuelven.** Un solo cruce de frontera en toda la corrida (a2, día 2,
  x=14→15, reexpulsado). Después derivan al oeste hasta congelarse: a3 21→14→13→12→11→10,
  a4 23→13→12→11→10.
- Direcciones de `move`: (0,−1)×44, (0,1)×34, (−1,0)×13, **(1,0)×5** — se alejan de B
  2,6× más de lo que se acercan, estando a **un paso**. Los 69 consumos: 100% en A.

Qué implica para lo ya registrado, sin adornos:

- La lectura **"posee la tabla pero no la usa para controlar su política"** no está
  sostenida por estos datos. El "4/61 snapshots en B" no es *no cruza a B*: es
  **fue expulsado de B y no tiene con qué volver**.
- El diagnóstico **"el mundo es inviable para un agente LLM que decide vía llamadas
  discretas"** se apoya en corridas donde la región de destino era inobservable. Puede
  ser cierto, pero está sin medir — igual que pasó con el reloj.
- Es el **tercer** defecto de instrumento (reloj, orden fijo del menú, región), y los
  tres se disfrazaron de límite del modelo. El patrón ya es la lección: antes de
  aceptar un "el modelo no puede", verificar que la información necesaria esté en la
  observación.

**Qué NO se cambió.** No se cambió de modelo (el oráculo sigue siendo `qwen2.5:7b`:
cambiarlo rompe la comparabilidad, que es lo único que el diseño mide). No se
suavizó el mundo — densidades, efectos, barrera y metabolismo intactos. No se
rediseñó el protocolo: los dos gates propuestos por Terra (cognitivo + política)
quedan en espera, no descartados, hasta tener el gate re-corrido sobre instrumento
limpio. No se abrió ronda 1.

Cómo se encontró: no por leer el resumen del gate, sino por reconstruir las
trayectorias por snapshot desde el log crudo y notar que los agentes **empezaban**
en B. La pregunta "¿por qué no cruza?" era la pregunta equivocada; la correcta era
"¿cómo salió de ahí?". Instrumento: `ai/probe_observability.py` (D-029) replaya
observaciones reales del trace y separa lectura, recuperación de tabla y rumbo.

---

## El oráculo no podía leer su propia tabla (2026-08-13)

Al auditar el probe de observabilidad apareció un cuarto defecto, de otra
familia que los tres de instrumento: **`qwen2.5:7b` no recupera la regla que
recibe textual en el prompt**. Medido sobre las 16 celdas del mundo con
`ai/bench_oraculo.py`, marca 0.50 de acierto por nivel contra un azar de
referencia de **0.375** — la estrategia trivial de contestar siempre el nivel
modal. El techo informado estaba, en la práctica, en el azar.

El corte por dimensión es lo que importa: liga símbolo y región, y **colapsa
la fase**. Con la tabla escrita una celda por línea verbaliza *"en región A
durante fase 1 (oscura)"* y acto seguido emite el valor de la fase 0. Nombra
la celda correcta en palabras y copia la fila equivocada.

Qué implica para lo ya registrado, sin adornos:

- La fase es una de las dos dimensiones de D-014, y el probe de composición
  (D-005/D-010) pregunta por B-oscura, que exige componer región Y fase. Un
  0% de `qwen2.5:7b` en la celda retenida **no es interpretable**: no se
  distingue "no compuso" de "no puede indexar por fase".
- Eso no afecta solo al brazo oráculo. Contamina la **métrica primaria en las
  cuatro condiciones**, porque las otras tres tienen que inferir lo que el
  oráculo ni siquiera logra copiar.
- Se suma un defecto propio del andamiaje: `{"energy_change": +1}` es JSON
  inválido, y le pedíamos al modelo "el número con signo". El que obedecía
  quedaba registrado como `null`, indistinguible de no haber contestado. Los
  probes en disco tienen 15-25% de nulos en las corridas de oráculo qwen.
  Arreglado y con test permanente; los crudos de esas corridas no se
  guardaban, así que esa fracción no es recuperable.

**Qué NO se cambió.** No se tocó el mundo: densidades, efectos, barrera,
metabolismo y ontología siguen intactos. No se aflojó el probe ni se cambió
la métrica. La tabla plana **no agrega información** — son los mismos 16
hechos de ORACLE_RULES sin indexación posicional, con test permanente que
falla si algún día se le cuela un hecho que la tabla actual no tenga. No se
abrió ronda 1.

Cómo se encontró: no por sospechar del modelo, sino porque el control pareado
del probe separó dos fallos que el promedio confundía — DeepSeek recupera la
tabla perfecto y aun así no sabe dónde queda B; qwen ni siquiera llega a esa
pregunta. Instrumento: `ai/bench_oraculo.py` (D-030), con el desagregado por
región, por fase y por celda retenida, porque el promedio escondía el
hallazgo (6/12 tapando 6/6 y 0/6).

---

## Elegimos un modelo con medio criterio (2026-08-14)

D-030 eligió `gemma2:9b` porque marcaba 1.0 en el banco de las 16 celdas. El
banco medía **un solo brazo**. Hay dos, y no ordenan igual:

- **estático** — región y fase en el TEXTO de la pregunta. Es la condición de
  `predict_effect` (D-010), la métrica primaria.
- **contextual** — región y fase solo en la observación. Es la condición del
  BUCLE DE ACCIÓN, donde el agente efectivamente vive.

`gemma2:9b` da 1.0 en el primero y **0.083** en el segundo. Cita la etiqueta de
una celda con el valor de otra dos filas abajo ("región A … fase 0 (clara):
+7", línea que no existe en su prompt). Y se confirmó en conducta antes de
gastar el gate: su smoke dio **0 consumos, 20 moves, 17 de ellos al oeste**.

**El smoke de 5 días no detectó nada, y esa es la lección.** Marcó 5/5
supervivientes: con ~100 de energía inicial y 0.3 por tick, a 5 días todavía no
hacía falta comer. Un criterio de supervivencia corto no distingue "funciona"
de "todavía no se murió". Los smokes de validación tienen que mirar conducta
(consumos, cruces, direcciones), no el contador de vivos.

Qué implica para lo ya registrado:

- Se descartaron modelos por un artefacto nuestro. `qwen3:4b` se rechazó el
  13/08 porque "con `max_tokens` bajo el `content` queda vacío" — eso era el
  tope que poníamos nosotros, no el modelo. Con presupuesto suficiente marca
  1.0 en los dos brazos. (Queda fuera igual: 77,5 s por decisión.)
- El mismo artefacto dio un Q3 = 0/3 falso a `deepseek-v4-flash`.
- `q3_heading_acc` se calculaba sobre 12 muestras cuando solo 3 eran
  contestables: tras D-029 las entidades visibles traen región, pero el radio
  de visión es 6 y en 9 de 12 no había ninguna entidad de la otra región a la
  vista. Se puntuaban como fallos preguntas imposibles — el error que ese
  probe existe para no cometer.

**Qué NO se cambió.** El mundo sigue intacto: densidades, efectos, barrera,
metabolismo, ontología. No se tocó el probe de composición ni la métrica
primaria. No se abrió ronda 1. Y NO se aflojó el criterio para que entrara un
modelo: se agregó un brazo, que es lo contrario.

Cómo se encontró: porque Zod paró en vez de correr el gate con un q2 malo, y
porque el probe guardaba las respuestas crudas — sin el crudo, "0.083" era
indistinguible de un fallo de parser y habríamos reformulado la pregunta hasta
que el número subiera.

---

## Gate `gate_oraculo4` — 0/5, pero la causa quedó aislada (2026-08-14)

Primer gate con el instrumento limpio: región etiquetada en cada entidad
visible (D-029), tabla del oráculo plana y generada del motor (D-030),
`deepseek-v4-flash` sin razonamiento (D-031), más la línea de contexto y el fix
del JSON con `+1`. Mismo seed, misma densidad y —esto importa— **el mismo
modelo** que la corrida del 13/08: `deepseek-chat` era v4-flash en modo no
pensante. O sea que la comparación aísla el instrumento.

**Resultado: 0/5. El gate no pasa. Ronda 1 sigue bloqueada y no se creó
`docs/gates/ronda1.gate`.**

| | `gate_oraculo_ds` (13/08) | `gate4` (14/08) |
|---|---|---|
| supervivientes | 0/5 | 0/5 |
| días de muerte | todos ~12 | 12, 14, 15, 15, **27** |
| consumos | 69 | **131** |
| comidas negativas | 28 (41%) | 41 (**31%**) |
| **energía neta de comer** | **−86** | **+86** |
| acciones ok | 251 | 411 |
| **cruces de frontera** | **1** | **1** |
| presencia en B | 6,6% | 2,4% |
| S2 en B intacta al final | sí | **sí, 8 celdas** |

Lo que dice el contraste, sin adornos: **los arreglos funcionaron en comer y no
movieron nada en llegar a B.** El agente dejó de envenenarse —la energía neta
de la comida pasó de −86 a +86— y el mejor sobrevivió hasta el día 27 en lugar
del 12. Pero cruzó la frontera **una sola vez en 30 días**, exactamente igual
que antes, y las 8 celdas de S2 en B, que valen +7 y +10, quedaron intactas
otra vez.

Eso deja un único sospechoso, y ya estaba medido antes de correr el gate: la
frontera solo es deducible dentro del radio de visión 6. El probe da rumbo
**3/3 donde hay una entidad de B a la vista y 0/9 donde no la hay** — un agente
que usa la información cuando existe y no la inventa cuando no. Propuesta en
D-032 (frontera en las reglas del oráculo).

**Qué NO se cambió.** El mundo sigue intacto: densidades, efectos, barrera,
metabolismo, ontología, radio de visión. No se tocó el probe ni la métrica
primaria. No se bajó el umbral del gate para dejarlo pasar — 0/5 contra un
umbral de 3/5 no admite lectura optimista. No se abrió ronda 1.

Costo: 1,33 M tokens, **US$0,03**. La corrida completa de ronda 1 (24 mundos)
extrapola a US$0,69 a precios de hoy y US$1,24 en valle desde el 16/08.

---

## Gate `gate_oraculo5` — el primer hallazgo que NO es un bug de instrumento (2026-08-14)

Con la geometría común de D-032 aplicada y verificada en el prompt de la
corrida (`- El mundo mide 30x30. La región A es la mitad OESTE (x < 15)…`) y
las etiquetas de región presentes en las observaciones (10/10 entidades).

**Resultado: 0/5, y CERO cruces de frontera** — uno menos que sin geometría.
Decirle al agente dónde está B no lo hizo ir a B. Ese es el tercer brazo del
criterio pre-registrado en D-032, y obliga a mirar el porqué en vez de seguir
arreglando el andamiaje.

### Hallazgo 1 — el agente tiene razón: A domina a B

Se le preguntó directamente, sobre observaciones reales de la corrida
(gate de política de Terra, 10 muestras con hambre): **dice que NO hay que ir
a B, 10 de 10 veces**, y su razón es correcta:

| | A-clara | A-oscura | B-clara | B-oscura |
|---|---|---|---|---|
| S1 | **+8** | **+4** | −1 | −5 |
| S2 | −2 | +1 | **+7** | +10 |
| S4 | +1 | −8 | **+7** | −2 |

Quedarse en A rinde **+8 en clara y +4 en oscura, con S1, en AMBAS fases**. Ir
a B rinde +7 y **solo en fase clara**, porque B-oscura está bloqueada por la
barrera (D-017). **A domina a B: no cruzar es la política correcta.** El
agente cita la barrera y los valores de la tabla textualmente.

Consecuencia de diseño, no de agente: el probe de composición exige haber
vivido B-clara, y la estructura de pagos del propio mundo hace irracional
visitarla. **D-023 (nacer repartido) empuja hacia B, D-017 expulsa, y la
ontología quita toda razón de volver.** Por eso ni la política reactiva
optimizada llega al 3,3% de consumos en B-clara: no es miopía suya, es que B
no paga.

### Hallazgo 2 — explotación miope con conocimiento y percepción perfectos

Lo que sí es un fallo del agente, y está limpio de instrumento:

- **Comió S2 68 veces y S1 CERO veces** (gate4: 101 S2 contra 18 S1).
- S2 en A-clara vale **−2**. S1 en A-clara vale **+8**.
- En esas mismas observaciones **S1 estaba VISIBLE a 5 pasos**, con S2
  adyacente a 0-1 pasos.
- El agente **dice** que S1 vale +8 y que hay S1 cerca. Y come el S2 de al lado.

No es falta de conocimiento (tiene la tabla y la recita), ni de percepción (ve
el S1), ni de comida: hay **80 unidades de S1 en A = 640 de energía**, contra
un déficit metabólico de **116** en 30 días. El mundo es holgadamente
sobrevivible quedándose quieto en A y caminando cinco pasos.

El fallo es **no ejecutar navegación de varios pasos hacia una recompensa
mejor conocida y visible**: consume lo adyacente aunque sepa que le resta
energía. Esto es control de política bajo conocimiento perfecto — el hallazgo
cognitivo genuino que el criterio pre-registrado anticipaba como tercer brazo.

**Límite de la evidencia, declarado**: 1 mundo, 1 seed, 5 agentes. Sostiene la
descripción del mecanismo, NO una tasa poblacional. Antes de reportarlo hay
que replicar sobre varias seeds — cuesta US$0,03 por mundo.

### CORRECCIÓN (mismo día): el hallazgo 2 NO se sostiene

La réplica sobre seeds 7/13/21 y la matriz contrafactual que exigió Terra lo
refutaron. Se deja escrito el hallazgo original arriba, sin editar, porque el
error importa más que la conclusión.

**Réplica, 4 seeds:**

| seed | superv. | S1 (+8) | S2 (−2) | neto | cruces | B-clara |
|---|---|---|---|---|---|---|
| 42 | 0/5 | **0** | **68** | −19 | 0 | 0 |
| 13 | 2/5 | **119** | 0 | +612 | 0 | 0 |
| 21 | 2/5 | 71 | 42 | +295 | 1 | 1 |
| 7 | 2/5 | 57 | 14 | +241 | 1 | 0 |

Fuera de la seed 42, el agente come el recurso BUENO 247 veces contra 56 el
malo. **La "miopía" era un artefacto de la seed 42**, donde el spawn dejó a
los agentes lejos de los cúmulos de S1. Habíamos gateado cuatro rondas sobre
una única seed, y resultó ser una tirada patológica.

**Matriz contrafactual** (estados construidos con el motor real, el menú de
acciones sale de `available_actions`, 6 posiciones por escenario):

| escenario | elige S1 (+8) | elige S2 (−2) |
|---|---|---|
| A · ambos en inventario | **6/6** | 0/6 |
| B · ambos adyacentes | **6/6** | 0/6 |
| C · el bueno a 5 pasos | 0/6 | **6/6** |

Disociación limpia: **la selección es perfecta (12/12) y la planificación
falla (0/6)**. Por el criterio que Terra fijó antes de correrla —"falla solo
en C ⇒ es horizonte/costo de planificación y NO es reportable como fallo de
política"— el hallazgo 2 queda **refutado como fallo de control de política**.
Lo que sí queda establecido, y es más estrecho: el agente no emprende
navegación de varios pasos hacia una recompensa mejor que ve y sabe valorar.

**Supervivencia real: 0, 2, 2, 2 de 5.** No es el 0/5 uniforme que creíamos.
Ningún mundo alcanza el umbral de 3/5, así que el gate sigue sin pasar, pero
el techo informado no está colapsado: está a un agente de distancia.

**Lección metodológica**: gatear sobre una sola seed produjo cuatro rondas de
diagnóstico sobre una tirada atípica. Los gates futuros corren ≥3 seeds antes
de concluir nada.

**Qué NO se cambió.** El mundo sigue intacto. No se tocó la ontología para que
B "pagara mejor" — eso contaminaría la interpretación y es exactamente lo que
la bitácora existe para impedir. No se abrió ronda 1.

---

## Rediseñar la tabla NO alcanza (2026-08-14)

Implementado el gate de Terra (`ai/gate_mundo.py`) con sus umbrales, sobre 12
seeds fijas y sin LLM. La tabla actual falla los tres:

| gate | resultado | umbral |
|---|---|---|
| 1 · viabilidad | longevidad 0,746 · **0/12** seeds con 4/5 | ≥0,80 · ≥9/12 |
| 2 · exposición | **3,3%** de trayectorias con D-025 | ≥75% |
| 3 · B importa | Δlongevidad 0,056 | ≥0,20 |

El gate 2 devuelve exactamente el 3,3% que Terra citó del piloto: el
instrumento calibra contra un dato conocido de antemano.

**Hallazgo del gate 1, nuevo** (redactado con la precisión que exigió Terra):
*el baseline determinista informado, dentro de la familia y los parámetros
evaluados, no acredita viabilidad robusta bajo el gate pre-registrado* — cero
seeds de doce alcanzan 4/5 supervivientes. Eso **no** demuestra que el mundo
sea duro para cualquier política: sin un planificador óptimo no corresponde
llamarle "techo" ni atribuir el fallo al mundo en general. Lo que sí invalida
es el uso de ese agente como techo/denominador de LE **de supervivencia**.

**Búsqueda de tabla: 400 candidatas evaluadas, ninguna pasa.** Con δ_región y
δ_fase variados y todas las invariantes intactas (separabilidad, D-022,
B-oscura bloqueada, S3 control), la mejor fracción D-025 alcanzada es **0,08
contra un umbral de 0,75** — un factor de diez. El alcance del resultado, otra
vez con la precisión de Terra: **ninguna de las 400 candidatas evaluadas, bajo
ESTA dinámica y ESTA familia de política, alcanza el umbral.** Es evidencia
suficiente para detener el tuning de tabla; no es una imposibilidad matemática
universal. Se descartó el confound obvio: ampliar el radio de planificación de
la política informada (5 → 10 → 20) no mejora la exposición y empeora la
longevidad, así que el cuello no es la miopía del baseline.

**Dónde se rompe, medido.** Patrón de exposición sobre 60 trayectorias
(12 seeds × 5 agentes) con la mejor candidata:

| trayectorias | celdas con al menos un consumo |
|---|---|
| **38** | A-clara + A-oscura (**nunca B-clara**) |
| 7 | solo A-clara |
| 7 | ninguna |
| **3** | **las tres (D-025 completo)** |
| 5 | otras combinaciones |

38 de 60 se asientan en A y no visitan B ni una vez, aun con B-clara pagando
+10 contra +8 de A-clara. El problema no está en cuánto paga B: está en la
dinámica que lleva a los agentes a asentarse en A —spawn, expulsión por
barrera y re-asentamiento— y ninguna tabla de pagos la corrige.

**Consecuencia:** se cumple la condición que el propio Terra puso para
reabrir D-023/D-017 ("solo si tras la geometría común sigue sin haber
exposición a B-clara"). La decisión vuelve a él con evidencia, no con
conjetura.

**Qué NO se cambió.** No se tocó la ontología: la búsqueda evalúa candidatas,
no las adopta. No se aflojó ningún umbral del gate — están congelados en un
test. No se abrió ronda 1.

---

## El probe nunca llevó la manipulación experimental (2026-08-14)

**Quinto bug de instrumento, y el único que cae sobre la métrica primaria.**

`predict_effect` —el probe de composición, D-010— construía un prompt desnudo:
sin `system_rules` y sin `memory`. Capturados los mensajes, las tres
condiciones LLM recibían textos **byte-idénticos**: 118 caracteres de system y
221 de user. El oráculo nunca tuvo su tabla al responder el probe. `memoria`
nunca tuvo sus recuerdos.

Es decir: **el probe de composición nunca pudo distinguir las condiciones.**
Todo resultado de composición anterior mide lo mismo — un modelo desnudo
adivinando. No es que las condiciones rindieran parecido: es que eran la misma
condición en el instante en que se las medía.

Y habría vuelto inútil la Fase E recién aprobada: entregar experiencias a mano
a una memoria que después nadie lee.

Corregido: el probe lleva ahora exactamente lo que define a cada condición —
el oráculo su tabla, `memoria` su registro literal (región, fase, recurso,
`energy_gain`), `sin_memoria` nada. No se agregó mecánica ni geometría: la
pregunta ya nombra símbolo, región y fase. Siete tests fijan que los tres
prompts sean distintos, que cada condición reciba lo suyo y solo lo suyo, y
que el valor de B-oscura no se filtre a quien no lo tiene por su condición.

### Smoke del protocolo D-033 (Fase E + Fase P)

Primera corrida con el instrumento reparado. **3 agentes por condición, 9
probes retenidos por condición: es un smoke de instrumento, NO un resultado.**

| condición | celdas vividas | celda RETENIDA (B-oscura) |
|---|---|---|
| oráculo | **27/27 = 1,00** | **9/9 = 1,00** |
| memoria | 14/27 = 0,52 | 0/9 = 0,00 |
| sin_memoria | 2/27 = 0,07 | 3/9 = 0,33 |

(azar por nivel de magnitud ≈ 1/6 = 0,17)

Lo que este smoke establece —y es lo único que establece— es que **el
instrumento discrimina**. Las tres condiciones se separan limpiamente en las
celdas vividas: 1,00 / 0,52 / 0,07. Eso nunca había ocurrido en el proyecto.

Lo que NO establece: nada sobre composición. Con 9 probes retenidos por
condición, el 0,00 de `memoria` y el 0,33 de `sin_memoria` son indistinguibles
del azar. La diferencia entre ambos tiene el signo contrario al esperado, lo
que a este n es exactamente lo que el ruido produce.

Dato que sí merece seguimiento: `memoria` acierta solo 0,52 en celdas que
acaba de vivir y que tiene **escritas literalmente en su prompt**. Recuperar
un `(símbolo, región, fase)` de una lista de 27 entradas es una tarea de
lectura, no de memoria — y es el mismo patrón de fallo de indexación que
qwen2.5:7b mostró con la tabla del oráculo. Si se confirma, el techo de
`memoria` estaría limitado por lectura y no por retención.

**Qué NO se cambió.** La ontología sigue congelada. D-023 y D-017 intactas. No
se tocó la definición del probe ni la métrica de magnitud (D-010). La Fase E
no expone B-oscura y `no_heldout_consumption()` sigue limpio.

---

## Gate de lectura: la memoria literal no es operativamente accesible (2026-08-14)

Terra fijó los umbrales antes de ver datos —**≥0,75 agregado y ≥0,60 en cada
celda vivida**— y el criterio: si una representación de memoria no pasa
recuperación de información **vivida**, no se corre ni se interpreta el probe
retenido para esa representación.

Resultado con `gemma2:9b`, 10 agentes, **90 preguntas** sobre celdas vividas:

| representación | agregado | A-clara | A-oscura | B-clara | |
|---|---|---|---|---|---|
| `memoria_literal` | **0,567** | 0,500 | 0,367 | 0,833 | **NO PASA** |
| `memoria_indexada` | **0,778** | 0,667 | 0,667 | 1,000 | **pasa** |

Estable respecto de la corrida previa de 27 preguntas (0,52 y 0,78): las
estimaciones casi no se movieron al triplicar el n.

**Honestidad sobre el margen:** `memoria_indexada` pasa por punto estimado, no
con holgura. A n=90 el IC95% del agregado es ≈[0,69 – 0,86], cuyo extremo
inferior queda por debajo del umbral; las celdas en 0,667 tienen n=30 y su IC
baja de 0,60. El gate está formulado como criterio de punto y por punto pasa —
pero no debe leerse como "la lectura ya no es un problema".

**El resultado sobre la memoria literal es un hallazgo, no un fracaso**, y así
lo pidió Terra: *la memoria literal cruda no es operativamente accesible para
estos agentes*. El patrón por celda lo respalda — A-oscura 0,367 contra
B-clara 0,833, siendo B-clara lo más reciente del log cronológico. Es efecto de
recencia sobre una lista cruda: el cuello es indexación/lectura, no retención.

`memoria_literal` queda como **ablación reportable**, no como condición central
de composición.

**Qué NO se cambió.** `memoria_indexada` contiene exclusivamente experiencias
propias observadas, agrupadas; no promedia (esa aritmética la sigue haciendo el
agente) y no filtra B-oscura, donde el agente nunca estuvo. No se excluyó
ningún mundo por fallar lectura: excluir selectivamente sesga el estimando, y
el gate evalúa la representación, no los casos.

---

## El piloto de potencia falló, y el motivo era el diseño (2026-08-14)

Para congelar N hacía falta σ_Δ, la desviación de las diferencias pareadas
`memoria_indexada − sin_memoria` por seed. El piloto de 8 seeds devolvió
**σ_Δ = 0,0 EXACTO**: los ocho dieron valores idénticos (0,000 contra 0,333,
diferencia −0,333 en todos).

Causa verificada, no supuesta: **una sola huella de memoria en 4 seeds**
comprobados. La Fase E entrega las mismas 9 celdas con los mismos valores en
todo seed —porque los efectos del mundo son deterministas (D-009/D-015) y la
exposición está estandarizada por construcción— y con `temperature=0` el
prompt idéntico produce la respuesta idéntica.

**Ocho seeds no eran ocho observaciones: eran ocho ejecuciones del mismo
ítem.** El seed dejó de ser fuente de varianza para el probe de composición, y
eso es una consecuencia directa de D-033 que ni Terra ni yo anticipamos al
escribirla: estandarizar la exposición era el punto de la Fase E, y su precio
es eliminar la variabilidad entre mundos.

**Fallo silencioso propio, corregido.** Con σ=0 mi `n_requerido` devolvía 16
—el piso— como si fuera una respuesta válida. Habríamos corrido 16 seeds
creyendo tener potencia 0,90 sobre un diseño sin varianza. Ahora marca
`degenerado`, devuelve `None` y explica el motivo, con test que lo fija.

**Observación sin valor estadístico:** `memoria_indexada` 0/3 contra
`sin_memoria` 1/3 en la celda retenida, replicado 8 veces con varianza cero.
Son ocho copias de una observación, **n efectivo = 1**. Llama la atención que
la memoria vaya en contra —coincide con el smoke previo (0,00 vs 0,33)— pero
no se reporta como resultado.

**Salida (D-034, Terra):** mantener la Fase E estandarizada y hacer variar la
ONTOLOGÍA. Banco de 32 tablas separables congelado en disco antes de cualquier
llamada a un modelo. La unidad inferencial vuelve a ser legítima sin fabricar
ruido subiendo `temperature`.

**Qué NO se cambió.** No se fijó N con los 8 seeds degenerados. No se subió
`temperature` para inventar varianza. La ontología de `ecologia-v1` sigue
congelada.

---

## El cuello es ligar la FASE, no la memoria (2026-08-14)

El gate de lectura falló sobre el banco de 32 ontologías, y al perseguir el
porqué apareció el mecanismo — el hallazgo más concreto de la sesión.

### El gate falla, y la medición de una sola tabla era optimista

| representación | agregado | A-clara | A-oscura | B-clara | |
|---|---|---|---|---|---|
| `memoria_indexada` | **0,663** | 0,521 | 0,490 | **0,979** | NO PASA |
| `memoria_literal` | 0,656 | 0,573 | 0,469 | 0,927 | NO PASA |

288 preguntas, 32 ontologías, `gemma2:9b`. Umbrales de Terra: ≥0,75 agregado y
≥0,60 por celda. **Ninguna representación pasa**, así que por D-034 la ronda de
composición NO se corre.

El 0,778 medido antes era sobre **una sola ontología** — la tabla congelada de
`ecologia-v1`. Sobre 32 cae a 0,663 y la ventaja de indexada sobre literal
**desaparece** (0,663 vs 0,656). Es el error de la seed 42 repetido: una
instancia única dio una estimación optimista. Esta vez el diseño lo detectó
antes de gastar la ronda.

### No es posición

`B-clara` se mantiene en ~1,0 con las filas del render en orden normal (0,958)
y en orden invertido (1,0). Descartado el artefacto de formato posicional. Los
niveles de magnitud del banco están repartidos en las tres celdas (25-30%
modal), así que tampoco se acierta por ser adivinable.

### El mecanismo: se liga la región, no la fase

Memorias de DOS celdas, 16 ontologías, solo S2:

| las dos celdas se distinguen por… | acierto |
|---|---|
| **REGIÓN** (misma fase) | **32/32 = 1,000** |
| **FASE** (misma región) | **21/32 = 0,656** |

Ligar la región es perfecto; ligar la fase, degradado. Eso explica el patrón
entero del gate: `B-clara` es la **única celda con región B**, recuperable con
una sola clave, y por eso da 0,98; `A-clara` y `A-oscura` comparten región y
exigen ligar **también** la fase, y por eso caen a ~0,50.

**Es el mismo fallo que abrió la sesión.** `qwen2.5:7b` con la tabla del
oráculo daba 6/6 en fase 0 y 0/6 en fase 1 — "liga símbolo y región, colapsa la
fase". Reaparece con otro modelo, otra representación y otra tarea.

**Por qué importa más allá de la memoria:** la fase es una de las dos
dimensiones de D-014, y el probe retenido exige componer región **y** fase. Si
la fase no se liga, un cero en B-oscura no mide fallo de composición: mide
fallo de binding. La distinción decide qué se puede afirmar.

**Qué NO se cambió.** No se corrió la ronda de composición. No se bajaron los
umbrales del gate. El banco sigue congelado y la ontología de `ecologia-v1`
intacta. `memoria_indexada` no se "arregló" para que pasara: se midió, falló, y
se reporta que falla.

---

## La fase como entero no se liga; en prosa sí (2026-08-14)

Continuación directa de lo anterior. Si el cuello era ligar la fase, quedaba
una asimetría sin justificar: **la tabla del oráculo ya escribía la fase en
prosa** desde D-030 —"durante fase 0 (clara)"— mientras la memoria la llevaba
como campo entero `"phase": 0`, porque `LiteralMemory` serializa el evento del
motor tal cual. Nadie decidió esa diferencia.

Medido sobre el banco, misma información, único cambio el render:

| render de la memoria | agregado | A-clara | A-oscura | B-clara | |
|---|---|---|---|---|---|
| JSON `"phase": 0` (32 ont.) | **0,663** | 0,521 | 0,490 | 0,979 | NO PASA |
| prosa `fase 0 (clara)` (32 ont.) | **0,962** | 0,979 | 0,990 | 0,917 | **PASA** |

A-oscura pasa de 0,490 a 0,990. **No es un límite del modelo: un entero suelto
en un campo JSON no se liga, y la misma fase en prosa sí.**

Consecuencia sobre lo ya registrado: la entrada anterior concluía que "se liga
la región, no la fase". Hay que leerla acotada — se liga la región **en
cualquier formato**, y la fase **solo cuando está en prosa**. El fallo de
binding es real pero es de representación, no de capacidad.

Y expone un confound que arrastrábamos sin verlo: **el oráculo leía prosa y la
memoria leía JSON**, y la diferencia entre condiciones incluía eso. No lo
decidió el diseño; salió de cómo serializa el motor.

**Pendiente de decisión, NO aplicado.** El cambio de render no se implementó:
Terra definió los constructos de memoria y fue explícito en que un cambio de
representación es un tratamiento declarado, no un arreglo silencioso. Queda a
su criterio.

**Y el patrón que hay que dejar visible:** llevamos tres representaciones
probadas —literal, indexada, indexada-en-prosa— y la tercera es la que pasa.
El argumento de consistencia con el oráculo es bueno, pero *"probamos hasta que
pasó"* es exactamente lo que esta bitácora existe para que se pueda auditar.
Queda escrito con esas palabras.

**Qué NO se cambió.** No se aplicó el render nuevo. No se corrió la ronda. Los
umbrales del gate siguen intactos, el banco congelado y `ecologia-v1` sin
tocar.

---

## Gate de lectura sobre el banco confirmatorio: PASA (2026-08-15)

Aplicado el orden completo que fijó Terra en D-035: renderer canónico en prosa
congelado, tests de transformación fiel, banco v2 con seed **20260815
pre-registrada** y **cero ontologías compartidas** con el v1, y recién entonces
el gate.

| banco | agregado | A-clara | A-oscura | B-clara | |
|---|---|---|---|---|---|
| **v2 (confirmatorio)** | **0,955** | 0,948 | **1,000** | 0,917 | **PASA** |
| v1 (calibración) | 0,962 | 0,979 | 0,990 | 0,917 | pasa |

288 preguntas, `gemma2:9b`, umbrales ≥0,75 agregado y ≥0,60 por celda.

**Lo que hace válido este número y no el anterior:** el v1 es el banco donde se
auditó el renderer, así que su 0,962 no puede avalar nada — quedó como
calibración del instrumento por decisión de Terra. El v2 es disjunto y su seed
se fijó antes de llamar a ningún modelo sobre él. Que el resultado replique
sobre tablas nuevas es lo que separa "la prosa funciona" de "la prosa se ajustó
a un banco".

A-oscura pasa de **0,490** (formato JSON) a **1,000**. Con la misma
información.

**Queda desbloqueada la Fase P**, por primera vez desde que empezó el
protocolo de composición. Corre sobre el banco v2, con el análisis
pre-registrado: permutación pareada sobre las 32 diferencias
`memoria_indexada − sin_memoria`, IC bootstrap remuestreando ontologías, y
`memoria_indexada_corrupta` como control de contenido fuera del contraste
primario. Referencia de azar del v2: **0,188** — la mejor estrategia constante,
no 1/6.

**Qué NO se cambió.** El banco v2 no se tocó tras generarlo. Los umbrales del
gate siguen siendo los pre-registrados. `ecologia-v1` sigue congelada. El
hallazgo de binding se reporta como calibración del instrumento, no como
resultado cognitivo.

---

## Ronda de composición (banco v2): la memoria interfiere, y sabemos por qué (2026-08-15)

Primera ronda de composición corrida con el instrumento completo. Corrida por
Zod; verificación del mecanismo por Opus. Banco v2 (32 ontologías, seed
pre-registrada, disjunto del de calibración), `gemma2:9b`, 576 probes por
condición, cobertura de exposición **192/192** en las tres.

### Resultado

| condición | correctos | proporción | sin_respuesta |
|---|---|---|---|
| `memoria_indexada` | 12/576 | **0,021** | 66 (11%) |
| `memoria_indexada_corrupta` | 49/576 | 0,085 | 223 (39%) |
| `sin_memoria` | 108/576 | **0,188** | 0 |

Contraste primario `memoria_indexada − sin_memoria`, pareado por ontología:
**−0,167**, permutación **p = 0,0004**, IC95% bootstrap **[−0,25 , −0,09]**.
Azar de referencia del banco: **0,188**.

`sin_memoria` cae clavado en el azar, como debe un control sin información.
`memoria_indexada` rinde **diez veces por debajo del azar**.

### El matiz de la no-respuesta NO explica el efecto

Zod marcó la asimetría (66 / 223 / 0 nulos) sin afirmarla. Condicionando a
haber respondido: `memoria_indexada` **0,024**, `corrupta` 0,139,
`sin_memoria` 0,188. El efecto **sobrevive** y sigue muy por debajo del azar.

### El mecanismo, medido

Rendir por debajo del azar es sistemático, no ruido. La causa:

| condición | repite un valor que vivió | acierto |
|---|---|---|
| `memoria_indexada` | **486/510 = 95,3%** | 0,024 |
| `corrupta` | 155/353 = 43,9% | 0,139 |
| `sin_memoria` | **0/576 = 0%** | 0,188 |

El gradiente de repetición mapea inverso sobre el acierto. Y **D-022 garantiza
que la celda retenida cae en un nivel de magnitud distinto al de las tres
vividas** — así que repetir un valor vivido es *necesariamente* incorrecto. De
ahí el rendimiento bajo el azar.

De qué celda copia, cuando copia:

- **82,4% de A-oscura** — la que comparte **fase** con la retenida
- 11,8% de B-clara — la que comparte **región**

Y lo decisivo: **la regla separable predice B-oscura exactamente en 510/510
casos**. La respuesta correcta era derivable de lo que tenía delante.

**Conclusión: no es que no pudiera componer. Recupera por una sola clave en
lugar de componer por dos.** Con conocimiento perfecto, accesible y verificado
legible (gate 0,955), el agente ancla en la dimensión que comparte con la celda
preguntada y devuelve ese valor.

### Alcance, declarado

Vale para `gemma2:9b`, `temperature=0`, esta familia de ontologías separables y
este formato de probe. No se afirma que los LLM no compongan: se afirma que
**bajo exposición dirigida, memoria accesible y respuesta verificable, este
agente recupera en vez de componer, y hacerlo lo lleva por debajo del azar**.
El diseño de la celda retenida (D-022) es lo que permite distinguir una cosa de
la otra — sin ese requisito, la repetición habría pasado por acierto parcial.

### Qué NO se cambió

Banco v2 intacto y seed sin regenerar. Renderer congelado. `temperature=0`.
Banco v1 sin reutilizar para inferencia. Ninguna ontología excluida. El
resultado salió **en contra de la hipótesis** y se reporta tal cual, como se
anticipó por escrito antes de correrlo.

---

## La réplica con un segundo modelo pasa los tres criterios (2026-08-15)

Corrida con los criterios de D-036 **escritos y commiteados antes** (`d39472b`).
`deepseek-v4-flash`, thinking desactivado, `temperature=0`, mismo banco v2,
mismo renderer, mismos prompts, sin excluir ontologías.

| criterio pre-registrado | umbral | gemma2:9b | deepseek-v4-flash |
|---|---|---|---|
| Δ(indexada − sin_memoria) | ≤ −0,10 | −0,167 | **−0,120** ✅ |
| permutación **unilateral** | p < 0,05 | — | **p = 0,0034** ✅ |
| repite un valor vivido | ≥ 70% | 95,3% | **73,8%** ✅ |
| brecha fase − región | ≥ 20 pts | ~70 pts | **33,3 pts** ✅ |

IC95% bootstrap sobre ontologías: **[−0,193 , −0,047]**, no cruza cero.

**El control cae en el mismo lugar con los dos modelos**: `sin_memoria` = 0,188
(gemma) y 0,177 (DeepSeek). Dos familias independientes coincidiendo en el
control es la mejor evidencia de que el banco está bien calibrado y de que el
efecto no viene del instrumento.

**Conclusión, con la redacción final que aprobó Terra** (afirma conducta
medida, no arquitectura mental interna):

> En dos modelos preespecificados —`gemma2:9b` y `deepseek-v4-flash`—, sobre un
> banco preregistrado de ontologías separables y bajo decodificación
> determinista, **la memoria indexada no mejora la exactitud en la celda
> retenida: la reduce frente a `sin_memoria`**. Las respuestas están dominadas
> por recuperación de valores vividos, con sesgo hacia la celda que comparte
> fase, en vez de la combinación región × fase requerida por la estructura
> generativa.

Alcance: **"replicado en dos familias de modelos"**. NO "los LLM hacen esto" —
para eso habría que predefinir un panel de tres o más modelos antes de mirar
los datos.

Matices que van con la afirmación, no aparte:
- La inferencia es sobre las **32 ontologías**, no sobre los probes.
- "Derivable" significa **derivable bajo la estructura separable que genera el
  banco**. Al agente no se le declara esa regla, así que la tarea mide
  **inducción de la estructura**, que es lo que se quiere medir.
- La referencia es el control `sin_memoria`, no un azar uniforme abstracto.
- "Por debajo del control" no es capacidad negativa general del modelo: es
  propiedad conjunta del banco, el criterio de scoring, la estrategia de
  recuperación y la garantía D-022. Sin D-022, copiar habría recibido crédito
  falso por composición.

Diferencia entre modelos que vale anotar: gemma repite en 95,3% de sus
respuestas y DeepSeek en 73,8%. DeepSeek recupera menos y aun así no compone —
su acierto (0,057) sigue muy por debajo de su propio control (0,177).

**Qué NO se cambió.** Los criterios se fijaron antes y no se movieron después
de ver el resultado. Banco intacto, renderer congelado, ninguna ontología
excluida, `temperature=0`, misma configuración que la corrida original.

---

## Estudio confirmatorio (banco v3): el efecto replica en tres modelos, el mecanismo no (2026-08-15)

Corrido con todo pre-registrado y commiteado antes: banco v3 (64 ontologías,
seed `20260815064`, disjunto de v1 y v2), panel de tres modelos declarado en
`f522df8`, criterio Δ ≤ −0,10 con permutación unilateral, unidad = ontología,
nulos como incorrectos. Los tres modelos habían pasado su propio gate de
lectura (0,993 · 0,955 · 0,896).

### Resultado primario: PASA en los tres

| modelo | indexada | sin_memoria | **Δ** | p (unilateral) | IC95% |
|---|---|---|---|---|---|
| `deepseek-v4-flash` | 0,083 | 0,201 | **−0,117** | 0,0007 | [−0,185 , −0,052] |
| `gemma2:9b` | 0,010 | 0,188 | **−0,177** | <0,001 | [−0,234 , −0,120] |
| `llama3.1:8b` | 0,031 | 0,208 | **−0,177** | <0,001 | [−0,240 , −0,120] |

Ningún IC cruza cero. Y el control cae en el mismo lugar en las tres familias:
**0,188 / 0,201 / 0,208** — la mejor evidencia de que el banco está calibrado y
el efecto no viene del instrumento.

### Secundarios: la recuperación se sostiene, el sesgo de fase NO

| modelo | tasa de respuesta | exactitud condicionada | recuperación de valor vivido | **sesgo fase − región** |
|---|---|---|---|---|
| `gemma2:9b` | 0,906 | 0,011 | 0,966 | **+0,768** |
| `llama3.1:8b` | 1,000 | 0,031 | 0,870 | **−0,162** |
| `deepseek-v4-flash` | 0,979 | 0,085 | 0,790 | **−0,007** |

La recuperación de valores vividos se sostiene en los tres (79-97%). **El sesgo
hacia la fase no.** Solo `gemma2:9b` lo tiene; `llama3.1:8b` se inclina hacia la
región y `deepseek-v4-flash` queda en cero exacto.

**Y no replicó ni dentro del mismo modelo:** `deepseek-v4-flash` marcaba +33,3
puntos de sesgo hacia fase en el banco v2 y **−0,7** en el v3. Era propiedad del
banco v2, no del modelo. Exactamente lo que un confirmatorio sobre tablas
nuevas existe para detectar.

### Redacción corregida

La aprobada decía "con sesgo hacia la celda que comparte fase". Esa cláusula se
cae. Queda:

> En tres modelos preespecificados —`gemma2:9b`, `deepseek-v4-flash` y
> `llama3.1:8b`—, sobre un banco preregistrado de ontologías separables y bajo
> decodificación determinista, **la memoria indexada no mejora la exactitud en
> la celda retenida: la reduce frente a `sin_memoria`**. Las respuestas están
> dominadas por recuperación de valores vividos (79-97%) en vez de la
> combinación región × fase requerida por la estructura generativa. **Cuál
> celda se recupera varía por modelo y no es una regularidad del panel**: solo
> `gemma2:9b` muestra sesgo hacia la celda que comparte fase.

Alcance: "replicado en tres familias de modelos". El mecanismo fino de
*qué* se recupera queda como observación por modelo, no como hallazgo del panel.

**Qué NO se cambió.** Ningún criterio se movió después de ver los números. El
banco v3 se generó y congeló antes de la primera llamada. Ninguna ontología
excluida. La cláusula del sesgo de fase se retira porque falló, no se
reinterpreta para que sobreviva.

---

## Ronda 1 — *pendiente (BLOQUEADA)*

**Pregunta:** ¿sobreviven y cruzan?
**Configuración prevista:** 30 días, densidad única 7%, con D-022 a D-026 aplicados.
32 mundos (8 seeds × 4 condiciones), directorio propio `data/silver/ronda1`.

**Bloqueo vigente (actualizado 2026-08-13):** el smoke test 30d del oráculo falló 0/5,
pero la causa registrada antes —"el techo informado no cruza a B teniendo la tabla
completa en el prompt" (§3 de `docs/WORLDLAB-avance-para-opus.md`)— quedó **invalidada**
por el tercer bug de instrumento: la región no es observable a distancia (D-029). Con
el techo colapsado LE sigue sin denominador, pero el 0/5 no es interpretable hasta
correr el probe de observabilidad y, si confirma, re-correr el gate con la región
expuesta como percepción en las 4 condiciones.

**Infra lista:** `scripts/worldlab_ronda1_recurrente.sh`, agendable cada 2 h; idempotente
(guard anti-doble-instancia + `--resume` por checkpoint de mundo).
