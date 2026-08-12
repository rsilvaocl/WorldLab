# WorldLab — Registro de Decisiones de Diseño

Formato: fecha · decisión · quién la tomó · estado

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

## D-011 · 2026-08-11 · Expulsión de regiones bloqueadas + integridad del held-out (Opus) · Aprobada
- Al entrar la fase oscura, los agentes en B son EXPULSADOS a la celda libre más
  cercana en región no bloqueada (búsqueda en espiral) — nadie puede vivir B-oscura.
- Red de detección permanente: `no_heldout_consumption()` — ningún consume ok en
  celda bloqueada. Test falla si se contamina el held-out por cualquier vía.
- Alfabeto simbólico reducido a 4 (`k1..k4`): el estimador de MI está sesgado al
  alza con alfabeto grande y pocos datos.
- Emergencia de señalización se mide con MI contra NULO POR PERMUTACIÓN (no contra cero).

## D-012 · 2026-08-11 · hear_radius > radio de visión: decisión escrita (Opus) · Aprobada
- `hear_radius` (6) > radio de visión (4): un agente puede OÍR a quien no ve.
- Decisión consciente y documentada, no accidente: crea situaciones interesantes
  (oír sin ver) y es parte del diseño del mundo.


## D-007 · 2026-08-11 · Orden de operaciones (Opus) · Aprobada
- Pre-registro DESPUÉS del piloto, no antes. El N sale de σ entre mundos (cálculo de potencia).
- Baseline determinista parametrizado y OPTIMIZADO (re-optimizado tras fixes de mecánica: D-001).
- Oráculo recibe las reglas del mundo (ground truth), no una traza reconstruida.
- Mundos de desarrollo vs reservado; condiciones intercaladas en misma ventana temporal.
