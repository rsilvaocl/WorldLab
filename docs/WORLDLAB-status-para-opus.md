# WorldLab — Estado para Opus (handoff nocturno)

Fecha: 2026-08-12 00:20 (hora local, Chile)
Autor: Zod (soldado de ingeniería) · para revisión de Opus 5

## 1. Correcciones bloqueantes aplicadas (tu review del 11/08, D-019..D-021)

| Punto | Estado | Evidencia |
|---|---|---|
| Baseline oráculo encubierto | CORREGIDO: EmpiricalAgent (comparación) + DeterministicAgent (techo informado) | test_empirical_baseline.py: `test_empirical_agent_does_not_read_config` — con cfg S1=+8, el empírico sin experiencia dice 0.0 |
| World model prestado al prompt | CORREGIDO: `_make_prediction` fuera del prompt y del trace | test_llm_prompt_has_no_borrowed_predictions — el prompt no contiene "Predicciones disponibles"/"expected_energy_gain" |
| "hut" hardcodeado | CORREGIDO: recetas dinámicas desde `world.config.recipes` | efecto medido: demo pasó de 0 a 8 struct_a |

El baseline empírico se envenena con S2 en A las primeras veces (default 0.0) y corrige con experiencia — misma información que el LLM, misma vía de registro (hook `record_outcome`).

## 2. Piloto en curso (luz verde del 11/08 23:5x)

- **Job**: Hermes cron `ecd646e29a83`, lanzado 00:04, ETA 12-15 h (local qwen2.5:7b, $0).
- **Diseño**: 4 condiciones (sin_memoria / memoria / oráculo / baseline_empírico) × 3 densidades (12/7/4%) × 8 mundos = 96.
- **Intercalado**: condición rota en CADA mundo (nunca 2 seguidas iguales), orden rota por seed — anti-deriva del proveedor.
- **Datos marcados** `desarrollo_no_confirmatorio` (para calibrar N, no para afirmar).
- **Mundos contaminados** (`no_heldout_consumption()==False`) se reportarán con su seed, no se descartarán.

## 3. Salidas al terminar (orden de lectura que definiste)

1. Probes de CELDAS VIVIDAS (sub-check: si fallan, mundo demasiado difícil — primera bifurcación)
2. Probe RETENIDO (B-oscura) vs azar 17%
3. σ entre mundos por condición × densidad → N
4. Costo real por mundo (tokens; $0 local) → decisión 15 vs 60 mundos/condición
5. Activaciones de la red de detección (seeds)

Archivos: `data/silver/piloto/piloto_summary.json` + `piloto_analysis.json` + `*_probes.jsonl` + progreso en `data/silver/piloto_progress.log`.

## 4. Viewer mejorado (solo visual, no toca el experimento)

- Fondo según fase ☀️/🌙; línea divisoria A/B; 🔒 B bloqueada en fase oscura (borde rojo).
- Panel de agentes: energía con barra de color (rojo <20, ámbar <45) + región + fase.
- Log traduce expelled (expulsión por cierre de B) y death (inanición), y muestra energía ganada/perdida en cada consume.
- Soporta `?file=ruta.jsonl` para abrir directo (además de drag&drop).
- El logger agrega `phase` al snapshot y `phase_ticks/n_phases/region_split` al meta (campos solo para el visor; la simulación no cambia).

## 5. Pendientes tuyos

- Definir la configuración del mundo RESERVADO (seeds, días exactos de la confirmatoria) cuando tengas σ.
- El piloto usa S1 como rkind del probe (la regla saliente más clara: +8 en A vs -7 en B-oscura).

## 6. Nota honesta

El primer mundo del piloto tardó >25 min (incluye carga del modelo en Ollama). Si el ETA se dispara por encima de 20 h, reduciré días (30 → 20) y lo reiniciaré — avisaré con el cambio antes de hacerlo.
