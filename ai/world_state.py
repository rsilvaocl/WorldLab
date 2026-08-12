"""WorldLab — núcleo del motor.

Fase 0: estado del mundo, invariantes y validación de acciones.
Sin ontología: el mundo concreto (recursos, recetas, física) se define por
config en la fase de diseño (Opus). Aquí solo la mecánica genérica:

  - grid NxN con entidades (agentes, recursos, objetos)
  - estado inmutable por tick (snapshot + eventos)
  - el LLM NUNCA modifica el estado: propone acciones, el validador decide
  - invariantes verificables: no-teletransporte, conservación de recursos,
    determinismo (misma seed + mismas acciones => mismo hash de estado)

Regla de oro (concepto v0.1 §5): el agente propone, el World Engine valida
y solo entonces ejecuta.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Entidades
# ---------------------------------------------------------------------------

@dataclass
class Entity:
    """Entidad base del mundo. eid es único dentro de una simulación."""
    eid: str
    kind: str                 # "agent" | "resource" | "object"
    x: int
    y: int
    attrs: Dict[str, Any] = field(default_factory=dict)

    def pos(self) -> Tuple[int, int]:
        return (self.x, self.y)


@dataclass
class AgentState:
    """Estado de un agente (lo que el motor sabe de él)."""
    entity: Entity
    energy: float
    inventory: Dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Eventos
# ---------------------------------------------------------------------------

@dataclass
class Event:
    """Un hecho registrado del mundo. Fuente única de verdad para replay y métricas."""
    day: int
    tick: int
    eid: str
    action: str
    outcome: str                 # "ok" | "invalid" | "impossible"
    detail: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps({
            "day": self.day, "tick": self.tick, "eid": self.eid,
            "action": self.action, "outcome": self.outcome, "detail": self.detail,
        }, sort_keys=True)


# ---------------------------------------------------------------------------
# Configuración del mundo
# ---------------------------------------------------------------------------

@dataclass
class WorldConfig:
    width: int = 30
    height: int = 30
    days: int = 100
    ticks_per_day: int = 48          # ~30 min por tick en escala simulada
    energy_per_tick: float = 0.5     # costo metabólico base por tick
    move_energy: float = 1.0
    seed: int = 1


# ---------------------------------------------------------------------------
# Estado del mundo
# ---------------------------------------------------------------------------

class WorldState:
    """Estado autoritativo del mundo. Toda mutación pasa por métodos validados."""

    def __init__(self, config: WorldConfig, initial_entities: List[Entity],
                 seed: int | None = None):
        self.config = config
        self.rng = __import__("random").Random(seed if seed is not None else config.seed)
        self.entities: Dict[str, Entity] = {}
        self.agents: Dict[str, AgentState] = {}
        self.day = 1
        self.tick = 0
        self.events: List[Event] = []
        for ent in initial_entities:
            self._place(ent)

    # -- colocación con validación --------------------------------------
    def _place(self, ent: Entity) -> None:
        if not (0 <= ent.x < self.config.width and 0 <= ent.y < self.config.height):
            raise ValueError(f"Entidad {ent.eid} fuera del grid: {ent.pos()}")
        if ent.eid in self.entities:
            raise ValueError(f"eid duplicado: {ent.eid}")
        if self.entities_at(ent.x, ent.y) and ent.kind != "resource":
            raise ValueError(f"Casilla ocupada en {ent.pos()}")
        self.entities[ent.eid] = ent
        if ent.kind == "agent":
            self.agents[ent.eid] = AgentState(entity=ent, energy=100.0)

    def scatter_resources(self, count: int, kind: str = "resource") -> None:
        """Coloca `count` recursos en celdas libres, usando el RNG sembrado.
        Misma seed => misma distribución. Recursos pueden coexistir en una celda."""
        placed = 0
        attempts = 0
        max_attempts = count * 20 + 100
        while placed < count and attempts < max_attempts:
            attempts += 1
            x = self.rng.randrange(self.config.width)
            y = self.rng.randrange(self.config.height)
            rid = f"r_{kind}_{placed}"
            self.entities[rid] = Entity(eid=rid, kind=kind, x=x, y=y,
                                        attrs={"amount": 10.0})
            placed += 1
        if placed < count:
            raise RuntimeError(f"Solo se pudieron colocar {placed}/{count} recursos")

    def entities_at(self, x: int, y: int) -> List[Entity]:
        return [e for e in self.entities.values() if e.x == x and e.y == y]

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.config.width and 0 <= y < self.config.height

    # -- acciones validables --------------------------------------------
    def can_move(self, eid: str, dx: int, dy: int) -> Tuple[bool, str]:
        ent = self.entities.get(eid)
        if ent is None:
            return False, "no_such_entity"
        if ent.kind != "agent":
            return False, "not_an_agent"
        nx, ny = ent.x + dx, ent.y + dy
        if not self.in_bounds(nx, ny):
            return False, "out_of_bounds"
        blockers = [e for e in self.entities_at(nx, ny) if e.kind != "resource"]
        if blockers:
            return False, "blocked"
        return True, "ok"

    def move(self, eid: str, dx: int, dy: int) -> Event:
        ok, reason = self.can_move(eid, dx, dy)
        if not ok:
            return self._event(eid, "move", "impossible", {"reason": reason})
        agent = self.agents[eid]
        if agent.energy < self.config.move_energy:
            return self._event(eid, "move", "impossible", {"reason": "no_energy"})
        ent = agent.entity
        ent.x += dx
        ent.y += dy
        agent.energy -= self.config.move_energy
        return self._event(eid, "move", "ok", {"from": (ent.x - dx, ent.y - dy),
                                               "to": (ent.x, ent.y)})

    def _event(self, eid: str, action: str, outcome: str,
               detail: Dict[str, Any]) -> Event:
        ev = Event(day=self.day, tick=self.tick, eid=eid,
                   action=action, outcome=outcome, detail=detail)
        self.events.append(ev)
        return ev

    # -- ciclo de tiempo -------------------------------------------------
    def advance_tick(self) -> None:
        """Avanza un tick: costo metabólico de todos los agentes."""
        for aid, agent in self.agents.items():
            agent.energy -= self.config.energy_per_tick
            if agent.energy <= 0:
                agent.energy = 0.0  # estado de inanición; muerte gestionada por regla de mundo
        self.tick += 1
        if self.tick >= self.config.ticks_per_day:
            self.tick = 0
            self.day += 1

    # -- determinismo ----------------------------------------------------
    def state_hash(self) -> str:
        """Hash canónico del estado. Misma seed + mismas acciones => hash idéntico."""
        payload = {
            "day": self.day, "tick": self.tick,
            "entities": sorted(
                (e.eid, e.kind, e.x, e.y, json.dumps(e.attrs, sort_keys=True))
                for e in self.entities.values()
            ),
            "agents": sorted(
                (aid, round(a.energy, 6),
                 json.dumps({k: round(v, 6) for k, v in a.inventory.items()}, sort_keys=True))
                for aid, a in self.agents.items()
            ),
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    # -- snapshot para percepción (subconjunto, nunca el estado completo) --
    def visible_to(self, eid: str, radius: int = 4) -> Dict[str, Any]:
        """Percepción limitada del agente: solo entidades dentro del radio."""
        ent = self.entities.get(eid)
        if ent is None:
            return {"error": "no_such_entity"}
        seen = []
        for other in self.entities.values():
            if abs(other.x - ent.x) <= radius and abs(other.y - ent.y) <= radius:
                seen.append({"eid": other.eid, "kind": other.kind,
                             "dx": other.x - ent.x, "dy": other.y - ent.y})
        return {"day": self.day, "tick": self.tick,
                "position": [ent.x, ent.y], "visible": seen}
