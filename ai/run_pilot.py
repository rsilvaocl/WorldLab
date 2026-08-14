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
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.world_state import WorldConfig, Entity, build_separable_effects
from ai.baseline import BaselineParams, EmpiricalAgent
from ai.simulate import Simulator, make_deterministic_policy, make_llm_policy, \
    make_empirical_policy
from ai.llm_agent import LLMAgent
from ai.memory import LiteralMemory
from ai.model_adapter import LLMClient
from ai.probe import run_probe_set

EFFECT_SPEC = {"S1": (+8.0, -9.0, -4.0), "S2": (-2.0, +9.0, +3.0),
               "S3": (0.0, 0.0, 0.0), "S4": (+1.0, +6.0, -9.0)}
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


PHASE_NAME = {0: "clara", 1: "oscura"}


def oracle_truth(cfg: WorldConfig) -> Dict[Tuple[str, str, int], float]:
    """La tabla real del mundo — ÚNICA fuente: cfg.consume_effects (lo que el motor aplica).

    D-030: antes había TRES copias de la tabla (ORACLE_RULES en run_pilot,
    TRUTH en probe_observability, flat_rules en bench_oraculo) que podían
    separarse en silencio de la ontología. Todo se deriva de acá.
    """
    symbols = sorted({k[0] for k in cfg.consume_effects})
    return {(s, r, p): cfg.consume_effects[(s, r, p)]
            for s in symbols for r in ("A", "B") for p in (0, 1)}


def oracle_rules(cfg: WorldConfig) -> str:
    """Reglas del mundo para el oráculo, GENERADAS del motor (cfg.consume_effects).

    Formato plano (D-030): una línea por celda, sin indexación posicional.
    Es el mismo formato que midió bench_oraculo como 'plana', ahora sin copia
    manual: si alguien edita la ontología, el prompt del oráculo la sigue.
    """
    truth = oracle_truth(cfg)
    lines = [f"- Consumir 1 de {s} en región {r} durante fase {p} "
             f"({PHASE_NAME[p]}): {truth[(s, r, p)]:+g} de energía"
             for s in sorted({k[0] for k in cfg.consume_effects})
             for r in ("A", "B") for p in (0, 1)]
    return (
        "Reglas del mundo (conocimiento de oráculo).\n"
        "Tabla completa de efectos. Busca la línea que coincida EXACTAMENTE "
        "con el símbolo, la región y la fase que se te pregunten:\n"
        + "\n".join(lines) + "\n"
        "- En fase 1 (oscura) la región B es inaccesible: la barrera te expulsa.\n"
        "- Los recursos se regeneran +0.5 por día hasta su carga inicial.\n"
        "- struct_a (S3x2 + S4x1) reduce tu metabolismo a la mitad en fase "
        "oscura si estás adyacente.\n"
        "- Tu energía no puede superar 100.\n"
    )


def spawn_positions(eids: List[str], cfg: WorldConfig, seed: int) -> List[Entity]:
    """D-023: nacimiento repartido entre regiones (spec v1.1 de Opus).

    Los 5 agentes nacen REPARTIDOS entre las dos regiones (2 en una, 3 en la
    otra; el lado mayor lo sortea el seed), NUNCA todos en la misma.

    Por qué: el piloto mostró que el 92% de los agentes terminaba sub-expuesto
    con cero consumos en B-clara. La causa de fondo es una trampa de
    explotación (no falta de días): una política que aprende descubre que S2
    es malo en A y deja de probarlo, pero S2 solo revela su valor en B.
    Nacer repartido entrega experiencia de ambas regiones por construcción.
    """
    import random
    rng = random.Random(seed)
    split_x = int(cfg.width * cfg.region_split)
    n = len(eids)
    n_left = rng.choice([n // 2, n - n // 2])  # 2 o 3 para 5 agentes
    n_right = n - n_left
    entities = []
    left_x = [max(2, split_x // 4 + i * 3) for i in range(n_left)]
    right_x = [split_x + 3 + i * 3 for i in range(n_right)]
    for i, eid in enumerate(eids):
        if i < n_left:
            entities.append(Entity(eid=eid, kind="agent", x=left_x[i], y=15))
        else:
            entities.append(Entity(eid=eid, kind="agent",
                                   x=right_x[i - n_left], y=15))
    return entities


def world_geometry(cfg: WorldConfig) -> str:
    """Geometría de las regiones, GENERADA de la config (D-032).

    Va en la MECÁNICA base, idéntica en las 4 condiciones — no en
    `system_rules`, que es lo que distingue al oráculo. No presta world model:
    dice DÓNDE están las regiones, no qué vale nada en ellas. Es de la misma
    naturaleza que `acciones_disponibles` (D-026) y que las etiquetas de región
    de las entidades visibles (D-029), y coherente con D-012 (identidad
    visible, propiedades ocultas).

    Por qué hace falta: el gate `gate_oraculo4` mostró que los arreglos de
    instrumento corrigieron COMER (energía neta de la comida −86 → +86) y no
    movieron NADA en llegar a B (1 cruce de frontera en 30 días, las 8 celdas
    de S2 en B intactas). La frontera solo era deducible dentro del radio de
    visión, y ni la política reactiva optimizada vive B-clara (3,3% de sus
    consumos en el piloto). Sin exposición a B-clara, B-oscura no es una
    composición: es una adivinanza.

    Lo que este cambio SÍ cambia (declarado, no disimulado): el experimento
    deja de medir cartografía a ciegas. Es deseable si la hipótesis es la
    composición de (símbolo, región, fase) — separa localizar el contexto de
    aprender su efecto, que hoy están confundidos.
    """
    split_x = int(cfg.width * cfg.region_split)
    return (
        f"- El mundo mide {cfg.width}x{cfg.height}. La región A es la mitad "
        f"OESTE (x < {split_x}) y la región B es la mitad ESTE (x >= {split_x}); "
        f"tu campo `position` es [x, y]. Esto dice dónde están las regiones, "
        f"no qué ocurre en ellas.\n"
    )


def make_agents(condition: str, model_name: str, client: LLMClient,
                world_cfg: WorldConfig,
                force_sleep: Optional[int] = None) -> Dict[str, Any]:
    """Crea 5 agentes para la condición. Devuelve {eid: agente} para policy y hooks.

    force_sleep (ABLATION, None en el experimento): fija el horizonte de
    despertar e ignora el que pide el modelo. Se aplica idéntico en las 3
    condiciones LLM — nunca a una sola, o sería ventaja diferencial.
    """
    geometry = world_geometry(world_cfg)   # D-032: idéntica en las 4
    agents: Dict[str, Any] = {}
    for i in range(5):
        eid = f"a{i}"
        if condition == "oraculo":
            ag = LLMAgent(eid, client, goal="sobrevivir y maximizar energía",
                          system_rules=oracle_rules(world_cfg),
                          think_every=8, hunger_threshold=30.0,
                          model_name=model_name, memory=None,
                          force_sleep=force_sleep, geometry=geometry)
        elif condition == "memoria":
            ag = LLMAgent(eid, client, goal="sobrevivir y maximizar energía",
                          think_every=8, hunger_threshold=30.0,
                          model_name=model_name,
                          memory=LiteralMemory(max_items=80, label="memory"),
                          force_sleep=force_sleep, geometry=geometry)
        elif condition == "sin_memoria":
            ag = LLMAgent(eid, client, goal="sobrevivir y maximizar energía",
                          think_every=8, hunger_threshold=30.0,
                          model_name=model_name, memory=None,
                          force_sleep=force_sleep, geometry=geometry)
        else:  # baseline_empirico — control de comparación, 0 tokens
            ag = EmpiricalAgent(eid, BaselineParams(eat_threshold=30.0,
                                                    build_min=4.0,
                                                    exploration=0.15),
                                rng_seed=1)
        agents[eid] = ag
    return agents


def run_world(condition: str, density: float, seed: int, days: int,
              model_name: str, client: LLMClient, out_dir: Path,
              exp_prefix: str = "piloto",
              force_sleep: Optional[int] = None) -> Dict[str, Any]:
    cfg = make_world_config(days)
    # la geometría la arma make_agents desde cfg: no se pasa desde afuera, para
    # que ningún llamador pueda darle una distinta a una condición (D-032)
    agents = make_agents(condition, model_name, client, cfg, force_sleep=force_sleep)
    eids = sorted(agents.keys())
    entities = spawn_positions(eids, cfg, seed)
    if condition == "baseline_empirico":
        policy = make_empirical_policy(agents)
    else:
        policy = make_llm_policy(agents)

    # D-024: probe de salida — al iniciar la inanición (energía 0, antes de
    # desaparecer), capturar el estado de conocimiento final del agente.
    # Antes, si el agente moría antes del final, su probe se perdía (0/0).
    exit_probes: List[Dict[str, Any]] = []

    def _on_starvation(aid: str, world: Any) -> None:
        ag = agents.get(aid)
        if ag is None or not hasattr(ag, "predict_effect"):
            return
        results = run_probe_set(world, ag, str(out_dir),
                                f"{exp_prefix}_{condition}_{int(density*100)}_s{seed}",
                                rkind="S1")
        for r in results:
            r["probe_moment"] = "exit_starvation"
        exit_probes.extend(results)

    sim = Simulator(cfg, policy, str(out_dir),
                    f"{exp_prefix}_{condition}_{int(density*100)}_s{seed}",
                    log_interval=12, resource_density=density,
                    resource_kinds=["S1", "S2", "S3", "S4"],
                    resource_names={"S1": "comida", "S2": "energía",
                                    "S3": "madera", "S4": "piedra"},
                    agent_hooks=agents,
                    on_starvation_start=_on_starvation)
    res = sim.run(entities, seed=seed)

    # probes de composición al final de la vida del agente (mundo terminado)
    probe_results = []
    world_for_probe = sim.last_world  # el mundo real con sus eventos y siembra
    for eid in eids:
        if eid not in world_for_probe.agents:
            continue
        ag = agents[eid]
        results = run_probe_set(world_for_probe, ag, str(out_dir),
                                f"{exp_prefix}_{condition}_{int(density*100)}_s{seed}",
                                rkind="S1")
        for r in results:
            r["probe_moment"] = "final"
        probe_results.extend(results)

    # red de detección: ¿alguien vivió la celda retenida? (usa el mundo real)
    heldout_ok = sim.last_world.no_heldout_consumption()

    # tokens: los baselines deterministas (EmpiricalAgent/DeterministicAgent)
    # no gastan LLM — no tienen contadores. getattr protege el sum.
    tokens = sum(getattr(ag, "total_prompt_tokens", 0) + getattr(ag, "total_completion_tokens", 0)
                 for ag in agents.values())
    calls = sum(getattr(ag, "total_calls", 0) for ag in agents.values())

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
        "exit_probes": exit_probes,
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
    ap.add_argument("--model", default="gemma2:9b", help="modelo Ollama/API")
    ap.add_argument("--backend", default="ollama", choices=["ollama", "openai"],
                    help="ollama local o API OpenAI-compatible (DeepSeek) — env: "
                         "WORLDLAB_LLM_API_KEY, WORLDLAB_LLM_BASE_URL, WORLDLAB_LLM_MODEL")
    ap.add_argument("--thinking", action="store_true",
                    help="DeepSeek v4: ACTIVA el modo razonamiento, que va apagado "
                         "por defecto (D-031). No usar en corridas: sobre el prompt "
                         "real cuesta 58,5 s y 5076 tokens de salida por decisión "
                         "contra 1,2 s y 30 sin razonar, y mide peor en el rumbo.")
    ap.add_argument("--density", default="all", choices=["all", "12", "7", "4"])
    ap.add_argument("--conditions", default="all", choices=["all", "sin_memoria", "memoria", "oraculo", "baseline_empirico"])
    ap.add_argument("--seeds", default="", help="lista de seeds específica, p.ej. '1,2,3' (override --worlds)")
    ap.add_argument("--smoke", action="store_true", help="prueba de humo: 1 mundo × densidad justa")
    ap.add_argument("--resume", action="store_true",
                    help="retomar: salta mundos ya completados (checkpoint por mundo)")
    ap.add_argument("--out-dir", default="data/silver/piloto",
                    help="directorio de salida (cada corrida con params distintos va a dir propio)")
    ap.add_argument("--force-sleep", type=int, default=None,
                    help="ABLATION: fija sleep_ticks e ignora el que pide el modelo "
                         "(separa 'no supo qué hacer' de 'no tuvo turnos'). "
                         "Marca los datos como ablation_no_confirmatorio.")
    ap.add_argument("--exp-prefix", default="piloto",
                    help="prefijo de archivos de experimento (p.ej. 'ronda1' para la ronda 1)")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    model_name = args.model
    # D-031: en DeepSeek v4 el razonamiento va DESACTIVADO. Sobre el prompt
    # real del agente, razonar cuesta 58.5 s y 5076 tokens de salida por
    # decision contra 1.2 s y 29 sin razonar — 49x el tiempo — y no mejora
    # nada: sin razonar mide 1.0 en los dos brazos, con razonamiento 2/3
    # en Q3. El `deepseek-chat` de gate_oraculo_ds ERA este mismo modo.
    if args.thinking:
        thinking = True
    elif args.backend == "openai":
        thinking = False          # DeepSeek v4: razonamiento apagado por defecto
    else:
        thinking = None           # ollama: se respeta el default del modelo
    client = LLMClient(backend=args.backend, model=model_name,
                       thinking=thinking)  # ollama local $0 / DeepSeek API

    if args.smoke:
        densities = [0.07]
        conditions = ["sin_memoria", "memoria", "oraculo"]
        worlds = [1]
        days = 12
    else:
        densities = [float(d) / 100 for d in ("12", "7", "4")] if args.density == "all" \
            else [float(args.density) / 100]
        conditions = CONDITIONS if args.conditions == "all" else [args.conditions]
        if args.seeds:
            worlds = [int(s) for s in args.seeds.split(",") if s.strip()]
        else:
            worlds = list(range(1, args.worlds + 1))
        days = args.days

    results = []
    t_start = time.time()

    # checkpoint: si ya hay summary, cargar lo completado (resume)
    summary_path = out_dir / f"{args.exp_prefix}_summary.json"
    done: set = set()
    if args.resume and summary_path.exists():
        try:
            prev = json.loads(summary_path.read_text())
            results = prev
            done = {(r["condition"], r["density"], r["seed"]) for r in prev}
            print(f"RESUME: {len(prev)} mundos ya completados — continúo desde ahí", flush=True)
        except json.JSONDecodeError:
            print("summary corrupto — empiezo de cero", flush=True)

    # INTERCALADO (exigencia de Opus): mundo por mundo, rotando condición en
    # CADA mundo (nunca dos mundos seguidos de la misma condición), densidad
    # rotando en bloque. Un diseño por bloques convertiría la deriva temporal
    # del proveedor en una diferencia entre condiciones indetectable después.
    n_cond = len(conditions)
    n_dens = len(densities)
    for seed in worlds:
        for k in range(n_cond * n_dens):
            condition = conditions[(k + seed) % n_cond]
            density = densities[(k // n_cond + seed) % n_dens]
            if (condition, density, seed) in done:
                continue  # ya completado en una corrida previa
            t0 = time.time()
            r = run_world(condition, density, seed, days, model_name, client,
                          out_dir, exp_prefix=args.exp_prefix,
                          force_sleep=args.force_sleep)
            dt = time.time() - t0
            r["elapsed_s"] = round(dt, 1)
            r["estado"] = ("ablation_no_confirmatorio" if args.force_sleep
                           else "desarrollo_no_confirmatorio")
            if args.force_sleep:
                r["force_sleep"] = args.force_sleep
            results.append(r)
            # CHECKPOINT: escribir el summary tras CADA mundo — si el proceso
            # muere (p.ej. el scheduler), el progreso no se pierde
            summary_path.write_text(json.dumps(results, ensure_ascii=False, indent=2))
            print(f"[{condition:16s} | d={density:.0%} | seed={seed}] "
                  f"superv={r['survivors']} en {dt:.0f}s "
                  f"tokens={r['tokens']} heldout={r['heldout_clean']}",
                  flush=True)

    print(f"\nResumen guardado: {summary_path}")
    print(f"Total: {len(results)} mundos en {(time.time()-t_start)/60:.1f} min")


if __name__ == "__main__":
    main()
