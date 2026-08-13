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
from typing import Any, Callable, Dict, List, Optional, Tuple


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
    starvation_ticks: int = 0        # ticks consecutivos con energía en 0


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
    energy_per_unit: Dict[str, float] = field(default_factory=dict)  # conversión recurso->energía
    recipes: Dict[str, Dict[str, float]] = field(
        default_factory=lambda: {"struct_a": {"S3": 2.0, "S4": 1.0}})
    # --- condiciones cruzadas (diseño Opus: ¿una condición o dos?) --------
    phase_ticks: int = 0             # duración de cada fase en ticks; 0 = sin ciclo
    n_phases: int = 2                # p.ej. clara(0) / oscura(1)
    region_split: float = 0.5        # fracción del ancho: x < split => región A, resto B
    phase_barriers: Dict[Tuple[int, str], bool] = field(default_factory=dict)
                                     # (fase, región) -> bloqueada (no se puede ENTRAR)
    consume_effects: Dict[Tuple[str, str, int], float] = field(default_factory=dict)
                                     # (rkind, región, fase) -> energía ganada; override
    # --- ontología aprobada (spec 2026-08-11, §8) ---------------------------
    clusters_n: int = 0              # 8 cúmulos; 0 = sin cúmulos (scatter plano)
    clusters_radius: int = 3
    clusters_per_region: int = 4
    regen_per_day: float = 0.0       # regeneración por recurso, tope = carga inicial
    starvation_ticks: int = 48       # ticks consecutivos en energía 0 => muerte
    struct_effects: Dict[str, Dict[str, Any]] = field(default_factory=dict)
                                     # p.ej. {"struct_a": {"metabolism_factor": 0.5, "phase": 1, "range": 1}}
    max_message_symbols: int = 3     # longitud máx del mensaje simbólico
    vision_radius: int = 4           # radio de percepción (hear_radius 6 > visión: D-012)
    # --- comunicación simbólica (D-008: canal simbólico, decisión Comandante) --
    symbol_alphabet: List[str] = field(
        default_factory=lambda: [f"k{i}" for i in range(1, 5)])
    hear_radius: int = 6             # radio en el que otros agentes oyen talk()
    seed: int = 1


def build_separable_effects(
    base: Dict[str, float],
    delta_region: Dict[str, Dict[str, float]],
    delta_phase: Dict[str, Dict[int, float]],
) -> Dict[Tuple[str, str, int], float]:
    """Genera consume_effects a partir de una REGLA SEPARABLE (exigencia de Opus):

        efecto(r, región, fase) = base(r) + δ_región(r, región) + δ_fase(r, fase)

    Por qué: si los 4 valores de la tabla se eligen a mano, la celda retenida
    (B-oscura) es un hecho suelto imposible de componer — el test mediría suerte,
    no modelado. Con forma separable, las 3 celdas vividas determinan
    matemáticamente la cuarta:  B-oscura = A-oscura + (B-clara − A-clara).
    Quien compone las dos reglas acierta; quien solo memoriza, no tiene de dónde.
    """
    out: Dict[Tuple[str, str, int], float] = {}
    for r in base:
        for region in ("A", "B"):
            for phase in (0, 1):
                out[(r, region, phase)] = (
                    base[r]
                    + delta_region.get(r, {}).get(region, 0.0)
                    + delta_phase.get(r, {}).get(phase, 0.0)
                )
    return out


def separable_invariant_holds(effects: Dict[Tuple[str, str, int], float]) -> bool:
    """Invariante de separabilidad: para todo recurso,
    efecto(B,oscura) − efecto(B,clara) == efecto(A,oscura) − efecto(A,clara).
    Si se rompe, el mundo dejó de ser aprendible y el test de composición
    dejó de significar nada (test permanente en test_crossed_conditions.py)."""
    for key in effects:
        r = key[0]
        if (r, "B", 0) not in effects or (r, "B", 1) not in effects \
           or (r, "A", 0) not in effects or (r, "A", 1) not in effects:
            continue
        if (effects[(r, "B", 1)] - effects[(r, "B", 0)]) != \
           (effects[(r, "A", 1)] - effects[(r, "A", 0)]):
            return False
    return True


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
        self._drop_seq = 0  # contador para eids opacos de recursos soltados
        self.inbox: Dict[str, List[Dict[str, Any]]] = {}  # mensajes oídos por agente
        # D-024: callback disparado cuando un agente ARRANCA la inanición
        # (primer tick con energía 0), ANTES de que desaparezca del mundo.
        # Permite capturar su estado de conocimiento final con un probe.
        self.on_starvation_start: Optional[Callable[[str, "WorldState"], None]] = None
        # CLONAR entidades iniciales: el motor nunca muta objetos del llamador.
        # Sin esto, reusar la misma lista entre simulaciones (p.ej. en el grid
        # search del baseline) contamina posiciones y colisiona.
        for ent in initial_entities:
            self._place(Entity(eid=ent.eid, kind=ent.kind, x=ent.x, y=ent.y,
                               attrs=dict(ent.attrs)))

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

    def scatter_resources(self, count: int, kind: str = "resource",
                          resource_kinds: Optional[List[str]] = None) -> None:
        """Coloca `count` recursos en celdas libres, usando el RNG sembrado.
        Misma seed => misma distribución. Recursos pueden coexistir en una celda.
        `resource_kinds` (p.ej. ["food","wood","stone"]) asigna tipo de recurso;
        si es None, queda sin tipo (ontología por definir)."""
        placed = 0
        attempts = 0
        max_attempts = count * 20 + 100
        while placed < count and attempts < max_attempts:
            attempts += 1
            x = self.rng.randrange(self.config.width)
            y = self.rng.randrange(self.config.height)
            rid = f"r_{kind}_{placed}"
            rkind = None
            if resource_kinds:
                rkind = resource_kinds[self.rng.randrange(len(resource_kinds))]
            attrs = {"amount": 10.0}
            if rkind:
                attrs["kind"] = rkind
            self.entities[rid] = Entity(eid=rid, kind=kind, x=x, y=y, attrs=attrs)
            placed += 1
        if placed < count:
            raise RuntimeError(f"Solo se pudieron colocar {placed}/{count} recursos")

    def seed_clusters(self, resource_kinds: List[str], density: float = 0.12) -> None:
        """Siembra en cúmulos (spec §3.2, requisito crítico de Opus).

        - clusters_n cúmulos, radio clusters_radius, per_region por región.
        - Cada cúmulo es de UN solo símbolo; los símbolos se reparten para que
          TODOS existan en AMBAS regiones (si S1 solo está en A, el agente nunca
          puede probarlo en B y no hay experimento).
        - Número total de recursos = density × celdas, repartidos entre cúmulos.
        - Posiciones sorteadas por seed (reproducibilidad).
        """
        cfg = self.config
        if cfg.clusters_n <= 0:
            self.scatter_resources(int(cfg.width * cfg.height * density),
                                   kind="resource", resource_kinds=resource_kinds)
            return
        n_clusters = cfg.clusters_n
        per_region = cfg.clusters_per_region
        radius = cfg.clusters_radius
        split = int(cfg.width * cfg.region_split)

        # asignar símbolo a cada cúmulo: per_region símbolos distintos por región
        # (con n=8, per_region=4, symbols=4 => cada región tiene los 4)
        cluster_symbols: List[Tuple[str, str]] = []  # (region, symbol)
        for region in ("A", "B"):
            for sym in resource_kinds:
                cluster_symbols.append((region, sym))

        # centros: sorteados por seed dentro de la región, con margen para el radio
        centers: List[Tuple[int, int]] = []
        for region, sym in cluster_symbols:
            if region == "A":
                x0, x1 = radius, split - radius - 1
            else:
                x0, x1 = split + radius, cfg.width - radius - 1
            if x1 <= x0:
                x0, x1 = 0, cfg.width - 1
            cx = self.rng.randint(x0, x1)
            cy = self.rng.randint(radius, cfg.height - radius - 1)
            centers.append((cx, cy))

        # repartir el total de recursos entre cúmulos
        total = int(cfg.width * cfg.height * density)
        per_cluster = max(1, total // n_clusters)
        remainder = total - per_cluster * n_clusters

        idx = 0
        for (region, sym), (cx, cy) in zip(cluster_symbols, centers):
            n_res = per_cluster + (1 if idx < remainder else 0)
            # colocar n_res recursos dentro del radio (Chebyshev), una por celda
            placed_in_cluster = 0
            attempts = 0
            while placed_in_cluster < n_res and attempts < n_res * 30 + 50:
                attempts += 1
                dx = self.rng.randint(-radius, radius)
                dy = self.rng.randint(-radius, radius)
                x, y = cx + dx, cy + dy
                if not self.in_bounds(x, y):
                    continue
                if self.entities_at(x, y):
                    continue
                rid = f"r_{sym}_{idx}_{placed_in_cluster}"
                amount = 10.0
                self.entities[rid] = Entity(eid=rid, kind="resource", x=x, y=y,
                                            attrs={"kind": sym, "amount": amount,
                                                   "initial_amount": amount,
                                                   "cluster": idx})
                placed_in_cluster += 1
            idx += 1

    def symbols_present_in_all_regions(self) -> bool:
        """Requisito crítico (spec §3.2): los 4 símbolos existen en ambas regiones."""
        per_region: Dict[str, set] = {"A": set(), "B": set()}
        for e in self.entities.values():
            if e.kind == "resource" and "kind" in e.attrs:
                per_region[self.region(e.x, e.y)].add(e.attrs["kind"])
        all_syms = set()
        for region in ("A", "B"):
            all_syms |= per_region[region]
        return all(len(all_syms & per_region[r]) == len(all_syms) and len(all_syms) > 0
                   for r in ("A", "B"))

    def entities_at(self, x: int, y: int) -> List[Entity]:
        return [e for e in self.entities.values() if e.x == x and e.y == y]

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.config.width and 0 <= y < self.config.height

    # -- condiciones cruzadas: fase + región (para world modeling) ---------
    def phase(self) -> int:
        """Fase actual (0=clara, 1=oscura...). Sin ciclo => siempre 0."""
        if self.config.phase_ticks <= 0:
            return 0
        return (self.tick // self.config.phase_ticks) % self.config.n_phases

    def region(self, x: int, y: int) -> str:
        """Región de una celda: A (izquierda) o B (derecha)."""
        return "A" if x < int(self.config.width * self.config.region_split) else "B"

    def _region_blocked(self, region: str, phase: int) -> bool:
        return bool(self.config.phase_barriers.get((phase, region), False))

    def ground_truth_effect(self, rkind: str, region: str, phase: int) -> float:
        """Efecto REAL de consumir `rkind` en (region, phase) según la config.
        Es la respuesta correcta objetiva del motor, usada por el probe de
        composición para comparar contra la predicción del agente."""
        key = (rkind, region, phase)
        if key in self.config.consume_effects:
            return self.config.consume_effects[key]
        return self.config.energy_per_unit.get(rkind, 5.0)

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
        # barrera de fase: bloquea CRUZAR hacia una región bloqueada en la fase
        # actual. Si ya estás dentro (p.ej. B al cambiar la fase), puedes
        # moverte dentro y salir — la barrera impide entrar, no congelar.
        if self._region_blocked(self.region(nx, ny), self.phase()):
            if self.region(ent.x, ent.y) != self.region(nx, ny):
                return False, "blocked_by_phase"
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

    # -- economía: recolectar / consumir / construir / comunicar ---------
    # Primitivas intencionalmente FÍSICAS, no semánticas (crítica #2 de Claude):
    # NO existe trade(). Existen gather, drop, pickup, give. Si emerge
    # intercambio condicionado a valor, eso es lo que observamos.

    def _adjacent(self, eid: str, target_eid: str) -> bool:
        ent, other = self.entities.get(eid), self.entities.get(target_eid)
        if ent is None or other is None:
            return False
        return abs(ent.x - other.x) + abs(ent.y - other.y) == 1

    def gather(self, eid: str, target_eid: str, amount: float = 1.0) -> Event:
        """Recolecta de un recurso adyacente O en la misma celda (distancia ≤ 1,
        consistente con pickup — bug corregido: antes exigía distancia == 1)."""
        ent, res = self.entities.get(eid), self.entities.get(target_eid)
        if ent is None or res is None:
            return self._event(eid, "gather", "impossible", {"reason": "no_such_entity"})
        if res.kind != "resource":
            return self._event(eid, "gather", "impossible", {"reason": "not_a_resource"})
        if abs(ent.x - res.x) + abs(ent.y - res.y) > 1:
            return self._event(eid, "gather", "impossible", {"reason": "not_adjacent"})
        avail = float(res.attrs.get("amount", 0.0))
        if avail <= 0:
            return self._event(eid, "gather", "impossible", {"reason": "depleted"})
        got = min(amount, avail)
        agent = self.agents[eid]
        rkind = res.attrs.get("kind", "generic")
        agent.inventory[rkind] = agent.inventory.get(rkind, 0.0) + got
        res.attrs["amount"] = avail - got
        return self._event(eid, "gather", "ok",
                           {"resource": rkind, "amount": got, "from": target_eid})

    def consume(self, eid: str, rkind: str, amount: float = 1.0) -> Event:
        """Come/bebe del inventario: recurso -> energía."""
        agent = self.agents.get(eid)
        if agent is None:
            return self._event(eid, "consume", "impossible", {"reason": "no_such_entity"})
        have = agent.inventory.get(rkind, 0.0)
        if have < amount:
            return self._event(eid, "consume", "impossible",
                               {"reason": "not_enough", "have": have, "need": amount})
        # conversión recurso -> energía. Si hay efecto cruzado (rkind, región, fase)
        # definido, lo usa; si no, la tabla plana energy_per_unit.
        ent = agent.entity
        key = (rkind, self.region(ent.x, ent.y), self.phase())
        if key in self.config.consume_effects:
            energy_gain = self.config.consume_effects[key] * amount
        else:
            energy_gain = self.config.energy_per_unit.get(rkind, 5.0) * amount
        agent.inventory[rkind] = have - amount
        agent.energy = min(agent.energy + energy_gain, 100.0)
        return self._event(eid, "consume", "ok",
                           {"resource": rkind, "amount": amount, "energy_gain": energy_gain,
                            "region": self.region(ent.x, ent.y), "phase": self.phase()})

    def drop(self, eid: str, rkind: str, amount: float) -> Event:
        """Suelta recurso del inventario en la celda actual (deja entidad en el suelo)."""
        agent = self.agents.get(eid)
        if agent is None:
            return self._event(eid, "drop", "impossible", {"reason": "no_such_entity"})
        have = agent.inventory.get(rkind, 0.0)
        if have < amount or amount <= 0:
            return self._event(eid, "drop", "impossible",
                               {"reason": "not_enough", "have": have})
        agent.inventory[rkind] = have - amount
        ent = agent.entity
        # eid OPACO (bug corregido): el tipo de recurso NO viaja en el id
        self._drop_seq += 1
        dropped = Entity(eid=f"e_{self._drop_seq:04d}", kind="resource",
                         x=ent.x, y=ent.y, attrs={"amount": amount, "kind": rkind,
                                                  "owner_dropped": eid})
        self.entities[dropped.eid] = dropped
        return self._event(eid, "drop", "ok", {"resource": rkind, "amount": amount})

    def pickup(self, eid: str, target_eid: str, amount: float | None = None) -> Event:
        """Toma recurso del suelo en la celda actual o adyacente."""
        ent, res = self.entities.get(eid), self.entities.get(target_eid)
        if ent is None or res is None:
            return self._event(eid, "pickup", "impossible", {"reason": "no_such_entity"})
        if res.kind != "resource" or "kind" not in res.attrs:
            return self._event(eid, "pickup", "impossible", {"reason": "not_dropped_resource"})
        if abs(ent.x - res.x) + abs(ent.y - res.y) > 1:
            return self._event(eid, "pickup", "impossible", {"reason": "not_adjacent"})
        avail = float(res.attrs["amount"])
        take = avail if amount is None else min(amount, avail)
        agent = self.agents[eid]
        rkind = res.attrs["kind"]
        agent.inventory[rkind] = agent.inventory.get(rkind, 0.0) + take
        res.attrs["amount"] = avail - take
        if res.attrs["amount"] <= 0:
            del self.entities[target_eid]
        return self._event(eid, "pickup", "ok", {"resource": rkind, "amount": take})

    def give(self, eid: str, target_eid: str, rkind: str, amount: float) -> Event:
        """Transfiere recurso a un agente adyacente. Primitiva física, no económica."""
        giver, receiver = self.agents.get(eid), self.agents.get(target_eid)
        if giver is None or receiver is None:
            return self._event(eid, "give", "impossible", {"reason": "no_such_agent"})
        if not self._adjacent(eid, target_eid):
            return self._event(eid, "give", "impossible", {"reason": "not_adjacent"})
        have = giver.inventory.get(rkind, 0.0)
        if have < amount or amount <= 0:
            return self._event(eid, "give", "impossible",
                               {"reason": "not_enough", "have": have})
        giver.inventory[rkind] = have - amount
        receiver.inventory[rkind] = receiver.inventory.get(rkind, 0.0) + amount
        return self._event(eid, "give", "ok",
                           {"resource": rkind, "amount": amount, "to": target_eid})

    def build(self, eid: str, structure: str, x: int, y: int) -> Event:
        """Construye una estructura en (x,y) adyacente. La RECETA vive en la
        config del mundo (WorldConfig.recipes), no en quien llama — un agente
        no puede declarar sus propios materiales (bug corregido: antes se
        construía gratis con materials={})."""
        agent = self.agents.get(eid)
        if agent is None:
            return self._event(eid, "build", "impossible", {"reason": "no_such_entity"})
        recipe = self.config.recipes.get(structure)
        if recipe is None:
            return self._event(eid, "build", "impossible",
                               {"reason": "unknown_recipe", "structure": structure})
        ent = agent.entity
        if abs(ent.x - x) + abs(ent.y - y) != 1:
            return self._event(eid, "build", "impossible", {"reason": "not_adjacent"})
        if not self.in_bounds(x, y):
            return self._event(eid, "build", "impossible", {"reason": "out_of_bounds"})
        if self.entities_at(x, y):
            return self._event(eid, "build", "impossible", {"reason": "cell_occupied"})
        for rkind, need in recipe.items():
            if agent.inventory.get(rkind, 0.0) < need:
                return self._event(eid, "build", "impossible",
                                   {"reason": "missing_material", "resource": rkind})
        for rkind, need in recipe.items():
            agent.inventory[rkind] -= need
        obj = Entity(eid=f"b_{structure}_{self.tick}_{eid}", kind="object",
                     x=x, y=y, attrs={"structure": structure})
        self.entities[obj.eid] = obj
        return self._event(eid, "build", "ok",
                           {"structure": structure, "at": [x, y],
                            "materials": dict(recipe)})

    def talk(self, eid: str, message: str, cost: float = 1.0) -> Event:
        """Comunicación SIMBÓLICA con costo energético (D-008).

        El mensaje debe ser una secuencia de símbolos del alfabeto del mundo
        (p.ej. "k7 k2 k9") SIN significado asignado. El lenguaje natural queda
        PROHIBIDO en el canal: reintroduciría la semántica humana que la
        ontología opaca eliminó (crítica #1 de Opus: "k7 k2 k9" no significa
        nada; si un símbolo correlaciona con un estado, eso es emergencia de
        señalización medible con información mutua).

        Los agentes dentro de hear_radius reciben el mensaje en su inbox.
        """
        agent = self.agents.get(eid)
        if agent is None:
            return self._event(eid, "talk", "impossible", {"reason": "no_such_entity"})
        if len(message) == 0:
            return self._event(eid, "talk", "impossible", {"reason": "empty"})
        if agent.energy < cost:
            return self._event(eid, "talk", "impossible", {"reason": "no_energy"})
        symbols = message.split()
        if not symbols:
            return self._event(eid, "talk", "impossible", {"reason": "empty"})
        alphabet = set(self.config.symbol_alphabet)
        for s in symbols:
            if s not in alphabet:
                return self._event(eid, "talk", "impossible",
                                   {"reason": "not_in_alphabet", "symbol": s})
        agent.energy -= cost
        ent = agent.entity
        # repartir en inbox a los agentes que oyen (radio de audición)
        for other in self.agents.values():
            if other.entity.eid == eid:
                continue
            dist = abs(other.entity.x - ent.x) + abs(other.entity.y - ent.y)
            if dist <= self.config.hear_radius:
                self.inbox.setdefault(other.entity.eid, []).append({
                    "tick": self.tick, "day": self.day,
                    "from": eid, "symbols": symbols, "distance": dist,
                })
        return self._event(eid, "talk", "ok", {"message": message, "cost": cost,
                                               "symbols": symbols})

    # -- ciclo de tiempo -------------------------------------------------
    def advance_tick(self) -> None:
        """Avanza un tick: metabolismo (con efecto de struct en fase oscura),
        contador de inanición (muerte a los starvation_ticks consecutivos),
        regeneración al cambiar de día, y expulsión de regiones bloqueadas."""
        phase = self.phase()
        for aid in list(self.agents.keys()):
            agent = self.agents.get(aid)
            if agent is None:
                continue  # murió durante la iteración previa
            # metabolismo con posible reducción por struct adyacente (fase oscura)
            factor = self._metabolism_factor(agent, phase)
            agent.energy -= self.config.energy_per_tick * factor
            if agent.energy <= 0:
                agent.energy = 0.0
                agent.starvation_ticks = getattr(agent, "starvation_ticks", 0) + 1
                # D-024: probe de salida — al PRIMER tick de inanición, antes
                # de que el agente desaparezca (muerte a los starvation_ticks).
                if agent.starvation_ticks == 1 and self.on_starvation_start:
                    try:
                        self.on_starvation_start(aid, self)
                    except Exception:
                        # el probe nunca puede tumbar el mundo
                        pass
                if agent.starvation_ticks >= self.config.starvation_ticks:
                    self._kill_agent(aid)
            else:
                agent.starvation_ticks = 0
        # limpiar agentes muertos del dict (ya removidos por _kill_agent)
        self.tick += 1
        if self.tick >= self.config.ticks_per_day:
            self.tick = 0
            self.day += 1
            self._regen_resources()
        self._expel_agents_from_blocked_regions()

    def _metabolism_factor(self, agent: AgentState, phase: int) -> float:
        """Factor metabólico por estructuras adyacentes (spec §3.6):
        struct_a reduce el metabolismo ×0.5 SOLO en fase oscura."""
        factor = 1.0
        ent = agent.entity
        for other in self.entities.values():
            if other.kind != "object":
                continue
            effect = self.config.struct_effects.get(other.attrs.get("structure", ""))
            if effect is None:
                continue
            if effect.get("phase") is not None and phase != effect["phase"]:
                continue
            rng = effect.get("range", 1)
            if abs(other.x - ent.x) + abs(other.y - ent.y) <= rng:
                factor *= float(effect.get("metabolism_factor", 1.0))
        return factor

    def _kill_agent(self, aid: str) -> None:
        """Muerte por inanición sostenida (spec §3.5): el agente sale del mundo
        y su inventario cae al suelo en su última celda."""
        agent = self.agents.get(aid)
        if agent is None:
            return
        ent = agent.entity
        self._event(aid, "death", "ok", {"reason": "starvation",
                                         "at": [ent.x, ent.y],
                                         "energy": round(agent.energy, 1)})
        for rkind, amt in agent.inventory.items():
            if amt <= 0:
                continue
            self._drop_seq += 1
            self.entities[f"e_{self._drop_seq:04d}"] = Entity(
                eid=f"e_{self._drop_seq:04d}", kind="resource",
                x=ent.x, y=ent.y, attrs={"amount": amt, "kind": rkind,
                                         "owner_dropped": aid})
        del self.entities[aid]
        del self.agents[aid]

    def _regen_resources(self) -> None:
        """Regeneración (spec §3.4): cada recurso recupera regen_per_day por día,
        con tope en su carga inicial (initial_amount). El mundo alcanza estado
        estable; la presión la fija la densidad, no el reloj."""
        regen = self.config.regen_per_day
        if regen <= 0:
            return
        for e in self.entities.values():
            if e.kind != "resource":
                continue
            cap = float(e.attrs.get("initial_amount", e.attrs.get("amount", 0.0)))
            e.attrs["amount"] = min(cap, float(e.attrs.get("amount", 0.0)) + regen)

    def _expel_agents_from_blocked_regions(self) -> None:
        """Expulsa agentes que quedaron en una región bloqueada por la fase actual.

        Crítica de Opus: si un agente se queda en B cuando llega la fase oscura,
        VIVE la celda retenida (B-oscura) y el test de composición se cae sin
        hacer ruido. La barrera impide entrar; la expulsión garantiza que nadie
        permanezca: se mueve a la celda libre más cercana en región no bloqueada."""
        phase = self.phase()
        for aid, agent in list(self.agents.items()):
            ent = agent.entity
            if self._region_blocked(self.region(ent.x, ent.y), phase):
                target = self._nearest_free_unblocked_cell(ent.x, ent.y, phase)
                if target is not None:
                    from_pos = (ent.x, ent.y)
                    ent.x, ent.y = target
                    self._event(aid, "expelled", "ok",
                                {"from": from_pos, "to": target, "phase": phase})

    def _nearest_free_unblocked_cell(self, x: int, y: int, phase: int):
        """Búsqueda en espiral: celda libre en región NO bloqueada más cercana."""
        limit = max(self.config.width, self.config.height)
        for radius in range(1, limit + 1):
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    if abs(dx) + abs(dy) != radius:
                        continue
                    nx, ny = x + dx, y + dy
                    if not self.in_bounds(nx, ny):
                        continue
                    if self._region_blocked(self.region(nx, ny), phase):
                        continue
                    if not self.entities_at(nx, ny):
                        return nx, ny
        return None

    def no_heldout_consumption(self) -> bool:
        """RED DE DETECCIÓN (Opus): ningún consume ok en una celda bloqueada.
        Si ocurre, la expulsión falló por alguna vía y la celda retenida se
        contaminó — el test de composición dejó de significar nada."""
        blocked = {(phase, region) for (phase, region), blocked
                   in self.config.phase_barriers.items() if blocked}
        for ev in self.events:
            if ev.action == "consume" and ev.outcome == "ok":
                key = (ev.detail.get("phase"), ev.detail.get("region"))
                if key in blocked:
                    return False
        return True

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
        """Percepción limitada del agente: solo entidades dentro del radio.

        DECISIÓN DE PERCEPCIÓN (explícita, no por omisión):
        - eids SIEMPRE opacos (nunca revelan tipo por el identificador).
        - El agente SÍ distingue el tipo de recurso a distancia (rkind) y el
          tipo de estructura (structure): regla del mundo. Es lo que le permite
          decidir "quiero comida" sin que el nombre viaje en el id.
        - No se revelan cantidades exactas de recursos (solo que existe).
        """
        ent = self.entities.get(eid)
        if ent is None:
            return {"error": "no_such_entity"}
        seen = []
        for other in self.entities.values():
            if abs(other.x - ent.x) <= radius and abs(other.y - ent.y) <= radius:
                info = {"eid": other.eid, "kind": other.kind,
                        "dx": other.x - ent.x, "dy": other.y - ent.y}
                if other.kind == "resource":
                    info["rkind"] = other.attrs.get("kind", "generic")
                elif other.kind == "object":
                    info["structure"] = other.attrs.get("structure", "unknown")
                seen.append(info)
        return {"day": self.day, "tick": self.tick,
                "position": [ent.x, ent.y],
                "region": self.region(ent.x, ent.y),
                "phase": self.phase(),
                "heard": list(self.inbox.get(eid, [])[-5:]),   # últimos 5 mensajes oídos
                "visible": seen}

    def available_actions(self, eid: str) -> List[Dict[str, Any]]:
        """Acciones EJECUTABLES en este instante, con argumentos ya rellenados (D-026).

        NO es prestar un world model: se dicen los botones que existen, no qué
        hacen. El agente sigue sin saber qué efecto tiene consumir S2 aquí y
        ahora — eso es lo único que el experimento le pide descubrir. Lo que
        se elimina es el ruido de saber escribir la API del motor (91-96% de
        rechazos del piloto: gather lejano, consume sin rkind).

        La lista replica las condiciones del validador (can_move, adyacencia,
        inventario, materiales) para que SOLO aparezcan acciones que el motor
        aceptaría. Aplicada idéntico en las 4 condiciones (D-026).
        """
        agent = self.agents.get(eid)
        if agent is None:
            return [{"action": "rest", "args": {}}]
        ent = agent.entity
        actions: List[Dict[str, Any]] = []

        # move: solo direcciones que el validador aceptaría (y alcanza la energía)
        if agent.energy >= self.config.move_energy:
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ok, _ = self.can_move(eid, dx, dy)
                if ok:
                    actions.append({"action": "move", "args": {"dx": dx, "dy": dy}})

        # gather: recursos a distancia <= 1 con cantidad disponible
        for other in self.entities.values():
            if other.kind != "resource":
                continue
            if abs(other.x - ent.x) + abs(other.y - ent.y) > 1:
                continue
            if float(other.attrs.get("amount", 0.0)) <= 0:
                continue
            actions.append({"action": "gather",
                            "args": {"target_eid": other.eid, "amount": 1}})

        # pickup: recursos DROPEADOS (suelo) a distancia <= 1 con cantidad
        for other in self.entities.values():
            if other.kind != "resource" or not other.attrs.get("owner_dropped"):
                continue
            if abs(other.x - ent.x) + abs(other.y - ent.y) > 1:
                continue
            if float(other.attrs.get("amount", 0.0)) <= 0:
                continue
            actions.append({"action": "pickup", "args": {"target_eid": other.eid}})

        # consume / drop: desde el inventario (solo lo que tiene)
        for rkind, qty in agent.inventory.items():
            if qty > 0:
                actions.append({"action": "consume", "args": {"rkind": rkind, "amount": 1}})
                actions.append({"action": "drop", "args": {"rkind": rkind, "amount": 1}})

        # give: a agentes adyacentes, por cada recurso que tiene
        for other in self.agents.values():
            if other.entity.eid == eid:
                continue
            if abs(other.entity.x - ent.x) + abs(other.entity.y - ent.y) != 1:
                continue
            for rkind, qty in agent.inventory.items():
                if qty > 0:
                    actions.append({"action": "give",
                                    "args": {"target_eid": other.entity.eid,
                                             "rkind": rkind, "amount": 1}})

        # build: recetas que alcanza con su inventario, en celdas adyacentes libres
        for structure, recipe in self.config.recipes.items():
            if any(agent.inventory.get(rkind, 0.0) < need for rkind, need in recipe.items()):
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = ent.x + dx, ent.y + dy
                if not self.in_bounds(nx, ny):
                    continue
                if self.entities_at(nx, ny):
                    continue
                actions.append({"action": "build",
                                "args": {"structure": structure, "x": nx, "y": ny}})

        # talk: símbolo del alfabeto, si tiene energía (cost = 1.0)
        if agent.energy >= 1.0 and self.config.symbol_alphabet:
            actions.append({"action": "talk",
                            "args": {"message": self.config.symbol_alphabet[0]}})

        # rest: siempre disponible
        actions.append({"action": "rest", "args": {}})
        return actions
