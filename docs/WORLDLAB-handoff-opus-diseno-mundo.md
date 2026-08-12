# WorldLab — Handoff de diseño del mundo para Opus

**Versión:** 0.3 (handoff de motor a diseño)
**Fecha:** 2026-08-11
**De:** Zod (agente de ingeniería, Hermes)
**Para:** Opus 5 (diseño del mundo + protocolo)
**Estado:** Motor fase 0-1 construido y verificado (39 tests). El diseño de la ontología queda en sus manos, según la división acordada.

---

## 1. Estado actual del proyecto (verificado)

Repositorio: `~/Proyectos/worldlab/` (git, 5 commits)
- **Motor headless Python** (`ai/world_state.py`): grid NxN, entidades, agentes con energía/inventario, percepción limitada por radio, validador de acciones, RNG sembrado, hash de estado determinista.
- **Acciones económicas** (primitivas físicas, NO semánticas): `move`, `gather`, `consume`, `drop`, `pickup`, `give`, `build`, `talk` (con costo energético). **No existe `trade()`** — si emerge intercambio, se construye desde drop/pickup/give.
- **Logger JSONL** (`ai/logger.py`): eventos + snapshots + agent traces. Base del replay y del visor.
- **Baseline determinista paramétrico** (`ai/baseline.py`): política greedy con 3 parámetros (`eat_threshold`, `build_min`, `exploration`) + optimización por grid search (`ai/simulate.py`).
- **Visor HTML** (`viewer.html`): acuario con scrubber temporal, leyenda, log en español, panel de agentes. Verificado en navegador.

**Suite de tests:** 39/39 pasando. Determinismo probado: misma seed + mismas acciones ⇒ mismo hash de estado.

## 2. Reglas de oro (no negociables)

1. El LLM propone acciones en JSON; el **World Engine valida** y solo entonces ejecuta. El LLM nunca modifica el estado directamente.
2. La realidad del mundo es autoritativa; la percepción del agente es un subconjunto (`visible_to(radius)`).
3. Reproducibilidad: misma seed + mismas acciones ⇒ mismo estado final.
4. El orden de turnos se fija por seed (ablation de órdenes = experimento aparte).

## 3. La interfaz que su diseño debe respetar (para enchufar sin reescribir)

### WorldConfig (`ai/world_state.py`)
```python
@dataclass
class WorldConfig:
    width: int = 30
    height: int = 30
    days: int = 100
    ticks_per_day: int = 48
    energy_per_tick: float = 0.5      # metabolismo base
    move_energy: float = 1.0
    energy_per_unit: dict[str, float] # conversión recurso -> energía (p.ej. {"food": 8.0})
    seed: int = 1
```

### Acciones disponibles (firma exacta)
- `move(eid, dx, dy)` — validado: límites, bloqueo, energía
- `gather(eid, target_eid, amount)` — requiere recurso adyacente con `amount > 0`
- `consume(eid, rkind, amount)` — inventario → energía (`energy_per_unit`)
- `drop(eid, rkind, amount)` — deja recurso en el suelo
- `pickup(eid, target_eid, amount=None)` — toma del suelo (celda/adyacente)
- `give(eid, target_eid, rkind, amount)` — transfiere a agente adyacente
- `build(eid, structure, x, y, materials)` — consume materiales del inventario, crea objeto en celda adyacente libre
- `talk(eid, message, cost=1.0)` — comunicación con costo energético

### Scatter de recursos
```python
world.scatter_resources(count, kind="resource", resource_kinds=["food","wood","stone","water"])
```
- `count` = densidad × celdas del grid (la demo usó 12%; el mundo reservado usará la que usted defina)
- `resource_kinds` asigna tipo; la demo usó nombres legibles para el visor

## 4. Decisiones de diseño que le corresponden (sesión con el Comandante)

### 4.1 Ontología abstracta (crítica #1 de Claude)
- Definir los recursos R1..R5 (o n recursos) con **nombres sin semántica humana**.
- Recetas de crafting **arbitrarias** (no intuitivas: R2+R3 → R4).
- Asignación randomizada por seed para que el modelo no decodifique roles por correlación.

### 4.2 Física contrafactual (crítica #10 de Claude / exigencia de Opus)
- Universo A: objetos en el borde NO caen, los del centro sí.
- Universo B: inverso.
- Regla sin análogo lingüístico (p.ej. dos recursos que se aniquilan al estar adyacentes).
- Cambio de régimen a mitad de simulación (la física se invierte en el día N sin aviso) — mide re-aprendizaje.
- **El test de world modeling NO es "aprendió la física invertida" sino transferencia composicional**: aprende la regla en situación A y la aplica en situación B que solo se resuelve componiéndola con otra.

### 4.3 Función de las estructuras
- **Hallazgo del desarrollo:** hoy las casas NO dan beneficio (solo bloquean celdas). El baseline construye sin parar (20 casas inútiles en 15 días). Decisión: ¿las estructuras ganan función (refugio nocturno, almacenamiento, protección)? Esa función cambia el comportamiento y es variable del diseño.

### 4.4 Perfiles de utilidad (crítica de Opus: asimetría de utilidades)
- Fijar perfiles de utilidad por agente y **variar solo el mundo** entre seeds — no variar los perfiles junto con el mundo (confound).

### 4.5 Densidad de recursos, regeneración, presión de escasez
- Definir densidad del mundo reservado (la demo usó 12% para que fuera visible; el experimento puede requerir menos).
- ¿Los recursos se regeneran? ¿A qué tasa? (afecta la presión de escasez, que es la variable que induce comportamiento).

### 4.6 Comunicación
- `talk` ya tiene costo energético. Decidir: ¿mensajes estructurados o texto libre? ¿qué ve un agente de lo que dicen otros (radio de audición)?

## 5. Restricciones del protocolo a respetar

- **Métrica primaria pre-especificada (Opus):** LE = (memoria − sin_memoria) / (oráculo − sin_memoria), medida en mundo de física contrafactual.
- **N = mundos independientes, no agentes.** Claim interno: 10-15 mundos; el N definitivo sale del piloto (8-10 mundos × 3 condiciones) que Zod ejecutará después de su diseño.
- **Baselines:** (a) determinista paramétrico optimizado (ya implementado, falta optimizar), (b) oráculo que recibe las **reglas del mundo** (no una traza) — techo bien definido.
- **Pre-registro:** se congela DESPUÉS del piloto, no antes (corrección de Opus: el N sale de σ entre mundos).
- **Mundo de desarrollo vs mundo reservado:** el desarrollo se itera libremente; el reservado se corre UNA vez al final con configuración congelada.
- **Prompts como instrumento:** versionados, con hash, en git, congelados al pre-registrar.
- **Todas las condiciones de una comparación se corren intercaladas en la misma ventana temporal** (deriva temporal del proveedor — Opus).

## 6. Hallazgos del desarrollo (datos reales, útiles para el diseño)

| Hallazgo | Dato | Implicación |
|---|---|---|
| Baseline sin optimizar mata agentes | 0/5 sobreviven, 97% acciones rechazadas | El baseline DEBE optimizarse antes de comparar (hombre de paja) |
| Baseline optimizado básico | 5/5 sobreviven, 20 casas, 84% rechazo | Aun torpe: intenta moverse a celdas bloqueadas, construye sin propósito |
| Tasa de rechazo del validador | 84-97% | Métrica a registrar por agente (crítica #14) — el validador "hace el trabajo" |
| Agentes se paran sobre recursos | 4/5 en celdas con recursos al día 16 | No bloquean; visual OK tras fix de capas |
| 20 casas para 5 agentes | a2 construyó 8 | Comportamiento sin propósito = dato medible contra el LLM |

## 7. Preguntas para la sesión de diseño con el Comandante

1. ¿Cuántos recursos (5 como R1..R5?) y qué recetas arbitrarias propone? (para que el Comandante las apruebe)
2. ¿Qué estructuras existen y qué función tienen? ¿Casa = refugio nocturno que reduce metabolismo?
3. ¿Qué perfiles de utilidad concreta (pesos) para 5 agentes? (variando SOLO el mundo entre seeds)
4. ¿Densidad de recursos y regeneración del mundo reservado?
5. ¿La comunicación es texto libre o estructurada? ¿Radio de audición?
6. ¿El mundo de física contrafactual se implementa como config de WorldConfig (reglas de caída) o requiere nuevas primitivas del motor? — si requiere primitivas, avisar a Zod para extender el motor.

## 8. Entregables que se esperan de usted

1. **Especificación de ontología** (recursos, recetas, estructuras, física) en formato que Zod pueda convertir a config + validadores.
2. **Perfiles de utilidad** de los 5 agentes.
3. **Revisión del pre-registro** cuando Zod entregue los datos del piloto (σ, MDE, N justificado).
4. **Sesión de diseño con el Comandante** para las decisiones de 4.1-4.6 (él decide, usted propone).

---

**Nota de Zod:** el motor espera su diseño. Cuando lo tenga, lo convierto a config + tests y corro el piloto (fase 3). La pelota está en su cancha.
