"""WorldLab — runner del piloto (fase 3).

Diseño de Opus: 3 condiciones (sin_memoria / memoria / oráculo) ×
3 densidades (12/7/4%) × N mundos (seeds).

Entrega al final:
- σ del desempeño entre mundos, por condición y densidad
- tasa de acierto en probes de CELDAS VIVIDAS (sub-check: si fallan,
  el mundo quedó demasiado difícil y nada más es interpretable)
- tasa de acierto en el probe RETENIDO (B-oscura) vs azar ~17%
- costo real en tokens (y dinero si API; local = $0)
- cuántos mundos activaron no_heldout_consumption() == False

El oráculo recibe las REGLAS del mundo en el prompt (ground truth), no una
traza: es el límite superior de desempeño (control, no modelo a imitar).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.world_state import WorldConfig, Entity, build_separable_effects
from ai.baseline import BaselineParams, EmpiricalAgent
from ai.simulate import Simulator, make_deterministic_policy, make_llm_policy, \
    make_empirical_policy
from ai.llm_agent import LLMAgent
from ai.memory import LiteralMemory
from ai.model_adapter import LLMClient
from ai.probe import run_probe_set

EFFECT_SPEC = {"S1": (+8.0, -11.0, -4.0), "S2": (-2.0, +9.0, +3.0),
               "S3": (0.0, 0.0, 0.0), "S4": (+1.0, 0.0, -1.0)}
DENSITIES = {"holgado": 0.12, "justo": 0.07, "hambre": 0.04}
CONDITIONS = ["sin_memoria", "memoria", "oraculo", "baseline_empirico"]


def make_world_config(days: int) -> WorldConfig:
    cfg = WorldConfig(width=30, height=30, days=days, ticks_per_day=24,
                      energy_per_tick=0.3, region_split=0.5, n_phases=2,
                      phase_ticks=12, clusters_n=8, clusters_radius=3,
                      clusters_per_region=4, regen_per_day=0.5,
                      starvation_ticks=48)
    cfg.consume_effects = build_separable_effects(
        base={s: spec[0] for s, spec in EFFECT_SPEC.items()},
        delta_region={s: {"B": spec[1]} for s, spec in EFFECT_SPEC.items() if spec[1]},
        delta_phase={s: {1: spec[2]} for s, spec in EFFECT_SPEC.items() if spec[2]})
    cfg.phase_barriers = {(1, "B"): True}
    cfg.struct_effects = {"struct_a": {"metabolism_factor": 0.5, "phase": 1, "range": 1}}
    cfg.recipes = {"struct_a": {"S3": 2.0, "S4": 1.0}}
    return cfg


ORACLE_RULES = (
    "Reglas del mundo (conocimiento de oráculo):\n"
    "- Consumir un recurso cambia tu energía según el símbolo y el CONTEXTO "
    "(región A/B y fase clara(0)/oscura(1)):\n"
    "  S1: A-clara +8, A-oscura +4, B-clara -3, B-oscura -7\n"
    "  S2: A-clara -2, A-oscura +1, B-clara +7, B-oscura +10\n"
    "  S3: 0 en todas las celdas\n"
    "  S4: A-clara +1, A-oscura 0, B-clara 0, B-oscura -1\n"
    "- En fase oscura (1) la región B es inaccesible: la barrera te expulsa.\n"
    "- Los recursos se regeneran +0.5 por día hasta su carga inicial.\n"
    "- struct_a (S3x2 + S4x1) reduce tu metabolismo a la mitad en fase oscura "
    "si estás adyacente.\n"
    "- Tu energía no puede superar 100.\n"
)


def make_agents(condition: str, model_name: str, client: LLMClient,
                world_cfg: WorldConfig) -> Dict[str, Any]:
    """Crea 5 agentes para la condición. Devuelve {eid: agente} para policy y hooks."""
    agents: Dict[str, Any] = {}
    for i in range(5):
        eid = f"a{i}"
        if condition == "oraculo":
            ag = LLMAgent(eid, client, goal="sobrevivir y maximizar energía",
                          system_rules=ORACLE_RULES,
                          think_every=8, hunger_threshold=30.0,
                          model_name=model_name, memory=None)
        elif condition == "memoria":
            ag = LLMAgent(eid, client, goal="sobrevivir y maximizar energía",
                          think_every=8, hunger_threshold=30.0,
                          model_name=model_name,
                          memory=LiteralMemory(max_items=80, label="memory"))
        elif condition == "sin_memoria":
            ag = LLMAgent(eid, client, goal="sobrevivir y maximizar energía",
                          think_every=8, hunger_threshold=30.0,
                          model_name=model_name, memory=None)
        else:  # baseline_empirico — control de comparación, 0 tokens
            ag = EmpiricalAgent(eid, BaselineParams(eat_threshold=30.0,
                                                    build_min=4.0,
                                                    exploration=0.15),
                                rng_seed=1)
        agents[eid] = ag
    return agents


def run_world(condition: str, density: float, seed: int, days: int,
              model_name: str, client: LLMClient, out_dir: Path) -> Dict[str, Any]:
    cfg = make_world_config(days)
    agents = make_agents(condition, model_name, client, cfg)
    eids = sorted(agents.keys())
    entities = [Entity(eid=eid, kind="agent", x=3 + i * 3, y=15)
                for i, eid in enumerate(eids)]
    if condition == "baseline_empirico":
        policy = make_empirical_policy(agents)
    else:
        policy = make_llm_policy(agents)

    sim = Simulator(cfg, policy, str(out_dir),
                    f"piloto_{condition}_{int(density*100)}_s{seed}",
                    log_interval=12, resource_density=density,
                    resource_kinds=["S1", "S2", "S3", "S4"],
                    resource_names={"S1": "comida", "S2": "energía",
                                    "S3": "madera", "S4": "piedra"},
                    agent_hooks=agents)
    res = sim.run(entities, seed=seed)

    # probes de composición al final de la vida del agente (mundo terminado)
    probe_results = []
    world_for_probe = sim.last_world  # el mundo real con sus eventos y siembra
    for eid in eids:
        if eid not in world_for_probe.agents:
            continue
        ag = agents[eid]
        results = run_probe_set(world_for_probe, ag, str(out_dir),
                                f"piloto_{condition}_{int(density*100)}_s{seed}",
                                rkind="S1")
        probe_results.extend(results)

    # red de detección: ¿alguien vivió la celda retenida? (usa el mundo real)
    heldout_ok = sim.last_world.no_heldout_consumption()

    tokens = sum(ag.total_prompt_tokens + ag.total_completion_tokens for ag in agents.values())
    calls = sum(ag.total_calls for ag in agents.values())

    return {
        "condition": condition,
        "density": density,
        "seed": seed,
        "survivors": res.survivors,
        "avg_energy": round(res.avg_energy, 1),
        "actions_ok": res.total_actions_ok,
        "actions_impossible": res.total_actions_impossible,
        "heldout_clean": heldout_ok,
        "llm_calls": calls,
        "tokens": tokens,
        "probes": probe_results,
    }


def make_llm_policy(agents: Dict[str, Any]):
    """Policy que delega en el LLMAgent correspondiente (devuelve 4-tupla)."""
    return _llm_policy_from(agents)


def _llm_policy_from(agents: Dict[str, Any]):
    from ai.simulate import make_llm_policy as _m
    return _m(agents)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--worlds", type=int, default=8, help="mundos (seeds) por celda")
    ap.add_argument("--days", type=int, default=30, help="días simulados por mundo")
    ap.add_argument("--model", default="qwen2.5:7b", help="modelo Ollama/API")
    ap.add_argument("--density", default="all", choices=["all", "12", "7", "4"])
    ap.add_argument("--conditions", default="all", choices=["all", "sin_memoria", "memoria", "oraculo"])
    ap.add_argument("--smoke", action="store_true", help="prueba de humo: 1 mundo × densidad justa")
    args = ap.parse_args()

    out_dir = Path("data/silver/piloto")
    out_dir.mkdir(parents=True, exist_ok=True)

    model_name = args.model
    client = LLMClient(backend="ollama", model=model_name)  # local $0

    if args.smoke:
        densities = [0.07]
        conditions = ["sin_memoria", "memoria", "oraculo"]
        worlds = [1]
        days = 12
    else:
        densities = [float(d) / 100 for d in ("12", "7", "4")] if args.density == "all" \
            else [float(args.density) / 100]
        conditions = CONDITIONS if args.conditions == "all" else [args.conditions]
        worlds = list(range(1, args.worlds + 1))
        days = args.days

    results = []
    t_start = time.time()
    for cond in conditions:
        for density in densities:
            for seed in worlds:
                t0 = time.time()
                r = run_world(cond, density, seed, days, model_name, client, out_dir)
                dt = time.time() - t0
                r["elapsed_s"] = round(dt, 1)
                results.append(r)
                print(f"[{cond} | d={density:.0%} | seed={seed}] "
                      f"superv={r['survivors']} en {dt:.0f}s "
                      f"tokens={r['tokens']} heldout={r['heldout_clean']}",
                      flush=True)

    summary_path = out_dir / "piloto_summary.json"
    summary_path.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"\nResumen guardado: {summary_path}")
    print(f"Total: {len(results)} mundos en {(time.time()-t_start)/60:.1f} min")


if __name__ == "__main__":
    main()
