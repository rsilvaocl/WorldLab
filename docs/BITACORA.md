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

## Ronda 1 — *pendiente*

**Pregunta:** ¿sobreviven y cruzan?
**Configuración prevista:** 30 días, densidad única 7%, con D-022 a D-026 aplicados.
