# WorldLab

Laboratorio experimental de agentes autónomos en un mundo 2D controlado.
Objetivo: **banco de pruebas para distinguir comportamiento emergente de comportamiento inducido** en agentes de IA.

## Estado

- **Fase 0 (en curso):** motor Python headless — estado del mundo, invariantes, validación de acciones, determinismo por hash. *Sin ontología todavía (diseño: Opus).*
- **Fases siguientes:** baseline determinista → visor HTML → agente LLM → piloto → pre-registro → corrida confirmatoria.

## Documentos

- `docs/WORLDLAB-revision-para-opus5.md` — consolidación de todas las rondas de revisión (ChatGPT, Zod, Claude, Opus 5) + protocolo v0.1 borrador.

## Reglas de oro (concepto v0.1 §5)

- El LLM **propone** acciones; el World Engine **valida** y solo entonces ejecuta.
- La realidad del mundo es autoritativa; la percepción del agente es un subconjunto.
- Determinismo: misma seed + mismas acciones ⇒ mismo hash de estado.

## Desarrollo

```bash
# venv (Python 3.12 de Homebrew)
/opt/homebrew/bin/python3.12 -m venv .venv
.venv/bin/pip install pytest
.venv/bin/python -m pytest tests/ -v
```

## Ver una corrida (visor)

`viewer.html` es un **panel de instrumentos**, no un reproductor: antes de que
nada se mueva dice si la corrida es confiable. Un archivo, cero dependencias,
cero red — abre igual desde `file://` que servido.

```bash
# 1. generar una demo (o usar una de data/bronze/ o data/silver/piloto/)
.venv/bin/python -m ai.run_demo 15 1

# 2. arrastrar el .jsonl al navegador
open viewer.html

# 3. o servir la carpeta y enlazar la corrida directamente
python3 -m http.server 8787
# http://localhost:8787/viewer.html?file=data/silver/piloto/piloto_baseline_empirico_12_s1_seed1.jsonl
```

Una corrida vive en **tres archivos**. El visor los lee todos: arrástrelos
juntos, o con `?file=` los busca por nombre.

| archivo | qué aporta |
|---|---|
| `<exp>_seed<N>.jsonl` | el mundo, los agentes y los eventos |
| `<exp>_seed<N>_traces.jsonl` | qué vio y qué respondió el modelo, por tick |
| `<exp>_probes.jsonl` | el exit probe — **ojo: sin el sufijo `_seed<N>`** |

Lo que el panel responde de un vistazo:

- **Anunciadores** (arriba a la derecha) — verde = medido por el motor,
  ámbar = derivado por el visor. Avisan si falta el probe, si faltan trazas, si
  hay agentes subexpuestos o si un filtro está ocultando datos. Son botones:
  llevan al instrumento que los explica.
- **Exposición** — ticks vividos en cada cruce región × fase. Si una celda base
  marca 0, el probe de ese agente no es interpretable, y lo dice.
- **Calibración** — el exit probe: aguja blanca = lo que el agente predijo,
  índice ámbar = la verdad del motor. Azar ≈ 17%.
- **Tripulación** — clic en un agente abre su decisión: observación, acción
  propuesta y respuesta cruda del modelo.

Teclado: espacio reproduce, ←/→ un momento (con Shift, diez), Inicio/Fin a los
extremos.

Los cuatro símbolos se distinguen por **forma** además de color, y los nombres
legibles (`comida`, `agua`…) se marcan como *alias solo del visor*: el modelo
nunca los ve.

## Agentes LLM (fase 2)

```bash
# demo con 5 agentes LLM (qwen2.5:7b local vía Ollama)
.venv/bin/python -c "
import sys; sys.path.insert(0,'.')
from ai.world_state import WorldConfig, Entity
from ai.model_adapter import LLMClient
from ai.llm_agent import LLMAgent
from ai.simulate import Simulator, make_llm_policy
cfg = WorldConfig(width=30, height=30, days=6, ticks_per_day=24, energy_per_tick=0.3)
cfg.energy_per_unit['food']=8.0; cfg.energy_per_unit['water']=5.0
client = LLMClient(backend='ollama', model='qwen2.5:7b', max_tokens=120)
goal='Sobrevive. Si tienes hambre, busca comida. Explora y recolecta recursos.'
agents={f'a{i}': LLMAgent(f'a{i}', client, goal=goal, think_every=24, hunger_threshold=35.0) for i in range(5)}
policy=make_llm_policy(agents)
sim=Simulator(cfg, policy, 'data/bronze', 'llm_demo', log_interval=12, resource_density=0.10,
              resource_kinds=['food','wood','stone','water'])
res=sim.run([Entity(eid=f'a{i}',kind='agent',x=5+i*3,y=5) for i in range(5)], seed=1)
print(res.to_dict())
"
```

El archivo resultante (`data/bronze/llm_demo_seed1.jsonl`) se ve en `viewer.html` como la demo determinista.
Los agentes LLM usan `qwen2.5:7b` (local, gratuito) o cualquier modelo vía `WORLDLAB_LLM_*` env vars (backend `openai`).

### Modelos y costo medido (local, M2 16GB)
| Modelo | tok/s | Decisión de agente | Uso |
|---|---|---|---|
| qwen2.5:7b | ~35 | ~1.5s (max_tokens 120) | **Recomendado para agentes** — JSON directo |
| qwen3:8b | ~31 | 19-38s (razona demasiado) | NO para agentes en v0.1 |
| DeepSeek API | API | ~1-2s | Alternativa remota (configurable) |
