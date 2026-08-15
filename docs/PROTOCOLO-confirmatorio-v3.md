# Protocolo del estudio confirmatorio — `composicion-bank-v3`

**Qué es este documento y qué NO es.** Es el registro consolidado de un
protocolo **congelado prospectivamente y versionado en Git antes de la
adquisición de datos**. No es una inscripción en un registro público externo
(OSF, AsPredicted). Esa inscripción habría sido preferible y **no existió**; no
se puede crear retroactivamente como si hubiera precedido la corrida, y este
documento no pretende sustituirla. Lo que aporta es evidencia prospectiva
auditable: los commits que fijan cada decisión anteceden, con hora, a la primera
llamada a un modelo.

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
| `data/resultados/confirmatorio_bankv3.json` | `56896f7086b660cb19397227d775801e75974c3ba23c6167577bfb08a1407954` |

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

---

## 2. Hipótesis primaria — prueba CONJUNTA

Formulada como **conjunción sobre los tres modelos**, no como tres contrastes
independientes:

> Los **tres** modelos preespecificados satisfacen
> Δ(`memoria_indexada` − `sin_memoria`) ≤ **−0,10**, cada uno con permutación
> pareada **unilateral** (cola inferior) y **p < 0,05**.

Al exigir que **todos** cumplan, la prueba es de tipo intersección-unión: el
error tipo I del conjunto está acotado por el de un contraste individual, así
que **no requiere corrección por multiplicidad** — la conjunción es más
conservadora que cualquier contraste suelto, no menos.

- **Unidad de análisis:** la **ontología** (n = 64). Los agentes son réplicas
  técnicas, no n: con exposición determinista y `temperature=0` son réplicas
  exactas (verificado — σ_Δ salió 0,0 al intentar usar el mundo como unidad).
- **Outcome:** proporción de probes correctos en la celda retenida B-oscura,
  evaluada por **nivel de magnitud** (6 niveles, D-010).
- **Nulos:** cuentan como **incorrectos** (criterio conservador).
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
- **Nulos observados:** 36/384 (`gemma2:9b`, 9,4%), 8/384
  (`deepseek-v4-flash`, 2,1%), 0/384 (`llama3.1:8b`). Derivados de la tasa de
  respuesta reportada; la asimetría entre modelos es real y queda como
  observación, no como explicación del efecto (el primario sobrevive al
  condicionar por respuesta).
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

**Primario — la conjunción se cumple:**

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
