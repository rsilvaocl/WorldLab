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
