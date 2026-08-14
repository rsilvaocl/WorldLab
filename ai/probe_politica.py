"""WorldLab — probe de POLÍTICA: ¿dónde se rompe la cadena conocimiento→acción?

Diagnóstico pedido por Terra (14/08). El agente recita que S1 en A-clara vale
+8 y come S2 (−2) que tiene al lado. Antes de llamar a eso "fallo de control de
política" hay que descartar dos explicaciones alternativas: el horizonte de
decisión discreto y el costo de planificar cinco pasos.

Matriz contrafactual sobre estados CONSTRUIDOS CON EL MOTOR REAL (no
observaciones editadas a mano: el menú `acciones_disponibles` sale de
`world.available_actions()`, que es de donde el agente elige — si el menú
fuera sintético, el probe mediría otra cosa):

  A · selección inmediata, inventario — tiene S1 y S2 en inventario, con hambre.
      Ambos `consume` están en el menú. Cero navegación, cero horizonte.
      Elegir S2 aquí = falla la SELECCIÓN, no la planificación.

  B · selección inmediata, suelo — S1 y S2 ambos ADYACENTES.
      Ambos `gather` en el menú. Un paso, sin planificar.
      Elegir S2 aquí = falla la selección con el valor a la vista.

  C · planificación — S2 adyacente, S1 a `far` pasos (visible).
      Solo `gather S2` en el menú; llegar a S1 exige varios `move`.
      Elegir S2 SOLO aquí = falla la PLANIFICACIÓN, no la selección.

Lectura: si falla en A y B, la cadena se rompe en la selección de acción con
conocimiento y percepción perfectos. Si falla solo en C, es horizonte/costo de
planificación y NO es reportable como fallo de política.

Uso:
    python -m ai.probe_politica --backend openai --model deepseek-v4-flash \\
        --repeats 5 --no-thinking
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict, List, Optional, Tuple

from .model_adapter import LLMClient
from .world_state import WorldConfig, WorldState, Entity


# El símbolo bueno y el malo en A-clara salen de la config, no se escriben a mano.
def best_worst_in(cfg: WorldConfig, region: str, phase: int) -> Tuple[str, str]:
    vals = {s: cfg.consume_effects[(s, region, phase)]
            for s in sorted({k[0] for k in cfg.consume_effects})}
    best = max(vals, key=lambda s: vals[s])
    worst = min(vals, key=lambda s: vals[s])
    return best, worst


def build_state(cfg: WorldConfig, escenario: str, ax: int, ay: int,
                far: int, seed: int) -> Tuple[WorldState, str, str]:
    """Mundo mínimo y determinista para un escenario de la matriz.

    Solo el agente y los dos recursos en juego: sin cúmulos ni ruido, para que
    la elección no dependa de qué más había cerca.
    """
    good, bad = best_worst_in(cfg, "A", 0)
    ents = [Entity(eid="a0", kind="agent", x=ax, y=ay)]

    def res(eid, kind, x, y, amount=10.0):
        return Entity(eid=eid, kind="resource", x=x, y=y,
                      attrs={"kind": kind, "amount": amount,
                             "initial_amount": amount})

    if escenario == "A":       # ambos en inventario
        ents.append(res("r_bad", bad, ax + 1, ay))
        ents.append(res("r_good", good, ax - 1, ay))
    elif escenario == "B":     # ambos adyacentes en el suelo
        ents.append(res("r_bad", bad, ax + 1, ay))
        ents.append(res("r_good", good, ax - 1, ay))
    elif escenario == "C":     # malo adyacente, bueno lejos pero visible
        ents.append(res("r_bad", bad, ax + 1, ay))
        ents.append(res("r_good", good, ax, ay - far))
    else:
        raise ValueError(escenario)

    world = WorldState(cfg, ents, seed=seed)
    if escenario == "A":
        # inventario cargado: la decisión es puramente cuál consumir
        world.agents["a0"].inventory[good] = 3.0
        world.agents["a0"].inventory[bad] = 3.0
    world.agents["a0"].energy = 25.0     # con hambre (umbral 30)
    return world, good, bad


def run_matrix(cfg: WorldConfig, client: LLMClient, repeats: int, far: int,
               out_path: str) -> Dict[str, Any]:
    from .llm_agent import LLMAgent
    from .run_pilot import oracle_rules, world_geometry

    rows: List[Dict[str, Any]] = []
    # posiciones distintas dentro de A, para no medir un único punto del mapa
    posiciones = [(6, 8), (8, 12), (5, 18), (10, 10), (4, 14),
                  (9, 20), (7, 6), (11, 16), (3, 9), (12, 12)][:repeats]

    for escenario in ("A", "B", "C"):
        for i, (ax, ay) in enumerate(posiciones):
            world, good, bad = build_state(cfg, escenario, ax, ay, far, seed=100 + i)
            agent = LLMAgent("a0", client, goal="sobrevivir y maximizar energía",
                             system_rules=oracle_rules(cfg),
                             geometry=world_geometry(cfg),
                             model_name=client.describe())
            obs = agent._build_observation(world)
            assert obs["region"] == "A" and obs["phase"] == 0, "el escenario exige A-clara"
            action, kwargs, raw = agent._ask_model(obs, cfg.energy_per_tick)

            # ¿eligió el bueno o el malo?
            elegido = None
            if action == "consume":
                elegido = kwargs.get("rkind")
            elif action == "gather":
                tid = kwargs.get("target_eid", "")
                elegido = good if tid == "r_good" else (bad if tid == "r_bad" else None)
            elif action == "move":
                elegido = "move"

            rows.append({
                "escenario": escenario, "pos": [ax, ay], "accion": action,
                "args": kwargs, "elegido": elegido,
                "good": good, "bad": bad,
                "valor_good": cfg.consume_effects[(good, "A", 0)],
                "valor_bad": cfg.consume_effects[(bad, "A", 0)],
                "acepta_bueno": elegido == good,
                "acepta_malo": elegido == bad,
                "raw": raw[:300],
            })
            print(f"  [{escenario}] pos=({ax},{ay}) -> {action} {kwargs} "
                  f":: {'BUENO' if elegido == good else ('MALO' if elegido == bad else elegido)}")

    def tasa(esc: str, key: str) -> Optional[float]:
        sub = [r for r in rows if r["escenario"] == esc]
        return round(sum(1 for r in sub if r[key]) / len(sub), 3) if sub else None

    summary = {
        "model": client.describe(),
        "n_por_escenario": len(posiciones),
        "far": far,
        "simbolo_bueno": rows[0]["good"], "valor_bueno": rows[0]["valor_good"],
        "simbolo_malo": rows[0]["bad"], "valor_malo": rows[0]["valor_bad"],
        "A_inventario": {"elige_bueno": tasa("A", "acepta_bueno"),
                         "elige_malo": tasa("A", "acepta_malo")},
        "B_ambos_adyacentes": {"elige_bueno": tasa("B", "acepta_bueno"),
                               "elige_malo": tasa("B", "acepta_malo")},
        "C_bueno_lejos": {"elige_bueno": tasa("C", "acepta_bueno"),
                          "elige_malo": tasa("C", "acepta_malo")},
    }
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "rows": rows}, f, ensure_ascii=False, indent=2)
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description="Probe de política (matriz contrafactual)")
    ap.add_argument("--backend", default="openai", choices=["ollama", "openai"])
    ap.add_argument("--model", default=None)
    ap.add_argument("--repeats", type=int, default=5, help="posiciones por escenario")
    ap.add_argument("--far", type=int, default=5, help="distancia del recurso bueno en C")
    ap.add_argument("--no-thinking", action="store_true")
    ap.add_argument("--out", default="data/silver/probe_politica/matriz.json")
    args = ap.parse_args()

    from .run_pilot import make_world_config
    cfg = make_world_config(30)
    client = LLMClient(backend=args.backend, model=args.model, temperature=0.0,
                       thinking=False if args.no_thinking else None, timeout=120)
    good, bad = best_worst_in(cfg, "A", 0)
    print(f"probe de política · {client.describe()}")
    print(f"  en A-clara: {good}={cfg.consume_effects[(good,'A',0)]:+g} (bueno) · "
          f"{bad}={cfg.consume_effects[(bad,'A',0)]:+g} (malo)\n")
    summary = run_matrix(cfg, client, args.repeats, args.far, args.out)
    print("\n" + json.dumps(summary, ensure_ascii=False, indent=2))
    print("\nLectura: falla en A y B => la cadena se rompe en la SELECCIÓN de "
          "acción con conocimiento y percepción perfectos. Falla solo en C => "
          "es horizonte/costo de planificación y NO es reportable como fallo "
          "de política.")


if __name__ == "__main__":
    main()
