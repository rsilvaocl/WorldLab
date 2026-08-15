# Protocolo del estudio confirmatorio — `composicion-bank-v3`

**Qué es este documento y qué NO es.** Es el registro consolidado de un
protocolo **congelado prospectivamente y versionado en Git antes de la
adquisición de datos**. No es una inscripción en un registro público externo
(OSF, AsPredicted). Esa inscripción habría sido preferible y **no existió**; no
se puede crear retroactivamente como si hubiera precedido la corrida, y este
documento no pretende sustituirla. Lo que aporta es evidencia prospectiva
auditable: los commits que fijan cada decisión anteceden, con hora, a la primera
llamada a un modelo.

**Límite de esa evidencia (Terra, 15/08):** las horas locales de Git **no son
prueba externa de anterioridad** — pueden reescribirse, y el repositorio no
conserva el timestamp de la primera llamada a un modelo. Lo defendible es
*"traza Git consistente con congelamiento prospectivo"*, no evidencia
independiente equivalente a OSF o AsPredicted.

---

## 1. Cadena de custodia

| commit | hora (ISO, local) | qué fija |
|---|---|---|
| `100b4f3` | 2026-08-15 12:40:12 −0400 | Banco v3 congelado + pre-registro completo (unidad, outcome, dirección, umbral, tratamiento de nulos, secundarios) |
| `f522df8` | 2026-08-15 12:44:58 −0400 | Panel de **tres** modelos declarado |
| — | entre 12:44:58 y 14:28 | **Ejecución del confirmatorio** (primera llamada posterior a `f522df8`) |
| `66bc28e` | 2026-08-15 14:54:40 −0400 | Resultado registrado |

**Advertencia sobre timestamps de archivo:** los `mtime` de
`data/banco/composicion_bank_v3.json` NO sirven como prueba de congelamiento —
un `git switch` posterior (recuperación del árbol, ver bitácora 15/08) los
reescribió. **La evidencia válida es la hora del commit**, no la del archivo.

### Checksums

| artefacto | SHA-256 |
|---|---|
| `data/banco/composicion_bank_v3.json` | `cc8f01a22a029a2f28c6e139c06cc74f1dea3a3baba4079aeff91153ae60a055` |
| `data/resultados/confirmatorio_bankv3.json` (**agregado**) | `56896f7086b660cb19397227d775801e75974c3ba23c6167577bfb08a1407954` |

**`confirmatorio_bankv3.json` NO es resultado crudo** (corrección de Terra):
contiene proporciones por ontología y métricas derivadas, pero **no** respuestas
por probe, errores, reintentos ni timestamps. El script descarta las filas por
probe tras calcular las tres componentes. **No existen JSONL crudos de esta
corrida**, así que los secundarios **no son recomputables desde disco**;
obtenerlos exige re-correr con persistencia por probe.

### Blobs del código en `HEAD` de la corrida

| blob | archivo |
|---|---|
| `6097a5c` | `ai/banco_ontologias.py` (generador, permutación, bootstrap) |
| `ff8ad92` | `ai/fase_exposicion.py` (Fase E) |
| `e59ee35` | `ai/gate_lectura.py` (gate y tres componentes) |
| `d015177` | `ai/memory.py` (renderer canónico, memoria indexada) |
| `bf1ce84` | `ai/llm_agent.py` (`predict_effect`, Fase P) |

El banco es **regenerable** desde su seed (`20260815064`) con
`generar_banco(n=64, seed=20260815064)`; hay test permanente que lo verifica y
que comprueba que es disjunto de v1 y v2.

### BRECHA DE REPRODUCIBILIDAD, declarada (hallazgo de Terra, 15/08)

La corrida **no usó `ai/run_composicion.py`**. Ese runner apunta al banco **v2**,
ejecuta **tres** condiciones, usa permutación **bilateral** por defecto y **no
pasa `thinking=False`** (el adaptador omite el campo cuando recibe `None`):
ejecutarlo **no reproduce** el v3.

El confirmatorio se ejecutó como **heredoc en línea**, que no quedó versionado.
Los blobs publicados originalmente no permitían reconstruir la ejecución.

**Reparación:** la transcripción literal de ese heredoc quedó en
`ai/run_confirmatorio_v3.py`, guardada **después** de la corrida. Cierra la
brecha de reconstrucción pero **no aporta anterioridad** — no es un artefacto
congelado antes de los datos, y presentarlo como tal falsificaría la custodia.

| blob | archivo | rol |
|---|---|---|
| `fcb4e71` | `ai/run_confirmatorio_v3.py` | script exacto de la corrida (versionado a posteriori) |
| `9d4a7c4` | `ai/model_adapter.py` | cliente LLM (`thinking`, reintentos) |
| `365b359` | `ai/run_composicion.py` | runner de Zod — **NO** es el de esta corrida |

**Comando exacto ejecutado:**

```bash
set -a && . ./.env && set +a
.venv/bin/python - <<'"'"'PY'"'"'   # contenido = ai/run_confirmatorio_v3.py
```

---

## 2. Criterio confirmatorio COMPUESTO (no "hipótesis primaria")

Renombrado tras la auditoría de Terra (15/08). Es un **criterio operacional
compuesto**, no una hipótesis estadística sobre un efecto de 10 puntos:

> Los **tres** modelos preespecificados satisfacen **ambas** condiciones:
> (i) Δ(`memoria_indexada` − `sin_memoria`) **observado** ≤ −0,10, y
> (ii) significación contra cero con permutación pareada **unilateral**
> (cola inferior) y **p < 0,05**.

**El nulo estadístico es H₀: Δ = 0**, no H₀: Δ ≥ −0,10. La permutación
implementada contrasta contra cero; el −0,10 es un **umbral operacional sobre el
efecto observado**, fijado de antemano, no un margen inferencial.

**Lo que esto SÍ y NO demuestra** (diagnóstico post hoc, centrando el contraste
en −0,10):

| modelo | p vs Δ=0 | p vs Δ=−0,10 | IC95% cruza −0,10 |
|---|---|---|---|
| `deepseek-v4-flash` | 0,0007 | **0,3154** | **sí** |
| `gemma2:9b` | <0,001 | 0,0051 | no |
| `llama3.1:8b` | <0,001 | 0,0070 | no |

**Conclusión defendible:** los tres reducen la exactitud y cumplen el criterio
operacional pre-registrado. **NO está demostrado que el efecto poblacional sea
de al menos 10 puntos en los tres** — en `deepseek-v4-flash` no lo está.

Sobre multiplicidad: al exigir que **todos** cumplan, es de tipo
intersección-unión y el error tipo I del conjunto queda acotado por el de un
contraste individual, así que no requiere corrección adicional.

- **Unidad de análisis:** la **ontología** (n = 64). Los agentes son réplicas
  técnicas, no n: con exposición determinista y `temperature=0` resultaron
  réplicas exactas (verificado — σ_Δ salió 0,0 al intentar usar el mundo como
  unidad). Nota: `temperature=0` **no garantiza determinismo**, menos aún en
  una API; es un parámetro, no una propiedad demostrada.
- **Outcome:** proporción de probes correctos en la celda retenida B-oscura,
  evaluada por **nivel de magnitud** (6 niveles, D-010).
- **Nulos:** cuentan como **incorrectos**. NO se describe como criterio
  conservador: ante una hipótesis direccional de deterioro puede **amplificar**
  el efecto esperado en vez de atenuarlo.
- **Dirección:** declarada de antemano (se espera que la memoria **reduzca** la
  exactitud), lo que justifica la prueba unilateral.

---

## 3. Secundarios PRE-REGISTRADOS

Descriptivos, reportados **por separado** — no son gates y no condicionan la
conclusión primaria:

1. **tasa de respuesta**;
2. **exactitud condicionada a respuesta**;
3. **recuperación de valor vivido** y **sesgo fase − región**.

Se reportan separados porque abstención y recuperación **no son extremos de un
único eje**: en el v2, `deepseek-v4-flash` recuperaba menos *y* se abstenía
menos que `gemma2:9b`.

**Post hoc, marcado como tal:** el análisis "de qué celda copia" sobre el banco
v2 (14/08) fue exploratorio; su hallazgo de sesgo hacia fase es lo que el v3
puso a prueba y **no replicó**.

---

## 4. Modelos y parámetros de inferencia

| modelo | proveedor | identidad | parámetros |
|---|---|---|---|
| `gemma2:9b` | Ollama local | digest `ff02c3702f32` | `temperature=0` |
| `llama3.1:8b` | Ollama local | digest `46e0c10c039e` | `temperature=0` |
| `deepseek-v4-flash` | API DeepSeek | sin digest expuesto por el proveedor | `temperature=0`, `thinking={"type":"disabled"}` |

**Limitación declarada:** el modelo de API no es verificable por digest ni
inmutable; el proveedor puede cambiarlo sin aviso. Los dos locales sí quedan
fijados por digest.

Cada modelo pasó su **propio gate de lectura** antes de entrar (≥0,75 agregado,
≥0,60 por celda), sobre el banco v2 —de desarrollo— para no gastar el v3:
`deepseek-v4-flash` 0,993 · `gemma2:9b` 0,955 · `llama3.1:8b` 0,896.

---

## 5. Reglas de exclusión, fallos y detención

- **Exclusión de ontologías: ninguna.** Excluir selectivamente sesga el
  estimando. Las 64 entran al análisis rindan lo que rindan.
- **Fallos de API / respuestas no parseables:** el cliente reintenta hasta 3
  veces con backoff (`max_retries=2`); agotados los intentos, la respuesta se
  registra como **nula** y cuenta como incorrecta.
- **Nulos observados, condición `memoria_indexada` únicamente:** 36/384
  (`gemma2:9b`, 9,4%), 8/384 (`deepseek-v4-flash`, 2,1%), 0/384
  (`llama3.1:8b`). Derivados de la tasa de respuesta reportada.
  **Los nulos de `sin_memoria` NO se registraron** — el script solo persistió
  filas por probe de `memoria_indexada`. Es un vacío del registro, no un cero.
  La asimetría entre modelos queda como observación, no como explicación del
  efecto: el primario sobrevive al condicionar por respuesta.
- **Regla de detención:** el estudio corre las 64 ontologías × 3 modelos × 2
  condiciones completas. **No hay parada opcional** ni análisis intermedios que
  puedan gatillar una decisión.
- **Sin exclusión de agentes por rendimiento**, en ninguna condición.

---

## 6. Implementación exacta de la inferencia

Ambas en `ai/banco_ontologias.py` (blob `6097a5c`), con tests:

**Permutación pareada unilateral** — bajo la nula el signo de cada diferencia
es intercambiable; 20.000 permutaciones; p = (extremos + 1) / (n_perm + 1):

```python
obs = mean(difs)
for _ in range(n_perm):
    m = mean(x if rng.random() < 0.5 else -x for x in difs)
    if signo * m >= signo * obs - 1e-12: extremos += 1
```

**IC bootstrap percentil al 95%**, remuestreando **ontologías** (no probes),
20.000 réplicas.

No se asume normalidad: con 64 proporciones acotadas sería un supuesto gratuito.

---

## 7. Resultado

**Criterio compuesto — se cumple en los tres** (Δ observado ≤ −0,10 y p < 0,05
contra cero). Recordar que el nulo es Δ = 0: no se demuestra un efecto
poblacional de 10 puntos en los tres (ver §2).

| modelo | indexada | sin_memoria | Δ | p (unilateral) | IC95% |
|---|---|---|---|---|---|
| `deepseek-v4-flash` | 0,083 | 0,201 | −0,117 | 0,0007 | [−0,185 , −0,052] |
| `gemma2:9b` | 0,010 | 0,188 | −0,177 | <0,001 | [−0,234 , −0,120] |
| `llama3.1:8b` | 0,031 | 0,208 | −0,177 | <0,001 | [−0,240 , −0,120] |

Ningún IC cruza cero. El control `sin_memoria` cae en el mismo lugar en las
tres familias (0,188 / 0,201 / 0,208).

**Secundarios:**

| modelo | tasa de respuesta | exactitud condicionada | recuperación de valor vivido | sesgo fase − región |
|---|---|---|---|---|
| `gemma2:9b` | 0,906 | 0,011 | 0,966 | **+0,768** |
| `llama3.1:8b` | 1,000 | 0,031 | 0,870 | **−0,162** |
| `deepseek-v4-flash` | 0,979 | 0,085 | 0,790 | **−0,007** |

**Referencia de azar del banco v3:** 0,203 — la mejor estrategia constante
(contestar siempre el mismo nivel de magnitud), **no** 1/6.

---

## 8. Conclusión, con su alcance

> En tres modelos preespecificados —`gemma2:9b`, `deepseek-v4-flash` y
> `llama3.1:8b`—, sobre un banco preregistrado de ontologías separables y bajo
> decodificación determinista, la memoria indexada no mejora la exactitud en la
> celda retenida: la reduce frente a `sin_memoria`. Entre las respuestas no
> nulas, predominan las recuperaciones de valores vividos (79–97%) en vez de la
> combinación región × fase requerida por la estructura generativa. La celda
> recuperada varía por modelo y no constituye una regularidad del panel: solo
> `gemma2:9b` muestra sesgo hacia la celda que comparte fase.

Alcance en tres niveles:

- **Efecto primario:** replicado en **tres modelos preespecificados** de tres
  familias. No se afirma "los LLM hacen esto".
- **Recuperación de valores vividos:** replicada en los tres.
- **Dirección fase/región:** descriptiva, específica de cada modelo **en este
  banco**.

**Lo que el diseño hace visible.** D-022 garantiza que la celda retenida cae en
un nivel de magnitud distinto al de las tres vividas; por eso recuperar un valor
vivido es *necesariamente* incorrecto y el rendimiento cae por debajo del
control. Esa caída es propiedad **conjunta** del banco, el criterio de scoring,
la estrategia de recuperación y D-022 — **no** una capacidad negativa general
del modelo. Sin D-022, copiar una celda vivida habría recibido crédito falso por
composición.

---

## 9. Qué NO se hizo

- No se movió ningún criterio después de ver los números.
- No se excluyó ninguna ontología.
- No se regeneró la seed del banco.
- El secundario que falló (sesgo de fase) **se retira, no se reinterpreta** para
  que sobreviva.
- La hipótesis pre-especificada en D-037 **se conserva intacta**, incluida la
  parte que después falló: reescribirla sería fabricar un pre-registro que
  acierta siempre.
- La entrada de bitácora del 14/08 **no se reescribió**; lleva una nota fechada
  que la acota.
