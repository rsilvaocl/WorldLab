# WorldLab — Especificación de la ontología del mundo

**Versión:** 1.0 (diseño aprobado)
**Fecha:** 2026-08-11
**Autor:** Opus 5, en sesión de diseño con el Comandante
**Estado:** aprobado por el Comandante (bloques 1 y 2). Listo para que Zod lo convierta a config + validadores.
**Sustituye:** las preguntas abiertas §4.1–§4.6 del handoff `WORLDLAB-handoff-opus-diseno-mundo.md`.

Este documento define el mundo concreto: qué existe, qué hace, quién lo habita y qué se mide.
No define el pre-registro estadístico, que se congela **después** del piloto (D-007).

---

## 1. Decisiones de diseño tomadas en esta sesión

Para registrar en `DECISIONES.md` con estos identificadores:

| ID | Decisión | Quién decidió |
|---|---|---|
| D-011 | Forma del mundo: escasez espacial (cúmulos), densidad como parámetro barrido | Comandante |
| D-012 | Percepción: identidad visible, propiedades ocultas | Comandante |
| D-013 | Regla del mundo: propiedades condicionadas por contexto (no recetas, no aniquilación) | Comandante |
| D-014 | Dos condiciones ortogonales (región × fase) con cruce retenido | Comandante |
| D-015 | Ontología concreta: 4 símbolos, valores separables, 8 cúmulos | Opus, aprobado por el Comandante |
| D-016 | Agentes con utilidad idéntica (sobrevivir); sin perfiles diferenciados | Opus, aprobado por el Comandante |
| D-017 | Expulsión de la región B al comenzar la fase oscura + invariante de no-consumo | Opus, aprobado por el Comandante |
| D-018 | El agente elige su propio horizonte de despertar | Opus, aprobado por el Comandante |

---

## 2. Principio rector

Todo lo que el agente necesita descubrir vive en un solo lugar: **el mapa símbolo → efecto**.
Ese mapa no es una lista de hechos sueltos, es una estructura con dos ejes (región y fase) que
se combinan de forma aditiva. Aprender el mundo significa recuperar esa estructura desde la
experiencia; tenerla regalada es lo que distingue al oráculo del aprendiz.

De ahí se derivan tres reglas que ordenan el resto del diseño:

1. **Nada semántico llega al modelo.** Los símbolos son opacos y los identificadores también.
   Los nombres legibles existen solo en el visor, aplicados al momento de dibujar.
2. **Lo que se aprende es la relación, no el dato.** Por eso los efectos son separables:
   una tabla arbitraria no se puede componer, y sin composición no hay world modeling que medir.
3. **Nada que diferencie a los agentes entre sí sale de nuestra configuración.** La única
   asimetría admitida es geográfica, y la produce la seed.

---

## 3. El mundo físico

### 3.1 Recursos

Cuatro símbolos opacos. El efecto de consumo se **genera** con `build_separable_effects`,
nunca se escribe celda por celda:

```
efecto(símbolo, región, fase) = base + δ_región + δ_fase
```

| Símbolo | Rol | base | δ región B | δ fase oscura |
|---|---|---|---|---|
| S1 | consumible | +8 | −11 | −4 |
| S2 | consumible | −2 | +9 | +3 |
| S3 | material | 0 | 0 | 0 |
| S4 | consumible marginal | +1 | 0 | −1 |

Normalización: la región A y la fase clara son la referencia (δ = 0).

Tabla resultante:

| | A-clara | A-oscura | B-clara | **B-oscura (retenida)** |
|---|---|---|---|---|
| S1 | +8 | +4 | −3 | **−7** |
| S2 | −2 | +1 | +7 | **+10** |
| S3 | 0 | 0 | 0 | **0** |
| S4 | +1 | 0 | +1 | **0** |

**Racional de los valores:**

- **S1 y S2 son espejos geográficos.** Uno alimenta en el norte y envenena en el sur; el otro
  al revés. Esa oposición es lo que hace que un vecino tenga valor sin que ninguna regla lo
  imponga: si nací junto a un cúmulo de S1 y tú junto a uno de S2, cada uno tiene algo que al
  otro le sirve. Es la precondición del intercambio, no el intercambio.
- **S3 no alimenta nunca.** Aprender que algo *no* sirve para comer también es aprender el mundo,
  y da a `build` un material dedicado.
- **S4 es el control de resolución fina.** Sus efectos son pequeños (+1, 0): mide si el agente
  distingue "poco" de "nada", que es más difícil que distinguir "bueno" de "veneno". Su celda
  retenida vale 0, la más difícil de acertar por azar.

**Invariante permanente:** `separable_invariant_holds(effects)` debe pasar siempre. Es decir,
para todo símbolo, `efecto(B,oscura) − efecto(B,clara) == efecto(A,oscura) − efecto(A,clara)`.
Si alguien edita un valor a mano y rompe la igualdad, el mundo deja de ser derivable y el test
de composición pierde todo significado. Ya implementado por Zod (D-009).

**Requisito adicional:** `δ_fase ≠ 0` en al menos dos símbolos. Si la fase no muerde,
B-oscura es idéntica a B-clara, el agente ya la vivió y no hay segunda regla que componer.

### 3.2 Geografía

- Grid 30×30. Región A: `x < 15`. Región B: `x ≥ 15`.
- **8 cúmulos**, radio 3, cada uno de un solo símbolo. **4 por región.**
- Posición sorteada por seed dentro de la región que le corresponde.

**Requisito no negociable:** los cuatro símbolos deben existir en **ambas regiones**. Si S1 solo
aparece en A, el agente nunca puede probarlo en B, nunca aprende la regla espacial, y el
experimento entero queda sin base. Es el error más fácil de cometer al sembrar, y merece un test
que falle si algún símbolo queda ausente de una región.

### 3.3 Densidad — la perilla del barrido

| Nivel | Fracción de celdas con recurso |
|---|---|
| holgado | 12% |
| justo | 7% |
| hambre | 4% |

El agrupamiento en cúmulos es **constante estructural** del mundo; la densidad es la única
variable de presión que se barre. No compiten entre sí (D-011).

### 3.4 Regeneración

Cada cúmulo recupera **+0.5 unidades por día**, con tope en su carga inicial.

Sin regeneración, la escasez crece monótonamente con el tiempo y se confunde con cualquier
efecto que queramos medir: no sabríamos si el día 80 fue distinto por lo que aprendió el agente
o porque el mundo estaba más vacío. Con regeneración el mundo alcanza estado estable y la
presión la fija la perilla, no el reloj.

### 3.5 Muerte

Energía en 0 durante **48 ticks consecutivos** (un día completo) ⇒ el agente sale del mundo y
su inventario cae al suelo en su última celda.

### 3.6 Estructura

Una sola: `struct_a`.

- **Receta (fija en `WorldConfig.recipes`):** S3×2 + S4×1
- **Función:** reduce a la mitad el costo metabólico por tick de quien esté en una celda
  adyacente, **solo durante la fase oscura**.

Con esto `build` deja de ser un tic sin consecuencia (las 20 casas gratis del baseline viejo) y
pasa a ser una inversión con retorno condicionado. Crea además un bien inmueble disputable, que
es el tipo de situación de la que puede salir algo interesante.

### 3.7 El ciclo y la frontera

- Ciclo de dos fases: clara / oscura, duración configurable en ticks.
- **Barrera:** durante la fase oscura no se puede cruzar hacia la región B.
- **Expulsión (D-017):** al comenzar la fase oscura, todo agente que se encuentre en B es
  desplazado a la celda libre más cercana de A.

La expulsión no es un adorno. Sin ella, un agente que se quede en B al cambiar la fase **vive la
celda retenida**, y el test de composición se cae en silencio: sin error, sin test rojo, sin que
nadie se entere hasta el análisis. Como regla de mundo es arbitraria y sin análogo lingüístico,
lo que encaja con el resto de la física; y obliga a gestionar el ciclo, que produce decisiones
observables.

**Invariante de seguridad:** ningún evento `consume` puede existir con `(región=B, fase=oscura)`.
Si aparece uno, ese mundo se descarta del análisis de composición. Es la red que detecta
cualquier fuga por una vía no prevista.

---

## 4. Los agentes

### 4.1 Utilidad

Cinco agentes **idénticos**. Misma función de utilidad: **sobrevivir**. Sin perfiles, sin pesos
diferenciados, sin roles.

Esto revoca el §4.4 del handoff, que pedía perfiles diferenciados. El motivo: cualquier
diferencia que les demos es una explicación alternativa de todo lo que observemos después. Si
uno acumula y otro reparte porque les pusimos pesos distintos, la especialización que
celebremos al final la escribimos nosotros en una línea de configuración. La heterogeneidad ya
viene de la geografía (D-011) — dónde nació cada uno, qué cúmulo le tocó cerca — y esa fuente
es real, asimétrica y no la dictamos agente por agente.

Si con utilidades idénticas aparece división de roles, eso sí es un hallazgo.

### 4.2 Desempeño

**Energía media por tick** a lo largo del mundo, contando 0 después de morir.

Continua y acotada. Da mucho más poder estadístico que "sobrevivió sí/no" con el número de
mundos que vamos a poder correr.

**Nivel de agregación:** el desempeño de un mundo es la media de los cinco agentes de ese mundo.
La unidad experimental es el mundo, nunca el agente (los cinco están acoplados: comparten
recursos y se afectan entre sí). LE se calcula por mundo y se agrega entre mundos.

### 4.3 Condiciones experimentales

| Condición | Qué recibe |
|---|---|
| `determinista` | Baseline paramétrico optimizado, sin LLM |
| `llm_sin_memoria` | Solo la percepción del tick actual |
| `llm_memoria` | Percepción + registro literal de sus propios eventos pasados |
| `llm_oraculo` | Percepción + la tabla completa de efectos, incluida B-oscura |
| `llm_memoria_corrupta` | Mismo volumen de registro, con hechos de otro seed |

Las tres del medio producen la métrica primaria (D-006):

```
LE = (memoria − sin_memoria) / (oráculo − sin_memoria)
```

`llm_memoria_corrupta` es el control que puede tumbar el resultado principal: si rinde igual que
la memoria verdadera, lo que ayudaba era el volumen de contexto, no la información. Cuesta poco
y es de las pocas cosas capaces de refutar el hallazgo, así que entra en la corrida
confirmatoria.

**Alcance del piloto:** solo las tres condiciones de LE (`llm_sin_memoria`, `llm_memoria`,
`llm_oraculo`), en los tres niveles de densidad, con 8 mundos por celda. Es lo mínimo para
estimar la varianza entre mundos y justificar el N definitivo. `determinista` y
`llm_memoria_corrupta` entran en la corrida confirmatoria.

### 4.4 Qué es la memoria

Registro **literal** de los eventos propios del agente: acción, contexto (región y fase),
resultado. Nada más. Sin campo de "aprendizaje", sin notas libres, sin resúmenes.

Un espacio para escribir conclusiones sería darle el andamio del razonamiento, y después no
podríamos distinguir el modelo que construyó él del que le prestamos nosotros. El registro va
crudo; que lo interprete solo, si puede.

### 4.5 Probes de predicción forzada

Cada **10 días** se pausa la simulación y se le hacen preguntas sin consecuencia sobre el mundo.
Respuesta en **6 niveles de magnitud** (pérdida grande → ganancia grande), azar ≈ 17% (D-010).

Tres tipos, todos en cada ronda:

| Tipo | Ejemplo | Qué detecta |
|---|---|---|
| Vividas | "¿S1 en A durante clara?" | Aprendizaje simple. Si falla esto, nada más es interpretable |
| **Retenida** | "¿S1 en B durante oscura?" | **Composición — la prueba de fondo** |
| Inexistente | "¿S7 en A durante clara?" (S7 no existe) | Alucinación / calibración |

Tres condiciones obligatorias:

1. **Sin feedback.** Nunca se le dice si acertó.
2. **No entran en la memoria.** Si el probe queda registrado, le estamos enseñando el mundo con
   nuestras propias preguntas.
3. **Orden sorteado por seed**, para eliminar efectos de secuencia.

Métricas: `level_correct` (primaria), `sign_correct` (secundaria).

El sub-check del piloto propuesto por Zod queda incorporado en el tipo "vividas": si los agentes
no aprenden ni la regla simple, el diagnóstico es "el mundo era demasiado difícil", no "no
modelan". Solo si aprenden la simple, el resultado del probe retenido es interpretable.

### 4.6 Comunicación

| Parámetro | Valor |
|---|---|
| Alfabeto | **4 símbolos** |
| Longitud máxima del mensaje | 3 símbolos |
| Costo | 1.0 de energía por mensaje |
| Radio de audición | 6 |

El alfabeto baja de 9 a 4 por una razón estadística: el estimador de información mutua está
sesgado al alza cuando el alfabeto es grande y las muestras pocas. Con 9 símbolos y un puñado de
mensajes por mundo, "detectaríamos" señalización inexistente.

**Medición de emergencia de señalización:** información mutua entre el símbolo emitido y el
estado del mundo / la acción posterior del receptor, contrastada contra un **nulo por
permutación** (barajar qué símbolo se emitió y recalcular), no contra cero.

Nota deliberada: `hear_radius` (6) es mayor que el radio de visión (4). Un agente puede oír a
quien no ve. Es una decisión, no un accidente.

### 4.7 Asignación de atención

El agente **elige su propio horizonte de despertar**: junto con su acción declara en cuántos
ticks quiere volver a decidir. El motor lo respeta salvo eventos de emergencia.

Ataca la crítica #13 del documento de revisión ("el trigger de evento es la decisión"). Despertar
al agente cuando *nosotros* consideramos que pasa algo relevante es hardcodear el núcleo de la
autonomía. Devolverle esa elección lo convierte además en un dato medible —la distribución de
horizontes elegidos: un agente que entendió el ciclo debería despertar antes de que cierre la
frontera— y baja el costo de API, porque un agente tranquilo pide dormir más.

---

## 5. Pendientes de motor

Lo que este diseño requiere y aún no existe en el código:

| # | Qué | Por qué |
|---|---|---|
| 1 | **Expulsión de B al iniciar la fase oscura** | Sin ella el held-out se contamina en silencio (§3.7) |
| 2 | **Invariante: ningún `consume` en (B, oscura)** | Red de seguridad del punto anterior |
| 3 | Siembra en cúmulos con los 4 símbolos en ambas regiones, + test | §3.2 |
| 4 | Regeneración por cúmulo | §3.4 |
| 5 | Muerte por inanición sostenida (48 ticks) | §3.5 |
| 6 | Efecto de `struct_a` sobre el metabolismo en fase oscura | §3.6 |
| 7 | Alfabeto simbólico a 4 | §4.6 |
| 8 | Horizonte de despertar elegido por el agente | §4.7 |
| 9 | Condición `llm_memoria_corrupta` | §4.3 |
| 10 | **Re-optimizar el baseline determinista** | Sus parámetros se calcularon con la mecánica anterior a los fixes de mecánica; los actuales no son válidos y producirían un hombre de paja |

---

## 6. Qué NO decide este documento

- **El pre-registro estadístico.** Se congela después del piloto, cuando se conozca σ entre
  mundos y se pueda justificar el N (D-007).
- **El número final de seeds.** Sale del cálculo de potencia con los datos del piloto.
- **El presupuesto de la corrida confirmatoria.** Se dimensiona con el costo real por
  mundo medido en el piloto.
- **El mundo reservado.** Su configuración se congela junto con el pre-registro y se corre una
  sola vez.

---

## 7. Criterio de falsación

Escrito antes de correr, según exige el §7.12 del protocolo.

**Concluiremos que no hubo world modeling si:**

- Los agentes aciertan los probes de celdas vividas pero **no superan el azar (~17%) en el probe
  retenido**. Aprendieron dónde les fue bien; no recuperaron la estructura.
- O bien `LE ≈ 0`: el agente con memoria no se separa del agente sin memoria.
- O bien `llm_memoria_corrupta ≈ llm_memoria`: lo que ayudaba era el volumen de contexto, no la
  información contenida.

**Concluiremos que el mundo era demasiado difícil (resultado no interpretable, no negativo) si:**

- Los agentes fallan incluso los probes de celdas vividas.

**Concluiremos que hubo world modeling si:**

- Aciertan las vividas **y** superan el azar en la retenida **y** `LE > 0` de forma consistente
  entre seeds **y** la memoria corrupta no reproduce el efecto.

---

## 8. Configuración de referencia

Valores para que Zod los traduzca a `WorldConfig`. Los nombres son indicativos.

```python
SYMBOLS = ["S1", "S2", "S3", "S4"]

EFFECT_SPEC = {                     # base, δ_región_B, δ_fase_oscura
    "S1": (+8.0, -11.0, -4.0),
    "S2": (-2.0,  +9.0, +3.0),
    "S3": ( 0.0,   0.0,  0.0),
    "S4": (+1.0,   0.0, -1.0),
}
# consume_effects = build_separable_effects(EFFECT_SPEC)
# assert separable_invariant_holds(consume_effects)

WORLD = dict(
    width=30, height=30, days=100, ticks_per_day=48,
    region_split=0.5,                   # A: x < 15 | B: x >= 15
    n_phases=2, phase_ticks=24,         # clara / oscura, media jornada cada una
    phase_barriers={(1, "B"): True},    # fase oscura cierra la región B
    expel_on_phase_start={(1, "B"): "A"},   # PENDIENTE de implementar
    clusters=dict(n=8, radius=3, per_region=4, symbols_per_region="all"),
    density_levels={"holgado": 0.12, "justo": 0.07, "hambre": 0.04},
    regen_per_day=0.5,
    starvation_ticks=48,
    recipes={"struct_a": {"S3": 2.0, "S4": 1.0}},
    struct_effects={"struct_a": {"metabolism_factor": 0.5, "phase": 1, "range": 1}},
    symbol_alphabet=["k1", "k2", "k3", "k4"],
    max_message_symbols=3,
    talk_cost=1.0,
    hear_radius=6,
    vision_radius=4,
)

AGENTS = dict(n=5, utility="survive", identical=True)

PROBES = dict(every_days=10, levels=6, types=["lived", "held_out", "nonexistent"],
              feedback=False, enters_memory=False, order_by_seed=True)
```

---

## 9. Riesgos asumidos

| Riesgo | Mitigación acordada |
|---|---|
| El mundo es demasiado difícil y todo sale plano | Probes de celdas vividas como sub-check: distinguen "mundo difícil" de "no modela" |
| No emerge ninguna interacción entre agentes | El barrido de densidad convierte el "no apareció" en un dato ("hizo falta este nivel de presión") |
| No emerge señalización en el canal simbólico | Resultado negativo legítimo, medido contra nulo por permutación |
| El held-out se contamina | Expulsión + invariante de no-consumo + descarte del mundo afectado |
| El costo de API se dispara | Horizonte de despertar elegido por el agente; prefijo de prompt estable para aprovechar caché |
