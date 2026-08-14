"""WorldLab — Fase E: exposición DIRIGIDA (D-033).

Qué hace: garantiza que cada agente viva experiencias REALES de consumo en las
tres celdas accesibles (A-clara, A-oscura, B-clara) para cada símbolo puntuado,
antes de que corra el probe retenido.

Por qué existe. El gate de mundo midió que la exposición a B-clara no emerge de
esta ecología: 400 candidatas de tabla evaluadas, mejor fracción D-025 = 0,08
contra un umbral de 0,75; 38 de 60 trayectorias se asientan en A y no visitan B
ni una vez. Sin las tres celdas vividas, B-oscura no es una composición sino
una adivinanza — y el probe no mide lo que dice medir.

LA RESTRICCIÓN QUE DEFINE ESTE MÓDULO (Terra, D-033): la exposición NO puede
depender de que el agente elija bien. Si recibir el dato exigiera acertar un
`gather` o un `consume`, se reintroduciría ruido de API y de planificación
dentro de la fase que existe justamente para eliminarlo. Por eso aquí el MOTOR
coloca al agente, le entrega el recurso y ejecuta el consumo.

Por qué se ejecuta el consumo REAL en vez de inyectar el evento en el historial:
`world.consume()` calcula la ganancia con `cfg.consume_effects`, emite el Event
y ese Event es el que recibe `record_outcome`. Fabricar el evento a mano sería
fabricar recuerdos — y la condición `memoria` mide precisamente qué hace el
agente con recuerdos que el mundo le dio. La única vía honesta es que el mundo
se los dé de verdad.

Qué NO hace: no toca B-oscura (celda retenida, D-005), no altera la tabla de
efectos y no le dice al agente qué significan los números. Solo garantiza que
los haya visto.

Es IDÉNTICA en las 4 condiciones. `sin_memoria` es el control negativo
esperado: recibe las mismas experiencias y no puede retenerlas.
"""

from __future__ import annotations

import random
from typing import Any, Callable, Dict, List, Optional, Tuple

from .world_state import WorldState, Event

CELDAS_VIVIDAS: Tuple[Tuple[str, int], ...] = (("A", 0), ("A", 1), ("B", 0))
CELDA_RETENIDA: Tuple[str, int] = ("B", 1)
SIMBOLOS_PUNTUADOS: Tuple[str, ...] = ("S1", "S2", "S4")   # S3 es control (D-022)
REPETICIONES = 3      # = MIN_EXPOSURE de D-025: 3 consumos por celda


def _tick_de_fase(world: WorldState, phase: int) -> int:
    """Primer tick del día que cae en `phase`."""
    pt = world.config.phase_ticks
    if pt <= 0:
        return 0
    return phase * pt


def _celda_libre_en(world: WorldState, region: str,
                    rng: random.Random) -> Tuple[int, int]:
    """Una celda libre de la región pedida, elegida de forma determinista."""
    split = int(world.config.width * world.config.region_split)
    x0, x1 = (0, split - 1) if region == "A" else (split, world.config.width - 1)
    for _ in range(200):
        x = rng.randint(x0, x1)
        y = rng.randint(0, world.config.height - 1)
        if not world.entities_at(x, y):
            return x, y
    # sin celda libre tras 200 intentos: barrido determinista
    for x in range(x0, x1 + 1):
        for y in range(world.config.height):
            if not world.entities_at(x, y):
                return x, y
    raise RuntimeError(f"región {region} sin celdas libres")


def exponer_agente(world: WorldState, eid: str, agente: Any,
                   seed: int = 0,
                   simbolos: Tuple[str, ...] = SIMBOLOS_PUNTUADOS,
                   celdas: Tuple[Tuple[str, int], ...] = CELDAS_VIVIDAS,
                   repeticiones: int = REPETICIONES,
                   on_event: Optional[Callable[[Event], None]] = None
                   ) -> List[Dict[str, Any]]:
    """Entrega a `eid` las experiencias de consumo de la Fase E.

    Devuelve el registro de lo entregado, para auditar que la exposición
    ocurrió: es la evidencia de que el probe posterior es interpretable.
    """
    if CELDA_RETENIDA in celdas:
        raise ValueError(
            "la celda retenida (B-oscura) NO puede exponerse: es lo que el "
            "probe pregunta (D-005)")

    agent = world.agents[eid]
    ent = agent.entity
    rng = random.Random(seed)
    tick0, day0, pos0 = world.tick, world.day, (ent.x, ent.y)
    registro: List[Dict[str, Any]] = []

    # orden determinista e IDÉNTICO en las 4 condiciones (depende del seed,
    # no de la condición): que el orden sea el mismo elimina una diferencia
    # entre brazos que nadie querría tener que descartar después.
    plan = [(s, reg, ph) for reg, ph in celdas for s in simbolos]
    rng.shuffle(plan)

    for rkind, region, phase in plan:
        world.tick = _tick_de_fase(world, phase)
        assert world.phase() == phase, "la fase no quedó como se pidió"
        for _ in range(repeticiones):
            x, y = _celda_libre_en(world, region, rng)
            ent.x, ent.y = x, y
            assert world.region(ent.x, ent.y) == region
            agent.inventory[rkind] = agent.inventory.get(rkind, 0.0) + 1.0
            ev = world.consume(eid, rkind, 1.0)
            if ev.outcome != "ok":
                raise RuntimeError(
                    f"la exposición dirigida falló en ({rkind},{region},{phase}): "
                    f"{ev.detail}")
            if on_event is not None:
                on_event(ev)
            # el agente registra el resultado por la MISMA vía que en el bucle
            # normal: sin esto, `memoria` no recibiría nada de la Fase E
            rec = getattr(agente, "record_outcome", None)
            if callable(rec):
                rec(ev)
            registro.append({
                "eid": eid, "rkind": rkind, "region": region, "phase": phase,
                "energy_gain": ev.detail.get("energy_gain"),
                "position": [x, y],
            })

    world.tick, world.day = tick0, day0
    ent.x, ent.y = pos0
    return registro


def exponer_todos(world: WorldState, agentes: Dict[str, Any], seed: int = 0,
                  **kw) -> List[Dict[str, Any]]:
    """Fase E para todos los agentes vivos, en orden determinista."""
    registro: List[Dict[str, Any]] = []
    for i, eid in enumerate(sorted(agentes)):
        if eid not in world.agents:
            continue
        registro += exponer_agente(world, eid, agentes[eid], seed=seed + i, **kw)
    return registro


def cobertura(registro: List[Dict[str, Any]],
              simbolos: Tuple[str, ...] = SIMBOLOS_PUNTUADOS,
              celdas: Tuple[Tuple[str, int], ...] = CELDAS_VIVIDAS
              ) -> Dict[str, Any]:
    """¿La Fase E cubrió lo que prometió? Se reporta SIEMPRE junto al probe.

    Si la cobertura no es completa, el probe de composición vuelve a ser
    ininterpretable — que es exactamente lo que esta fase existe para evitar.
    """
    por_agente: Dict[str, set] = {}
    for r in registro:
        por_agente.setdefault(r["eid"], set()).add(
            (r["rkind"], r["region"], r["phase"]))
    esperado = {(s, reg, ph) for reg, ph in celdas for s in simbolos}
    completos = {e for e, v in por_agente.items() if v >= esperado}
    return {
        "agentes": len(por_agente),
        "agentes_con_cobertura_completa": len(completos),
        "cobertura_completa": bool(por_agente) and len(completos) == len(por_agente),
        "faltantes": {e: sorted(esperado - v) for e, v in por_agente.items()
                      if not v >= esperado},
        "consumos_totales": len(registro),
    }
