"""WorldLab — demo: genera una simulación de ejemplo con el baseline
determinista y la deja lista para ver en viewer.html.

Uso: .venv/bin/python -m ai.run_demo [days] [seed]
"""

import sys
import os

from .world_state import WorldConfig, Entity, build_separable_effects
from .baseline import BaselineParams, EmpiricalAgent
from .simulate import Simulator, make_empirical_policy

DEMO_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "bronze")


def main() -> None:
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    # ontología v1 aprobada (spec 2026-08-11 §8): cúmulos, fases, regeneración
    cfg = WorldConfig(width=30, height=30, days=days, ticks_per_day=24,
                      energy_per_tick=0.3, region_split=0.5, n_phases=2,
                      phase_ticks=12, clusters_n=8, clusters_radius=3,
                      clusters_per_region=4, regen_per_day=0.5,
                      starvation_ticks=48)
    EFFECT_SPEC = {"S1": (+8.0, -11.0, -4.0), "S2": (-2.0, +9.0, +3.0),
                   "S3": (0.0, 0.0, 0.0), "S4": (+1.0, 0.0, -1.0)}
    cfg.consume_effects = build_separable_effects(
        base={s: spec[0] for s, spec in EFFECT_SPEC.items()},
        delta_region={s: {"B": spec[1]} for s, spec in EFFECT_SPEC.items() if spec[1]},
        delta_phase={s: {1: spec[2]} for s, spec in EFFECT_SPEC.items() if spec[2]})
    cfg.phase_barriers = {(1, "B"): True}
    cfg.struct_effects = {"struct_a": {"metabolism_factor": 0.5, "phase": 1, "range": 1}}
    cfg.recipes = {"struct_a": {"S3": 2.0, "S4": 1.0}}

    agents = [Entity(eid=f"a{i}", kind="agent", x=3 + i * 3, y=15) for i in range(5)]
    # baseline EMPÍRICO (comparación): aprende de sus propios consumos,
    # se envenena y corrige — como el LLM. El informado (techo) no se demuestra.
    emp = {e.eid: EmpiricalAgent(e.eid,
                                 BaselineParams(eat_threshold=30.0,
                                                build_min=4.0,
                                                exploration=0.15))
           for e in agents}
    policy = make_empirical_policy(emp)
    # nombres bonitos SOLO para el visor; el mundo es opaco (S1..S4)
    sim = Simulator(cfg, policy, DEMO_DIR, f"demo_ont_v1_d{days}_s{seed}", log_interval=12,
                    resource_density=0.12,
                    resource_kinds=["S1", "S2", "S3", "S4"],
                    resource_names={"S1": "comida", "S2": "energía", "S3": "madera",
                                    "S4": "piedra"},
                    agent_hooks=emp)
    res = sim.run(agents, seed=seed)
    print("Demo generada:", res.events_path)
    print(res.to_dict())


if __name__ == "__main__":
    main()
