"""Regresión piloto 12/08: una acción malformada (gather sin target_eid) NUNCA
puede tumbar el experimento — se registra como impossible y el mundo sigue.
Causa raíz de las muertes del piloto: TypeError no protegido en simulate.run."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.simulate import Simulator
from ai.world_state import WorldConfig, Entity


def make_bad_policy():
    """Devuelve SIEMPRE gather sin target_eid (como el LLM a veces hace)."""
    def policy(world, aid, tick, rng_turn):
        return "gather", {}
    return policy


def test_malformed_gather_does_not_crash(tmp_path):
    cfg = WorldConfig(width=10, height=10, days=3, ticks_per_day=8,
                      energy_per_tick=0.5, move_energy=0.1)
    sim = Simulator(cfg, make_bad_policy(), str(tmp_path), "test_malformed")
    agents = [Entity(eid=f"a{i}", kind="agent", x=i, y=i) for i in range(3)]
    sim.run(agents, seed=1)  # no debe lanzar TypeError

    events = []
    for line in (tmp_path / "test_malformed_seed1.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        if obj.get("type") == "event":
            events.append(obj)
    assert events, "debe haber eventos"
    imp = [e for e in events if e["outcome"] == "impossible"]
    assert imp, "las acciones malformadas deben registrarse como impossible"
    assert all(e["detail"].get("reason", "").startswith("malformed") for e in imp)
