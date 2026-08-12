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
