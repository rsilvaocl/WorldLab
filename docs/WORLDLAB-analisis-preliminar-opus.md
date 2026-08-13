# WorldLab — Análisis preliminar para Opus (piloto en curso)

Fecha: 2026-08-13 08:45 (hora local, Chile)
Autor: Zod (soldado de ingeniería) · para revisión de Opus 5
Estado: **PRELIMINAR — 94/96 mundos completados** (faltan 2 del seed 8). Análisis generado con `ai/analyze_pilot.py` (fix aplicado: claves tupla no serializables en `piloto_analysis.json`).

## 1. Señal dominante: los agentes LLM NO sobreviven 30 días

| Condición | Energía μ | Supervivientes μ | Probes vividas | Probes retenida |
|---|---|---|---|---|
| sin_memoria (d=4/7/12%) | **0.0** | **0.0** | NaN (sin probes) | NaN (sin probes) |
| memoria (d=4/7/12%) | **0.0** | **0.0** | NaN | NaN |
| oraculo (d=4/7/12%) | **0.0** | **0.0** | NaN | NaN |
| baseline_empirico (d=4%) | 16.8 | 0.9 | 63.9% | **0.0%** (0/8) |
| baseline_empirico (d=7%) | 23.0 | 1.4 | 58.3% | **0.0%** (0/11) |
| baseline_empirico (d=12%) | 23.3 | 2.5 | 46.3% | **0.0%** (0/21) |

- **Todas las condiciones LLM mueren**: energía μ = 0.0, supervivientes μ = 0.0, en las 3 densidades y 3 condiciones (sin_memoria, memoria, oráculo). El baseline empírico sobrevive (0.9–2.5 supervivientes, energía 16.8–23.3).
- **Consecuencia operativa**: sin supervivientes LLM no hay probes (0/0, NaN). **No se puede calcular LE** (numerador y denominador = 0). El piloto midió que el mundo a 30 días es **inhabitable para qwen2.5:7b**, no midió composición.
- Consistente con el hallazgo verificado: qwen2.5 "piensa en intención, no distancia" → propone gather a distancia → rechazos del validador (~80%) → no come → muere de inanición. El baseline empírico se mueve cada tick y come.

## 2. Sub-check de Opus (celdas vividas): aplica al baseline, no a los LLM

- Baseline empírico acierta vividas al 46–64% (varias veces el azar de magnitud ~17%) — el mundo es **aprendible por experiencia** cuando el agente vive.
- Retenida: **0.0% en las 3 densidades** (0/8, 0/11, 0/21). Control negativo perfecto: el baseline NO compone (no puede predecir la celda que nunca vio). La celda retenida está genuinamente fuera del alcance de la memoria.
- La comparación clave (LLM vs baseline en retenida) **no es posible aún** — los LLM no llegan al probe.

## 3. Exposición por celda: el diagnóstico es "mundo demasiado duro", no "no compone"

- **92% de agentes sub-expuestos** (36/39) con <3 consumos en alguna celda vivida. El corte dominante: **B-clara (B-0) = 0 consumos** en casi todos.
- La advertencia del script es explícita: si la mayoría está sub-expuesta, el hallazgo del piloto **no es sobre modelado** — es que 30 días no alcanzan para recorrer el mundo.
- B-0 = 0 sugiere que la barrera nocturna + expulsión impiden visitas suficientes a B en fase clara, o que la supervivencia corta el recorrido.

## 4. Costo real (local = $0, decisión de N despejada)

| Condición | tokens/mundo μ | llamadas μ | tiempo μ |
|---|---|---|---|
| sin_memoria | 230–379k | ~254 | 733–1267s |
| memoria | 376–559k | ~198–219 | 1248–1900s |
| oraculo | 82–120k | ~88–108 | 280–413s |
| baseline_empirico | 0 | 0 | 0s |

El costo no es el limitante. El limitante es la **supervivencia**, no el presupuesto.

## 5. Integridad del held-out: impecable

- **0/94 mundos contaminados** ✅ — la red de detección (`no_heldout_consumption`) no se activó en ningún mundo. Expulsión + invariante funcionan.

## 6. Preguntas para Opus (ronda 8)

1. **¿Cómo salvar la supervivencia sin contaminar el diseño?** Opciones que evaluar:
   a. Aumentar días (30 → 100, `ai/extend_pilot.py` ya existe) — pero si el agente muere el día 5, más días no ayudan; el agente muerto no aprende.
   b. **Suavizar el mundo** (más energía inicial / consumo más barato / recursos más densos) — pero el mundo RESERVADO debe congelarse; esto es calibración en mundo de desarrollo.
   c. **Aumentar `max_tokens`/mejorar el prompt** para reducir rechazos del validador (el 80% de rechazo es el problema de raíz: el LLM propone gather a distancia).
   d. Evaluar otro modelo local (gemma/qwen3 con think off) que ejecute la política física mejor.
2. **¿El probe retenido debería correr al morir el agente** (último estado) en vez de solo al final? Si el agente murió el día 5, su último conocimiento es limitado, pero quizás suficiente para una forced-choice — y evita el 0/0.
3. **Mínimo de exposición para declarar un mundo "válido"**: con 92% sub-expuesto, ¿congelamos el corte o lo revisamos?

## 7. Archivos de referencia

- `data/silver/piloto/piloto_summary.json` (94 mundos)
- `data/silver/piloto/piloto_analysis.json` (guardado tras fix)
- `data/silver/piloto_progress.log`
- Scripts: `ai/analyze_pilot.py` · `ai/extend_pilot.py` · `ai/run_pilot.py`

## 8. Nota honesta

El piloto NO está "funcionando" como experimento de composición todavía: está funcionando como **filtro de habitabilidad**. Ese es un resultado legítimo del piloto (para eso es el piloto), pero significa que la confirmatoria necesita un mundo habitable primero. Espero su directiva sobre la ronda de calibración antes de tocar la config del mundo.
