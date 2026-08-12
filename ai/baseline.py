"""WorldLab — baseline determinista (fase 0/1).

Política greedy paramétrica SIN LLM. Exigencia de Opus: no es "la mejor
política simple posible" aspiracional, sino una clase paramétrica fija cuyos
k parámetros se optimizan por búsqueda en el mundo de desarrollo hasta
convergencia. Un baseline que no se optimizó no es baseline, es hombre de paja.

Parámetros (k = 3):
  eat_threshold:  si energía < umbral y hay comida -> consumir
  build_min:      materiales mínimos para construir una estructura
  exploration:    probabilidad de movimiento no-greedy (explorar)

La política es DETERMINISTA dado (seed, parámetros): misma entrada => misma
secuencia de acciones. Eso permite comparar contra agentes LLM sin confound.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from .world_state import WorldState


@dataclass
class BaselineParams:
    eat_threshold: float = 30.0      # energía mínima antes de comer si hay comida
    build_min: float = 6.0           # suma de materiales para considerar construir
    exploration: float = 0.15        # fracción de ticks con movimiento no-greedy


class DeterministicAgent:
    """Agente determinista: decide acciones a partir de la percepción visible.
    Sin memoria, sin modelo, sin LLM. Decide CADA TICK (barato)."""

    def __init__(self, eid: str, params: BaselineParams, rng_seed: int = 0):
        self.eid = eid
        self.params = params
        self.rng = __import__("random").Random(rng_seed)

    def decide(self, world: WorldState) -> Tuple[str, dict]:
        """Retorna (acción, kwargs). El motor valida; si es imposible, el
        agente no insiste (sigue con la siguiente regla en el próximo tick)."""
        agent = world.agents[self.eid]
        ent = agent.entity
        energy = agent.energy
        p = self.params

        # 1. urgencia: comer si hay comida y la energía está bajo el umbral
        food = agent.inventory.get("food", 0.0)
        if food > 0 and energy < p.eat_threshold:
            return "consume", {"rkind": "food", "amount": 1.0}

        # 2. recolectar el recurso adyacente más valioso (greedy)
        best = self._best_adjacent_resource(world)
        if best is not None:
            return "gather", {"target_eid": best.eid, "amount": 1.0}

        # 3. construir si el inventario cubre la receta definida en el mundo
        recipe = world.config.recipes.get("hut")
        if recipe and all(agent.inventory.get(r, 0.0) >= need for r, need in recipe.items()):
            bx, by = self._free_adjacent_cell(world)
            if bx is not None:
                return "build", {"structure": "hut", "x": bx, "y": by}

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
        ent = world.entities[self.eid]
        best, best_val = None, 0.0   # 0.0: solo recursos con amount > 0
        for other in world.entities.values():
            if other.kind != "resource":
                continue
            if abs(other.x - ent.x) + abs(other.y - ent.y) == 1:
                val = float(other.attrs.get("amount", 0.0))
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
        ent = world.entities[self.eid]
        radius = 5
        best, best_dist = None, 10**9
        for other in world.entities.values():
            if other.kind != "resource":
                continue
            d = abs(other.x - ent.x) + abs(other.y - ent.y)
            if 0 < d <= radius and d < best_dist:
                best, best_dist = other, d
        if best is None:
            return None
        dx = 0 if best.x == ent.x else (1 if best.x > ent.x else -1)
        dy = 0 if best.y == ent.y else (1 if best.y > ent.y else -1)
        # prefiere el eje con mayor distancia (evita zigzag)
        if abs(best.x - ent.x) >= abs(best.y - ent.y):
            return {"dx": dx, "dy": 0}
        return {"dx": 0, "dy": dy}
