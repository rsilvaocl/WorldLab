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
    # IDs OPACOS (crítica de Opus): el mundo experimental usa S1..S4, sin
    # semántica; los nombres bonitos viven SOLO en el visor vía resource_names.
    cfg.energy_per_unit["S1"] = 8.0   # comida (para el visor)
    cfg.energy_per_unit["S2"] = 5.0   # agua
    cfg.energy_per_unit["S3"] = 3.0   # madera
    cfg.energy_per_unit["S4"] = 1.0   # piedra

    agents = [Entity(eid=f"a{i}", kind="agent", x=5 + i * 2, y=5) for i in range(5)]
    policy = make_deterministic_policy(BaselineParams(eat_threshold=35.0,
                                                      build_min=6.0,
                                                      exploration=0.15))
    # mundo de desarrollo: densidad de recursos generosa (12% del grid) para
    # que la demo muestre comportamiento; el mundo reservado usará la densidad
    # definida por el pre-registro (Opus). Recursos con nombres legibles para
    # el visor (ontología real de Opus reemplazará esto).
    sim = Simulator(cfg, policy, DEMO_DIR, f"demo_d{days}_s{seed}", log_interval=12,
                    resource_density=0.12,
                    resource_kinds=["S1", "S2", "S3", "S4"],
                    resource_names={"S1": "comida", "S2": "agua",
                                    "S3": "madera", "S4": "piedra"})
    res = sim.run(agents, seed=seed)
    print("Demo generada:", res.events_path)
    print(res.to_dict())


if __name__ == "__main__":
    main()
