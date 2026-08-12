"""WorldLab — demo: genera una simulación de ejemplo con el baseline
determinista y la deja lista para ver en viewer.html.

Uso: .venv/bin/python -m ai.run_demo [days] [seed]
"""

import sys
import os

from .world_state import WorldConfig, Entity
from .baseline import BaselineParams
from .simulate import Simulator, make_deterministic_policy

DEMO_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "bronze")


def main() -> None:
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    cfg = WorldConfig(width=30, height=30, days=days, ticks_per_day=24,
                      energy_per_tick=0.25)
    cfg.energy_per_unit["food"] = 8.0
    cfg.energy_per_unit["water"] = 5.0

    agents = [Entity(eid=f"a{i}", kind="agent", x=5 + i * 2, y=5) for i in range(5)]
    policy = make_deterministic_policy(BaselineParams(eat_threshold=35.0,
                                                      build_min=6.0,
                                                      exploration=0.15))
    # mundo de desarrollo: densidad de recursos generosa (12% del grid) para
    # que la demo muestre comportamiento; el mundo reservado usará la densidad
    # definida por el pre-registro (Opus)
    sim = Simulator(cfg, policy, DEMO_DIR, f"demo_d{days}_s{seed}", log_interval=12,
                    resource_density=0.12)
    res = sim.run(agents, seed=seed)
    print("Demo generada:", res.events_path)
    print(res.to_dict())


if __name__ == "__main__":
    main()
