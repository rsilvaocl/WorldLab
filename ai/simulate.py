"""WorldLab — runner headless de simulaciones (fase 0/1).

Ejecuta un mundo con una política dada (determinista o, más adelante, LLM),
registra eventos + snapshots + traces en JSONL, y calcula métricas básicas.

El loop de simulación es barato: los agentes deterministas deciden cada tick;
los agentes LLM (fase 2) decidirán solo ante eventos (fase 2+).
"""

from __future__ import annotations

import json
import os
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from .world_state import WorldConfig, WorldState, Entity
from .baseline import BaselineParams, DeterministicAgent
from .logger import JsonlLogger


@dataclass
class SimResult:
    """Resultado de una simulación: métricas básicas + rutas de archivos."""
    experiment_id: str
    seed: int
    days: int
    survivors: int
    avg_energy: float
    total_actions_ok: int
    total_actions_impossible: int
    structures_built: int
    total_gathered: float
    events_path: str
    trace_path: Optional[str] = None
    elapsed_s: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "seed": self.seed,
            "days": self.days,
            "survivors": self.survivors,
            "avg_energy": round(self.avg_energy, 2),
            "total_actions_ok": self.total_actions_ok,
            "total_actions_impossible": self.total_actions_impossible,
            "structures_built": self.structures_built,
            "total_gathered": round(self.total_gathered, 2),
            "events_path": self.events_path,
            "trace_path": self.trace_path,
            "elapsed_s": round(self.elapsed_s, 2),
        }


class Simulator:
    """Ejecuta una simulación headless completa."""

    def __init__(self, config: WorldConfig, policy: Callable, output_dir: str,
                 experiment_id: str, log_interval: int = 48,
                 death_energy: float = 0.0, resource_density: float = 0.05):
        self.config = config
        self.policy = policy          # policy(world, tick) -> (action, kwargs) por agente
        self.output_dir = output_dir
        self.experiment_id = experiment_id
        self.log_interval = log_interval
        self.death_energy = death_energy
        self.resource_density = resource_density

    def _build_world(self, agents: List[Entity], seed: int) -> WorldState:
        world = WorldState(self.config, agents, seed=seed)
        count = int(self.config.width * self.config.height * self.resource_density)
        world.scatter_resources(count, kind="resource")
        return world

    def run(self, agents: List[Entity], seed: int) -> SimResult:
        t0 = time.time()
        os.makedirs(self.output_dir, exist_ok=True)
        events_path = os.path.join(self.output_dir, f"{self.experiment_id}_seed{seed}.jsonl")
        trace_path = events_path.replace(".jsonl", "_traces.jsonl")
        logger = JsonlLogger(events_path, meta={
            "experiment": self.experiment_id,
            "seed": seed,
            "days": self.config.days,
            "ticks_per_day": self.config.ticks_per_day,
            "width": self.config.width,
            "height": self.config.height,
        })
        trace_logger = JsonlLogger(trace_path, meta={"experiment": self.experiment_id,
                                                     "seed": seed, "kind": "agent_trace"})

        world = self._build_world(agents, seed)
        stats = {
            "ok": 0, "impossible": 0, "built": 0, "gathered": 0.0,
        }

        # orden de turnos: FIJADO por seed (reproducible) — el ablation de
        # órdenes distintos es experimento aparte (crítica de Opus)
        agent_ids = sorted(world.agents.keys())
        rng_turn = random.Random(seed)

        for _ in range(self.config.days):
            for _tick in range(self.config.ticks_per_day):
                for aid in agent_ids:
                    agent = world.agents.get(aid)
                    if agent is None:
                        continue
                    if agent.energy <= self.death_energy:
                        # muerte: el agente deja de actuar (sigue en el mundo como cadáver)
                        continue
                    action, kwargs = self.policy(world, aid, world.tick, rng_turn)
                    if action == "rest":
                        continue
                    method = getattr(world, action, None)
                    if method is None:
                        continue
                    ev = method(aid, **kwargs)
                    logger.log_event(ev)
                    if ev.outcome == "ok":
                        stats["ok"] += 1
                        if action == "gather":
                            stats["gathered"] += float(ev.detail.get("amount", 0.0))
                        if action == "build":
                            stats["built"] += 1
                    else:
                        stats["impossible"] += 1
                if world.tick % self.log_interval == 0:
                    logger.log_snapshot(day=world.day, tick=world.tick, state=world)
                world.advance_tick()

        logger.log_snapshot(day=world.day, tick=world.tick, state=world)
        logger.close()
        trace_logger.close()

        alive = [a for a in world.agents.values() if a.energy > self.death_energy]
        result = SimResult(
            experiment_id=self.experiment_id,
            seed=seed,
            days=self.config.days,
            survivors=len(alive),
            avg_energy=sum(a.energy for a in alive) / max(len(alive), 1),
            total_actions_ok=stats["ok"],
            total_actions_impossible=stats["impossible"],
            structures_built=stats["built"],
            total_gathered=stats["gathered"],
            events_path=events_path,
            trace_path=trace_path,
            elapsed_s=time.time() - t0,
        )
        return result


def make_deterministic_policy(params: BaselineParams):
    """Crea la política determinista estándar (1 agente por eid)."""
    def policy(world: WorldState, aid: str, tick: int, rng: random.Random):
        agent = DeterministicAgent(aid, params, rng_seed=tick)
        return agent.decide(world)
    return policy


# ---------------------------------------------------------------------------
# Optimización de parámetros del baseline (búsqueda en mundo de desarrollo)
# ---------------------------------------------------------------------------

def optimize_baseline(config: WorldConfig, agents: List[Entity],
                      output_dir: str, experiment_id: str = "dev_baseline",
                      param_grid: Optional[List[Dict[str, float]]] = None,
                      score_fn: Optional[Callable[[SimResult], float]] = None,
                      n_seeds: int = 3) -> Tuple[Dict[str, float], float, List[Dict[str, Any]]]:
    """Busca los k parámetros del baseline que maximizan el score promedio
    sobre n_seeds en el mundo de desarrollo. NO es la corrida confirmatoria.

    Score por defecto: supervivencia (survivors) + energía + acciones útiles.
    """
    if param_grid is None:
        param_grid = [
            {"eat_threshold": t, "build_min": b, "exploration": e}
            for t in (20.0, 30.0, 40.0)
            for b in (4.0, 6.0, 8.0)
            for e in (0.05, 0.15, 0.3)
        ]
    if score_fn is None:
        def _default_score(r: SimResult) -> float:
            return (r.survivors * 10.0 + r.avg_energy * 0.5
                    + r.total_gathered * 0.2 + r.structures_built * 2.0)
        score_fn = _default_score

    best_params, best_score = {}, -1e9
    results: List[Dict[str, Any]] = []
    for p in param_grid:
        params = BaselineParams(**p)
        policy = make_deterministic_policy(params)
        scores = []
        for s in range(1, n_seeds + 1):
            sim = Simulator(config, policy, output_dir,
                            f"{experiment_id}_p{len(results)}", log_interval=9999)
            res = sim.run(agents, seed=s)
            scores.append(score_fn(res))
        avg = sum(scores) / len(scores)
        results.append({"params": p, "score": round(avg, 2)})
        if avg > best_score:
            best_score, best_params = avg, p
    return best_params, best_score, results
