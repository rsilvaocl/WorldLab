# WorldLab — Documento de Revisión para Opus 5

**Versión:** 0.2 (revisión pre-diseño)
**Fecha:** 2026-08-11
**Autor del concepto:** ChatGPT (v0.1) + revisión adversarial de Claude + críticas de Zod (agente de Hermes)
**Solicitud:** Veredicto adversarial final antes de congelar el protocolo experimental e iniciar el diseño. No se pide código; se pide crítica de la metodología.

---

## 1. Contexto

- **Proyecto:** WorldLab — laboratorio experimental de agentes autónomos de IA en un mundo 2D controlado, persistente y reproducible.
- **Hardware:** Mac M2, 16 GB RAM, sin GPU dedicada. Sin servidores propios, sin cloud permanente.
- **Restricción fundamental:** bajo costo. Primero demostrar concepto; no comprar infraestructura hasta que la versión anterior no pueda resolver el experimento.
- **Estado:** concepto + 3 rondas de revisión (ChatGPT → Zod → Claude → respuesta ChatGPT → crítica de Zod sobre Claude). Este documento consolida todo para una cuarta y última ronda antes de congelar el protocolo.

---

## 2. Objetivo científico reformulado

> Construir un **banco de pruebas para distinguir comportamiento emergente de comportamiento inducido** en agentes de IA.

**Pregunta central:** Cuando colocamos un agente de IA en un mundo cuyas reglas no conoce y le damos experiencia, ¿podemos demostrar que **construye un modelo útil de ese mundo**, en lugar de simplemente aplicar conocimiento que ya traía?

No se busca AGI ni "inteligencia general". Se busca medir fenómenos concretos: cooperación, competencia, especialización, intercambio, alianzas, conflictos, adaptación, aprendizaje, prevención de riesgos — y distinguir cuáles son genuinos de cuáles son artefactos del diseño.

---

## 3. Arquitectura del concepto original (v0.1)

- Mundo 2D pequeño, recursos escasos (comida, agua, madera, piedra, hierro).
- 5 agentes con objetivos individuales, percepción limitada, memoria, recursos limitados, capacidad de comunicarse y actuar.
- **Regla crítica:** el LLM propone acciones en JSON (`{"action": "move", "target": "vase"}`); el World Engine valida (¿puede? ¿está cerca? ¿existe? ¿es físicamente posible? ¿hay energía?) y solo entonces ejecuta. El LLM **nunca** modifica el estado del mundo directamente.
- Sin instrucciones explícitas de cooperar, comerciar o construir sociedad.
- Separación estricta: realidad objetiva / percepción del agente / creencia / decisión / resultado.
- Stack propuesto originalmente: Godot 4 (motor) + Python/FastAPI (orquestación) + HTTP + Pydantic + SQLite + Parquet/DuckDB.

**Crítica de Zod (resumen):** Godot + FastAPI + HTTP es sobre-ingeniería para el MVP. El motor debe ser Python headless (estado en memoria, acciones validadas, telemetría JSONL, render ASCII para debug). Godot solo como reproductor de replay en fases tardías. Modelos: DeepSeek flash (API barata) o qwen3:8b / gemma4-qat:12b (local). Costo estimado: centavos a pocos dólares por simulación de 5 agentes × 100 días con decisiones por evento (no por frame).

---

## 4. Revisión adversarial de Claude (21 críticas, resumidas)

### I. Emergencia falsa por diseño del entorno
1. **El vocabulario es la respuesta:** "comida/agua/madera/piedra/hierro" + "casas/cofres" es Minecraft; el modelo ya trae miles de textos de aldeas y comercio. Si emerge comercio, se midió el corpus. **Test:** renombrar todo a R1..R5 + struct_a con recetas arbitrarias. Si el comercio desaparece, nunca fue emergente.
2. **La primitiva de acción ES el comportamiento:** si se implementa `trade()`, "¿emerge el comercio?" equivale a "¿emerge el salto?" en un juego con botón de salto. Emergencia real sería comercio construido desde drop + pickup + coordinación temporal, sin primitiva de intercambio.
3. **Las personalidades son instrucciones disfrazadas:** aunque se borre "Rex el comerciante", si su utilidad es maximizar riqueza y la riqueza requiere bienes ajenos, el comercio es consecuencia mecánica del diseño, no descubrimiento.
4. **El menú de acciones en el prompt** tiene efectos de orden y recencia. **Test:** aleatorizar el orden y meter 2-3 acciones señuelo inútiles.

### II. Aprendizaje falso
5. **Acumular contexto no es aprender.** Control decisivo: **agente oráculo** que recibe en t=0 todos los hechos que el agente con memoria habría descubierto. Si oráculo ≈ agente-con-memoria, no hubo aprendizaje: hubo acceso a información.
6. **Mejoró el mundo, no el agente.** Control: inyectar un agente virgen en un mundo del día 80. Si rinde igual que los veteranos, el "aprendizaje" estaba en el entorno.
7. **Sesgo de supervivencia:** los torpes mueren; la población superviviente parece más lista sin que nadie aprendiera. Medir trayectorias individuales, nunca promedios poblacionales.
8. **El trace es confabulación.** Test brutal: borrar el campo `Learning` de la memoria persistida y re-correr. Si el comportamiento no cambia, era decoración narrativa.

### III. World modeling falso — el fallo más grave
9. **La física está en el idioma:** la palabra "vaso" ya contiene la física (el vidrio se rompe, el borde es peligroso). El modelo no necesita el mundo para "predecir".
10. **La única prueba limpia: física invertida.** Mundo donde los objetos en el borde NO caen y los del centro sí; nombres abstractos (obj_7 con propiedad P). Si el agente sigue prediciendo que el borde es peligroso, usa su prior, no el mundo. Si aprende la regla invertida desde experiencia, ahí hay world modeling genuino.
11. **Sesgo de selección:** solo se ven predicciones de acciones ejecutadas. Necesario: **forced-choice probes** (preguntar qué predice, ejecutar independientemente, comparar).
12. **El world model puede ser solo más cómputo.** Control placebo: darle al baseline el mismo presupuesto de tokens extra en tarea irrelevante.

### IV. Autonomía falsa
13. **El trigger de evento es la decisión:** despertar al LLM cuando "se agota la comida" es hardcodear la asignación de atención (núcleo de la autonomía). Mínimo: medir qué fracción del comportamiento se explica solo con la tabla de triggers.
14. **El validador hace el trabajo:** si se rechazan acciones inválidas y se re-pregunta, es rejection sampling. Registrar tasa de rechazo por agente.

### V. Artefactos de medición
15. **Métricas que definen su propia respuesta:** "cooperativo" no debe etiquetarse por botón, sino por consecuencia (cuesta al actor, beneficia a otro, calculado sobre el estado del mundo).
16. **N = número de mundos, no de agentes.** Cinco agentes en una simulación no son cinco muestras: están acopladas.
17. **"61% vs 84%" no es un resultado:** sin ~20+ seeds por condición, intervalos de confianza y tamaño de efecto es ruido. Con 9 métricas × 4 condiciones habrá significancia por azar: **pre-especificar una métrica primaria**.
18. **Reproducibilidad falsa con API:** los proveedores cambian pesos sin avisar; temperature=0 no da determinismo real. Para claims fuertes, agentes en modelos locales congelados.

### VI. Sesgo del experimentador
19. **Jardín de senderos que se bifurcan:** ajustar el mundo hasta que produzca cooperación y reportarla como emergente. Defensa: **pre-registro con hash de configuración congelado + mundo reservado** que se corre una sola vez al final.
20. **Heider-Simmel:** los humanos ven intenciones en dos triángulos moviéndose. Defensa: **codificación ciega** (clasificar episodios sin saber la condición).
21. **HARKing:** once preguntas originales son once lentes post-hoc. Pre-especificar.

**La pregunta que falta en el documento original:** ¿Qué observación haría concluir que NO hubo emergencia? Sin esa respuesta escrita antes de correr, no es un experimento: es una demo con vocabulario científico.

**Definición operativa de emergencia propuesta por Claude** (un comportamiento cuenta como emergente solo si cumple las cuatro):
1. No existe como primitiva de acción.
2. Su vocabulario no aparece en el prompt ni en los nombres del mundo.
3. Es reproducible en ≥N seeds y supera a un baseline reactivo determinista en el mismo mundo.
4. No se reproduce con una regla más simple (si 20 líneas de código generan lo mismo, no se descubrió nada).

**Qué salva el proyecto (Claude):** el valor no está en el motor ni en Godot, sino en tener el único banco de pruebas con mundos de física contrafactual y prompts despojados de vocabulario humano. Es barato — requiere disciplina, no GPU.

---

## 5. Respuesta de ChatGPT (adopciones y matices)

Adopta como obligatorio:
1. **Baseline determinista** — comparar: mundo → agente determinista | agente LLM | LLM + memoria | LLM + memoria + world model. Si el determinista consigue lo mismo, la complejidad del LLM no era necesaria.
2. **Física invertida** — obj_17 en universo A (centro cae, borde estable) y universo B (inverso), sin contarlo. Convierte world modeling en hipótesis comprobable.
3. **Agente oráculo** — veterano vs nuevo + información equivalente. Si funcionan igual, hubo adquisición de información, no aprendizaje estratégico.
4. **N = mundos** — condición A con seeds 001..030, condición B con seeds 001..030. La unidad experimental es el mundo independiente.
5. **Pre-registro + mundo reservado** — antes de ejecutar: qué resultado aceptaría/rechazaría la hipótesis; no cambiar las reglas porque el resultado sea aburrido.

Matiz sobre "tres LLMs no son peer review": correcto, pero los LLMs son generadores de hipótesis y detectores de fallos, no autoridad. La validación real será: código + experimento reproducible + controles + datos.

**Redefinición del proyecto:** no es "crear una sociedad de agentes" ni "un mundo virtual con IA" — es construir un **banco de pruebas para distinguir comportamiento emergente de comportamiento inducido**.

---

## 6. Crítica de Zod a la crítica de Claude

**Veredicto:** ~17/21 correctas y accionables, 3-4 matizables, 0 descartables. Puntos más fuertes: #1 (vocabulario), #2 (primitivas), #10 (física invertida), #16 (N=mundos), #19 (pre-registro).

**Matices:**
- **#18 (reproducibilidad local obligatoria):** diagnóstico correcto, prescripción exagerada. Se exige robustez estadística (≥N seeds, distribución documentada), no determinismo bit a bit. API con registro riguroso (provider, modelo, versión, temperatura, fecha, hash de prompt) da reproducibilidad estadística aceptable para v0.1. Local congelado se reserva para claims fuertes.
- **#12 (placebo de world model):** el "razonamiento irrelevante" como placebo introduce otro confound. Mejor: **presupuesto de tokens fijo por decisión** en ambas condiciones.
- **#16 en la práctica:** análisis multinivel (mixed-effects) puede rescatar mundos correlacionados si el presupuesto no alcanza, pero exige más supuestos. Para v0.1: N=mundos directo.
- **Definición de emergencia:** la condición 4 ("regla más simple") debe **pre-especificarse** en el pre-registro, no descubrirse post-hoc, o es otra forma de HARKing. "20 líneas" es un proxy, no un criterio formal.

**Lo que falta (ni Claude ni ChatGPT lo cubrieron):**
1. **Presupuesto cuantificado:** ~30 mundos × 4 condiciones × 100 días × 5 agentes × ~5 decisiones/día ≈ **300.000 llamadas al modelo**. Hay que dimensionarlo antes de congelar.
2. **El prompt como instrumento científico:** versionado con hash, en git, congelado. Es la variable más frágil del diseño.
3. **Orden de turnos en el tick** (quién actúa primero) — confound silencioso.
4. **La comunicación debe costar:** si hablar es gratis, el discurso cooperativo es ruido. La comunicación debe consumir energía/tokens para ser una decisión económica.
5. **Calibración de la percepción** (golden tests: el agente solo ve lo que debe).
6. **Baseline reactivo justo:** la mejor política simple posible con la misma información, no una heurística cualquiera (si es malo, la comparación favorece al LLM injustamente).
7. **Dos ejes de reproducibilidad:** seed del mundo (determinista) vs estocasticidad del modelo (estadística). Documentar ambos por separado.

---

## 7. Protocolo experimental propuesto v0.1 (borrador para revisión de Opus 5)

1. **Hipótesis:** un agente LLM con memoria que experimenta en un mundo con reglas desconocidas construye un modelo útil de ese mundo (mejora su desempeño en la métrica primaria vs baseline determinista y vs oráculo).
2. **Hipótesis nula:** el agente LLM no difiere significativamente del baseline determinista; la ventaja de memoria/world-model desaparece frente al agente oráculo.
3. **Definición operacional de emergencia:** las 4 condiciones de Claude (ver §4), con la condición 4 pre-especificada.
4. **Mundo:** grid pequeño (p. ej. 30×30), ontología abstracta (R1..R5, struct_a), recetas arbitrarias, asignación randomizada por seed, física contrafactual (universos con reglas invertidas).
5. **Agentes:** 5, mismo modelo, objetivos = funciones de utilidad diferenciadas (pesos), percepción parcial calibrada, memoria episódica/social/semántica básica.
6. **Baselines:** (a) agente determinista reactivo (mejor política simple posible con misma información), (b) agente oráculo (toda la información en t=0).
7. **Variables independientes:** presencia de memoria, presencia de world model, ontología (semántica vs abstracta), reglas físicas (normal vs invertida).
8. **Métrica primaria (única, pre-especificada):** diferencia de desempeño entre agente-con-memoria y agente-oráculo en mundo contrafactual (mide construcción de modelo del mundo vs prior del modelo). Métricas secundarias: survival_rate, productividad, tasa de cooperación por consecuencia, tasa de rechazo del validador, prediction error en forced-choice probes.
9. **Controles:** prompts congelados y versionados, presupuesto de tokens fijo por decisión, orden de turnos fijado por seed, comunicación con costo, tasa de rechazo registrada.
10. **Seeds:** ≥20 por condición; N = mundos independientes, no agentes.
11. **Análisis estadístico:** pre-registrado; CI + tamaño de efecto; corrección por comparaciones múltiples; análisis de trayectorias individuales (no promedios poblacionales).
12. **Criterio de falsación:** escrito antes de correr. Pregunta: ¿qué observación nos haría concluir que no hubo emergencia?
13. **Presupuesto máximo:** fijado antes de correr (cómputo + API).
14. **Reglas que NO podremos modificar tras el pre-registro:** hipótesis, métrica primaria, prompts, ontología, config de mundo, análisis. Mundo de desarrollo (para iterar) separado del **mundo reservado** (una sola ejecución al final, con configuración congelada).

---

## 8. Preguntas para Opus 5 (se solicita respuesta adversarial, no complaciente)

1. ¿Qué críticas de Claude considera **exageradas o incorrectas**? ¿Cuáles se le escapan a todos nosotros?
2. ¿La **definición operacional de emergencia** (4 condiciones) es defendible? ¿La modificaría o la simplificaría?
3. ¿El **baseline determinista** propuesto es justo? ¿Cómo especificarlo para que la comparación no favorezca al LLM?
4. ¿El enfoque **N=mundos** es correcto para v0.1? ¿Cuántas seeds como mínimo para un claim interno vs un claim publicable?
5. ¿La **física invertida** como contrafactual es suficiente para probar world modeling? ¿Qué contrafactuales adicionales diseñaría?
6. ¿El **presupuesto estimado (~300K llamadas)** es aceptable? ¿Cómo reducirlo sin perder poder estadístico?
7. ¿La **métrica primaria propuesta** es la correcta? ¿Cuál usaría usted?
8. ¿Qué **análisis estadístico** pre-registraría?
9. ¿El diseño del agente (percepción, memoria, utilidad) tiene **confounds no cubiertos**?
10. **Veredicto final:** ¿procede el diseño/implementación con este protocolo, o qué cambiaría antes?

**Regla de la solicitud:** señalar fallos sobre elogiar aciertos. Si el protocolo tiene un agujero fatal, decirlo directamente.
