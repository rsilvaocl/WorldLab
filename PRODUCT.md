# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Two audiences read the same surface, and the design must serve both without a mode switch:

1. **El investigador (usuario primario).** Ingeniero en computación que corre el laboratorio
   solo, en un Mac M2 de 16GB, con modelos locales (Ollama / qwen2.5:7b) y APIs remotas.
   Situación: acaba de terminar una corrida y necesita responder *¿esta corrida sirve o está
   rota?* antes de gastar horas en la siguiente. Depura agentes, no admira gráficos.
2. **El revisor externo.** Alguien que nunca leyó el protocolo — un profesor del diplomado,
   un colega, un lector del repo. Debe entender qué se está probando y qué pasó sin abrir
   `docs/`. No conoce la jerga (fase, región, cruce retenido, probe de composición).

## Product Purpose

WorldLab es un banco de pruebas para **distinguir comportamiento emergente de comportamiento
inducido** en agentes LLM. Un mundo 2D determinista, cinco agentes, y un experimento con una
casilla retenida. Éxito = poder afirmar, con evidencia auditable, que un agente compuso dos
reglas que nunca vio juntas — o que no lo hizo.

El visor (`viewer.html`) es la única superficie visual del proyecto. Su trabajo no es
"reproducir una simulación": es **hacer auditable una corrida**. Un visor que deja creer que
una corrida sirve cuando no sirve es un fallo de producto, no un fallo estético.

## Positioning

El mecanismo que ningún visor de simulación vecino puede copiar: **la casilla nunca vivida**.
El mundo se construye para que un agente solo pueda vivir 3 de las 4 combinaciones
(región × fase); la cuarta (región B en fase oscura) está cerrada por barrera. Al final se le
pregunta por esa cuarta. Como nunca estuvo ahí, no hay nada que recordar: solo acierta quien
entendió que la región suma un término y la fase otro, y los compone.

La evaluación no es binaria: se discretiza el cambio de energía en 6 niveles, así que el azar
cae a ~17%.

## Operating Context

- Se abre local, sin build, sin servidor, sin dependencias: `open viewer.html` y se arrastra
  un `.jsonl`. También acepta `?file=<ruta>` para enlazar corridas.
- Una corrida vive en **tres archivos hermanos** en disco:
  | archivo | contenido | lo lee el visor hoy |
  |---|---|---|
  | `<exp>_seed<N>.jsonl` | `meta` + `event` + `snapshot` | sí |
  | `<exp>_seed<N>_traces.jsonl` | decisión por tick del LLM: `observation`, `proposed_action`, `raw_response`, `model`, `reason`, `sleep_ticks` | no |
  | `<exp>_probes.jsonl` | el exit probe: `region`, `phase`, `rkind`, `never_lived`, `predicted_energy_change`, `truth_energy_change`, `predicted_level`, `truth_level`, `sign_correct`, `level_correct`, `absolute_error` | no |
  Nota de nomenclatura: **probes NO lleva el sufijo `_seed<N>`**; traces sí.
- Directorios: `data/bronze` (demos), `data/silver/piloto` (el piloto real: 96 mundos +
  `piloto_analysis.json` + `piloto_summary.json`), `data/gold` (vacío).
- Condiciones experimentales: `sin_memoria`, `memoria`, `oraculo`, `baseline_empirico`.
  Densidad de recursos 4 / 7 / 12 %. Semillas 1..8.

## Capabilities and Constraints

- **Cero dependencias, un solo archivo.** Sin build, sin CDN, sin fuentes remotas: el visor
  tiene que abrir desde `file://` igual que desde un servidor. Esto es una restricción dura.
- El `.jsonl` puede venir de un tercero: **todo lo que sale del archivo se escapa antes de
  tocar el DOM**. El repo es público.
- Los símbolos del mundo son **opacos** (`S1..S4`). Los nombres legibles (`comida`, `agua`…)
  vienen de `meta.resource_names` y existen **solo para el visor** — el modelo nunca los ve.
  Mostrarlos como si fueran verdad del mundo es una mentira de producto.
- `meta` es heterogéneo entre generaciones de datos: las corridas viejas (`demo_d15_s1`) no
  traen `phase_ticks`, `n_phases` ni `region_split`. El visor **deriva** fase y región cuando
  faltan. Derivar sin decirlo es la falla de honestidad más grave de la superficie.
- Determinismo: misma semilla + mismas acciones ⇒ mismo hash de estado. La corrida es un
  objeto reproducible, no un stream.
- Niveles de magnitud del probe (`ai/probe.py`): `0` pérdida grande (≤ −8), `1` pérdida media
  (≤ −3), `2` pérdida pequeña (< 0), `3` ganancia pequeña (< 3), `4` ganancia media (< 8),
  `5` ganancia grande (≥ 8).
- Escala: mundo 30×30, ~20 días × 24 ticks, cientos de snapshots y miles de eventos por
  corrida. El render corre en `<canvas>` 2D.

## Brand Commitments

- Nombre: **WorldLab**. Interfaz en español (usted/imperativo neutro, no "tú").
- `assets/logo.jpg` existe y es del proyecto. El usuario pidió explícitamente que la marca de
  agua del logo **al centro del grid sea más grande**.
- Semántica de color ya establecida y no negociable como *significado* (su rendición sí es
  libre): **región A y región B deben ser distinguibles al instante**, y el ciclo claro/oscuro
  debe leerse sin etiqueta.
- Requisito nuevo del usuario: **los recursos deben distinguirse por forma, no solo por
  color.**

## Evidence on Hand

Real y en disco, listo para usar como material de diseño:

- 96 mundos del piloto con sus probes y trazas (`data/silver/piloto/`).
- `piloto_analysis.json`: `n_mundos`, `sigma_energia` por condición×densidad,
  `mundos_contaminados`, y `exposicion.subexpuestos` — agentes con exposición 0 en una celda,
  que **invalidan su propio probe**.
- `docs/BITACORA.md`, `docs/DECISIONES.md` y las rondas de revisión.

No existe todavía: `data/gold`, corrida confirmatoria, pre-registro. No inventar resultados,
tasas de acierto ni conclusiones que estos archivos no contengan.

## Product Principles

1. **La corrida es la unidad, no el frame.** Un visor que solo reproduce el tiempo obliga a
   reconstruir la conclusión de memoria. La superficie debe entregar el veredicto y dejar
   bajar al detalle, no al revés.
2. **Nada derivado se muestra como observado.** Fase, región y nombres de recursos son
   inferencias del visor; deben verse distintas de lo que el motor registró.
3. **Los fallos son datos.** Un intento rechazado dice más del agente que uno logrado.
   Esconderlos por defecto sesga la lectura.
4. **Doble lectura sin doble interfaz.** El titular lo entiende quien nunca leyó el protocolo;
   el detalle lo necesita quien depura. Misma pantalla.
5. **Sin dependencias, sin excusas.** La restricción de un archivo no autoriza menos oficio.

## Accessibility & Inclusion

- Interfaz en español, contraste WCAG AA como piso.
- **El color nunca puede ser el único portador de significado**: región, fase, tipo de recurso
  y éxito/fallo necesitan forma, posición o texto además de color. Esto es requisito explícito
  del usuario para los recursos y se extiende al resto por coherencia.
- Todo el recorrido primario (cargar, reproducir, recorrer el tiempo, inspeccionar un agente)
  debe completarse por teclado.
