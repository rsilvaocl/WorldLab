"""WorldLab — baselines deterministas (fase 0/1).

Política greedy paramétrica SIN LLM. Exigencia de Opus: no es "la mejor
política simple posible" aspiracional, sino una clase paramétrica fija cuyos
k parámetros se optimizan por búsqueda en el mundo de desarrollo hasta
convergencia. Un baseline que no se optimizó no es baseline, es hombre de paja.

Parámetros (k = 3):
  eat_threshold:  si energía < umbral y hay comida -> consumir
  build_min:      materiales mínimos para construir una estructura
  exploration:    probabilidad de movimiento no-greedy (explorar)

DOS variantes (corrección de Opus):
- DeterministicAgent  = "determinista INFORMADO" (techo determinista). Lee
  cfg.consume_effects (la tabla de verdad). NO es el baseline de comparación:
  es un ORÁCULO con otra ropa — si el LLM no le gana, no aprendemos nada.
  Se conserva porque es informativo: si el oráculo LLM no le gana a un greedy
  que conoce las reglas, eso dice algo importante.
- EmpiricalAgent       = baseline de COMPARACIÓN (condición 3 de emergencia:
  "supera a un baseline reactivo determinista"). Mantiene una tabla de efecto
  promedio OBSERVADO por (símbolo, región, fase), poblada por sus propios
  consumos (record_outcome del motor). Se envenena las primeras veces, como
  el LLM — es la mejor política simple posible con la MISMA información.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .world_state import WorldState


@dataclass
class BaselineParams:
    eat_threshold: float = 30.0      # energía mínima antes de comer si hay comida
    build_min: float = 6.0           # suma de materiales para considerar construir
    exploration: float = 0.15        # fracción de ticks con movimiento no-greedy


class DeterministicAgent:
    """Agente determinista INFORMADO (techo): conoce cfg.consume_effects.
    Decide CADA TICK (barato). NO es el baseline de comparación — ver módulo."""

    def __init__(self, eid: str, params: BaselineParams, rng_seed: int = 0):
        self.eid = eid
        self.params = params
        self.rng = __import__("random").Random(rng_seed)

    def _expected_value(self, world: WorldState, rkind: str) -> float:
        """Valor esperado de consumir `rkind` en la región/fase actual del agente.
        Lee la TABLA DE VERDAD (cfg.consume_effects) — es el techo informado."""
        cfg = world.config
        ent = world.entities[self.eid]
        key = (rkind, world.region(ent.x, ent.y), world.phase())
        if key in cfg.consume_effects:
            return cfg.consume_effects[key]
        return cfg.energy_per_unit.get(rkind, 0.0)

    def _best_energy_resource(self, world: WorldState):
        """El recurso del inventario con mayor valor esperado en la celda actual."""
        agent = world.agents[self.eid]
        best, best_val = None, -1.0
        for rkind, amt in agent.inventory.items():
            if amt <= 0:
                continue
            val = self._expected_value(world, rkind)
            if val > best_val:
                best, best_val = rkind, val
        return best

    def decide(self, world: WorldState) -> Tuple[str, dict]:
        """Retorna (acción, kwargs). El motor valida; si es imposible, el
        agente no insiste (sigue con la siguiente regla en el próximo tick)."""
        agent = world.agents[self.eid]
        ent = agent.entity
        energy = agent.energy
        p = self.params

        # 1. urgencia: comer el recurso más energético del inventario
        if energy < p.eat_threshold:
            best_food = self._best_energy_resource(world)
            if best_food is not None:
                return "consume", {"rkind": best_food, "amount": 1.0}

        # 2. recolectar el recurso adyacente más valioso (greedy)
        best = self._best_adjacent_resource(world)
        if best is not None:
            return "gather", {"target_eid": best.eid, "amount": 1.0}

        # 3. construir si el inventario cubre ALGUNA receta del mundo (dinámico)
        for recipe_name, recipe in world.config.recipes.items():
            if all(agent.inventory.get(r, 0.0) >= need for r, need in recipe.items()):
                bx, by = self._free_adjacent_cell(world)
                if bx is not None:
                    return "build", {"structure": recipe_name, "x": bx, "y": by}
                break  # hay receta pagable pero no celda libre; no probar otras

        # 4. moverse hacia el recurso visible más cercano (greedy)
        step = self._step_toward_resource(world)
        if step is not None:
            return "move", step

        # 5. exploración: movimiento aleatorio (con probabilidad exploration)
        if self.rng.random() < p.exploration:
            dx = self.rng.choice([-1, 0, 0, 1])
            dy = self.rng.choice([-1, 0, 0, 1])
            if dx or dy:
                return "move", {"dx": dx, "dy": dy}

        # 6. nada útil que hacer -> descansar (acción nula implícita)
        return "rest", {}

    # ------------------------------------------------------------------
    def _best_adjacent_resource(self, world: WorldState):
        """Recurso adyacente con mayor valor esperado en la celda actual
        (usa consume_effects, no cantidad ni nombre semántico)."""
        ent = world.entities[self.eid]
        best, best_val = None, 0.0   # 0.0: solo recursos con amount > 0 y valor > 0
        for other in world.entities.values():
            if other.kind != "resource":
                continue
            if abs(other.x - ent.x) + abs(other.y - ent.y) == 1:
                amount = float(other.attrs.get("amount", 0.0))
                if amount <= 0:
                    continue
                rkind = other.attrs.get("kind", "generic")
                val = amount * (self._expected_value(world, rkind) + 1e-9)
                if val > best_val:
                    best, best_val = other, val
        return best

    def _free_adjacent_cell(self, world: WorldState):
        ent = world.entities[self.eid]
        for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
            nx, ny = ent.x + dx, ent.y + dy
            if world.in_bounds(nx, ny) and not world.entities_at(nx, ny):
                return nx, ny
        return None, None

    def _step_toward_resource(self, world: WorldState):
        """Moverse una celda hacia el recurso visible de MAYOR valor esperado
        en la celda actual (no el más cercano — eso lo atasca en cúmulos de
        bajo valor y muere de hambre junto a la comida)."""
        ent = world.entities[self.eid]
        radius = 5
        best, best_val = None, -1.0
        for other in world.entities.values():
            if other.kind != "resource":
                continue
            d = abs(other.x - ent.x) + abs(other.y - ent.y)
            if 0 < d <= radius:
                amount = float(other.attrs.get("amount", 0.0))
                if amount <= 0:
                    continue
                rkind = other.attrs.get("kind", "generic")
                val = self._expected_value(world, rkind) + 1e-9
                if val > best_val:
                    best, best_val = other, val
        if best is None:
            return None
        dx = 0 if best.x == ent.x else (1 if best.x > ent.x else -1)
        dy = 0 if best.y == ent.y else (1 if best.y > ent.y else -1)
        # prefiere el eje con mayor distancia (evita zigzag)
        if abs(best.x - ent.x) >= abs(best.y - ent.y):
            return {"dx": dx, "dy": 0}
        return {"dx": 0, "dy": dy}


class EmpiricalAgent(DeterministicAgent):
    """Baseline de COMPARACIÓN (corrección de Opus): la mejor política simple
    posible con la MISMA información que el LLM.

    Mantiene una tabla de efecto promedio OBSERVADO por (símbolo, región, fase),
    poblada por sus propios consumos (el motor le entrega el resultado real vía
    record_outcome, igual que al LLM). Sin observaciones previas, el valor por
    defecto es 0.0 — se envenena las primeras veces (come S2 en A creyéndolo
    bueno), igual que el LLM, y va corrigiendo con la experiencia.

    No lee cfg.consume_effects: esa tabla es el oráculo, no un baseline.
    """

    def __init__(self, eid: str, params: BaselineParams, rng_seed: int = 0,
                 default_value: float = 0.0):
        super().__init__(eid, params, rng_seed)
        self.default_value = default_value
        # (rkind, región, fase) -> lista de energy_gain observados
        self._observed: Dict[Tuple[str, str, int], List[float]] = {}

    def record_outcome(self, ev) -> None:
        """El motor le entrega el resultado real de su consumo (mismo hook que el LLM)."""
        if ev.action != "consume" or ev.outcome != "ok":
            return
        key = (ev.detail.get("resource"), ev.detail.get("region"),
               ev.detail.get("phase"))
        self._observed.setdefault(key, []).append(float(ev.detail.get("energy_gain", 0.0)))

    def _expected_value(self, world: WorldState, rkind: str) -> float:
        """Efecto PROMEDIO OBSERVADO en la región/fase actual; sin datos, 0.0
        (neutro — prueba y aprende, como el LLM)."""
        ent = world.entities[self.eid]
        key = (rkind, world.region(ent.x, ent.y), world.phase())
        obs = self._observed.get(key, [])
        if not obs:
            return self.default_value
        return sum(obs) / len(obs)

    def predict_effect(self, rkind: str, region: str, phase: int) -> Optional[float]:
        """Forced-choice probe para el baseline empírico: devuelve el promedio
        observado en esa celda, o None si nunca la vivió. Nota: el greedy
        empírico NO compone — sin dato de B-oscura, no tiene de dónde sacarlo.
        Ese contraste con el LLM es exactamente lo que mide el experimento."""
        obs = self._observed.get((rkind, region, phase), [])
        if not obs:
            return None
        return sum(obs) / len(obs)
