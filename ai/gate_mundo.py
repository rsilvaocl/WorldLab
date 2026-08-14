"""WorldLab — gate de viabilidad y exposición del MUNDO (spec de Terra, 14/08).

Qué problema resuelve. El probe de composición exige haber vivido A-clara,
A-oscura y B-clara, y la estructura de pagos actual hace irracional visitar B:
S1 rinde +8/+4 en A en AMBAS fases, mientras B rinde +7 y solo en fase clara
porque B-oscura está bloqueada. **A domina a B.** Por eso ni la política
reactiva optimizada pasa del 3,3% de consumos en B-clara: no es incapacidad,
es que B no paga. Sin exposición a B-clara, B-oscura no es una composición
sino una adivinanza.

La regla que hace honesto el rediseño (Terra): que "B pague" tiene que ser una
propiedad VERIFICABLE del mundo bajo una política informada, comprobada ANTES
de correr un solo LLM — no un ajuste retrospectivo hasta que el modelo
sobreviva. Este módulo implementa esa verificación.

Los tres gates, sobre 12 seeds fijas (1..12), 30 días, d=7%, 5 agentes:

  1. VIABILIDAD — la política informada sin restricción alcanza longevidad
     media >= 0.80 y >= 4/5 supervivientes en >= 9/12 seeds. Impide "arreglar
     B" volviendo el mundo invivible.

  2. EXPOSICIÓN — por seed, >= 3/5 agentes con >= 2 consumos ok en B-clara Y
     con exposición completa D-025 (consumos en A-clara, A-oscura y B-clara).
     En agregado, >= 75% de trayectorias agente×seed (45/60) pasan D-025 y la
     media es >= 2 consumos en B-clara por trayectoria. No se exige 5/5:
     convertiría el gate en un requisito de control perfecto y volvería a
     confundir las capas.

  3. B IMPORTA — la política libre supera a la variante A-only (ambas
     reoptimizadas en la misma familia y con el mismo presupuesto de búsqueda)
     en longevidad media >= +0.20 (seis días sobre 30), >= 1 superviviente
     adicional en >= 9/12 seeds, y >= +15 de energía final media.

Precisión de vocabulario que Terra exigió: esto NO demuestra que "A-only no
puede sobrevivir óptimamente" — eso requeriría un planificador óptimo. Lo que
demuestra es **presión de supervivencia hacia B para la mejor política
informada dentro de la familia evaluada**.

AVISO SOBRE "LE": aquí `longevidad` es días vividos / días totales, por agente.
NO es la LE de D-006, que es `(memoria − sin_memoria) / (oráculo −
sin_memoria)`, una razón ENTRE condiciones que exige corridas LLM. Terra usó
"LE" en el sentido de longevidad ("0.20 = seis días sobre 30"); se le da otro
nombre para que las dos métricas no se confundan nunca en el registro.
"""

from __future__ import annotations

import json
import os
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .baseline import BaselineParams, DeterministicAgent
from .world_state import (WorldConfig, WorldState, Entity,
                          build_separable_effects, separable_invariant_holds)
from .probe import _magnitude_level

SEEDS_GATE = tuple(range(1, 13))          # 12 seeds fijas
LIVED_CELLS = (("A", 0), ("A", 1), ("B", 0))
RETAINED_CELL = ("B", 1)
EVALUATED = ("S1", "S2", "S4")            # S3 es control (D-022)

# --- umbrales, fijados por Terra ANTES de ver ningún dato ------------------
G1_LONGEVIDAD_MEDIA = 0.80
G1_SUPERV_MIN = 4                          # de 5
G1_SEEDS_MIN = 9                           # de 12
G2_AGENTES_CON_B = 3                       # de 5, por seed
G2_CONSUMOS_B_MIN = 2                      # por agente
G2_FRACCION_D025 = 0.75                    # 45/60 trayectorias
G2_MEDIA_B_CLARA = 2.0
G3_DELTA_LONGEVIDAD = 0.20                 # seis días sobre 30
G3_DELTA_SUPERV_SEEDS = 9                  # de 12
G3_DELTA_ENERGIA = 15.0


class AOnlyAgent(DeterministicAgent):
    """La misma política informada, restringida a NO cruzar a B.

    Es el contrafáctico del gate 3: si esta variante rinde casi igual que la
    libre, B sigue siendo opcional y la exposición a B-clara dependerá de
    exploración residual — que es exactamente la situación que el gate existe
    para detectar.
    """

    def __init__(self, eid: str, params: BaselineParams, rng_seed: int = 0,
                 split_x: int = 15):
        super().__init__(eid, params, rng_seed)
        self.split_x = split_x

    def _en_A(self, x: int) -> bool:
        return x < self.split_x

    def decide(self, world: WorldState) -> Tuple[str, dict]:
        action, kwargs = super().decide(world)
        ent = world.entities[self.eid]
        if action == "move":
            nx = ent.x + int(kwargs.get("dx", 0))
            if not self._en_A(nx):
                return "rest", {}          # se niega a cruzar
        if action == "gather":
            tgt = world.entities.get(kwargs.get("target_eid", ""))
            if tgt is not None and not self._en_A(tgt.x):
                return "rest", {}
        return action, kwargs


def _policy(params: BaselineParams, a_only: bool, split_x: int):
    def policy(world: WorldState, aid: str, tick: int, rng: random.Random):
        cls = AOnlyAgent if a_only else DeterministicAgent
        ag = (cls(aid, params, rng_seed=tick, split_x=split_x) if a_only
              else cls(aid, params, rng_seed=tick))
        return ag.decide(world)
    return policy


# ---------------------------------------------------------------------------
# Métricas por corrida

def metricas_de_corrida(events_path: str, days: int,
                        eids: Tuple[str, ...]) -> Dict[str, Any]:
    """Longevidad, supervivientes, energía final y exposición por celda.

    Todo sale del JSONL de eventos: la misma fuente que audita el visor.
    """
    ultimo_dia: Dict[str, int] = {e: 0 for e in eids}
    energia: Dict[str, float] = {e: 0.0 for e in eids}
    vivos_final: set = set()
    expos: Dict[str, Dict[Tuple[str, int], int]] = {
        e: {c: 0 for c in LIVED_CELLS} for e in eids}

    with open(events_path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            o = json.loads(line)
            if o.get("type") == "snapshot":
                vivos = {a["eid"] for a in o["entities"] if a["kind"] == "agent"}
                for eid in vivos:
                    ultimo_dia[eid] = max(ultimo_dia.get(eid, 0), o["day"])
                vivos_final = vivos
                for eid, st in o.get("agents", {}).items():
                    if eid in energia:
                        energia[eid] = float(st.get("energy", 0.0))
            elif (o.get("type") == "event" and o.get("action") == "consume"
                  and o.get("outcome") == "ok"):
                d = o.get("detail", {})
                key = (d.get("region"), d.get("phase"))
                if o["eid"] in expos and key in expos[o["eid"]]:
                    expos[o["eid"]][key] += 1

    longev = {e: min(1.0, ultimo_dia.get(e, 0) / days) for e in eids}
    d025 = {e: all(expos[e][c] > 0 for c in LIVED_CELLS) for e in eids}
    return {
        "longevidad": longev,
        "longevidad_media": sum(longev.values()) / len(eids),
        "supervivientes": len(vivos_final & set(eids)),
        "energia_final_supervivientes": (
            sum(energia[e] for e in vivos_final & set(eids)) / len(vivos_final & set(eids))
            if (vivos_final & set(eids)) else 0.0),
        "consumos_b_clara": {e: expos[e][("B", 0)] for e in eids},
        "exposicion_d025": d025,
    }


def correr_mundo(cfg: WorldConfig, seed: int, params: BaselineParams,
                 a_only: bool, out_dir: str, tag: str) -> Dict[str, Any]:
    from .simulate import Simulator
    from .run_pilot import spawn_positions

    eids = tuple(f"a{i}" for i in range(5))
    ents = spawn_positions(list(eids), cfg, seed)
    split_x = int(cfg.width * cfg.region_split)
    sim = Simulator(cfg, _policy(params, a_only, split_x),
                    output_dir=out_dir, experiment_id=tag)
    sim.run(ents, seed=seed)
    path = os.path.join(out_dir, f"{tag}_seed{seed}.jsonl")
    m = metricas_de_corrida(path, cfg.days, eids)
    m["seed"] = seed
    return m


def evaluar(cfg: WorldConfig, params: BaselineParams, a_only: bool,
            out_dir: str, tag: str,
            seeds: Tuple[int, ...] = SEEDS_GATE) -> List[Dict[str, Any]]:
    return [correr_mundo(cfg, s, params, a_only, out_dir, f"{tag}_s{s}")
            for s in seeds]


# ---------------------------------------------------------------------------
# Los tres gates

def gate1_viabilidad(libre: List[Dict[str, Any]]) -> Dict[str, Any]:
    media = sum(m["longevidad_media"] for m in libre) / len(libre)
    ok_seeds = sum(1 for m in libre if m["supervivientes"] >= G1_SUPERV_MIN)
    return {
        "longevidad_media": round(media, 3),
        "seeds_con_4_de_5": ok_seeds,
        "pasa": media >= G1_LONGEVIDAD_MEDIA and ok_seeds >= G1_SEEDS_MIN,
    }


def gate2_exposicion(libre: List[Dict[str, Any]]) -> Dict[str, Any]:
    seeds_ok = 0
    trayectorias, con_d025, total_b = 0, 0, 0
    for m in libre:
        buenos = sum(1 for e, n in m["consumos_b_clara"].items()
                     if n >= G2_CONSUMOS_B_MIN and m["exposicion_d025"][e])
        if buenos >= G2_AGENTES_CON_B:
            seeds_ok += 1
        for e, n in m["consumos_b_clara"].items():
            trayectorias += 1
            total_b += n
            if m["exposicion_d025"][e]:
                con_d025 += 1
    frac = con_d025 / trayectorias if trayectorias else 0.0
    media_b = total_b / trayectorias if trayectorias else 0.0
    return {
        "seeds_con_3_agentes_expuestos": seeds_ok,
        "fraccion_d025": round(frac, 3),
        "media_consumos_b_clara": round(media_b, 2),
        "pasa": (seeds_ok == len(libre) and frac >= G2_FRACCION_D025
                 and media_b >= G2_MEDIA_B_CLARA),
    }


def gate3_b_importa(libre: List[Dict[str, Any]],
                    aonly: List[Dict[str, Any]]) -> Dict[str, Any]:
    dl = (sum(m["longevidad_media"] for m in libre)
          - sum(m["longevidad_media"] for m in aonly)) / len(libre)
    seeds_mas_superv = sum(1 for a, b in zip(libre, aonly)
                           if a["supervivientes"] >= b["supervivientes"] + 1)
    de = (sum(m["energia_final_supervivientes"] for m in libre)
          - sum(m["energia_final_supervivientes"] for m in aonly)) / len(libre)
    return {
        "delta_longevidad": round(dl, 3),
        "seeds_con_superviviente_extra": seeds_mas_superv,
        "delta_energia_final": round(de, 2),
        "pasa": (dl >= G3_DELTA_LONGEVIDAD
                 and seeds_mas_superv >= G3_DELTA_SUPERV_SEEDS
                 and de >= G3_DELTA_ENERGIA),
    }


GRID = tuple(BaselineParams(eat_threshold=e, build_min=b, exploration=x)
             for e in (20.0, 30.0, 40.0)
             for b in (4.0, 6.0)
             for x in (0.05, 0.15, 0.25))
SEEDS_TUNING = (101, 102, 103)     # DISJUNTAS de SEEDS_GATE: no se afina y evalúa
                                   # sobre los mismos mundos


def reoptimizar(cfg: WorldConfig, a_only: bool, out_dir: str,
                tag: str) -> BaselineParams:
    """Mejor parámetro de la familia para ESTA tabla, con el MISMO presupuesto
    de búsqueda para las dos políticas (exigencia de Terra en el gate 3).

    Sin esto, el gate 3 compararía una política libre afinada para la tabla
    vieja contra una A-only nunca afinada, y la diferencia mediría el ajuste,
    no la importancia de B. Se afina en seeds DISJUNTAS de las del gate.
    """
    mejor, mejor_score = GRID[0], -1.0
    for i, p in enumerate(GRID):
        ms = evaluar(cfg, p, a_only, out_dir, f"{tag}_tune{i}", SEEDS_TUNING)
        score = sum(m["longevidad_media"] for m in ms) / len(ms)
        if score > mejor_score:
            mejor, mejor_score = p, score
    return mejor


def evaluar_tabla(cfg: WorldConfig, params: Optional[BaselineParams],
                  out_dir: str, tag: str,
                  seeds: Tuple[int, ...] = SEEDS_GATE,
                  reoptimizar_params: bool = True) -> Dict[str, Any]:
    if reoptimizar_params:
        p_libre = reoptimizar(cfg, False, out_dir, f"{tag}_opt_libre")
        p_aonly = reoptimizar(cfg, True, out_dir, f"{tag}_opt_aonly")
    else:
        p_libre = p_aonly = params
    libre = evaluar(cfg, p_libre, False, out_dir, f"{tag}_libre", seeds)
    aonly = evaluar(cfg, p_aonly, True, out_dir, f"{tag}_aonly", seeds)
    g1, g2, g3 = (gate1_viabilidad(libre), gate2_exposicion(libre),
                  gate3_b_importa(libre, aonly))
    return {"gate1_viabilidad": g1, "gate2_exposicion": g2,
            "gate3_b_importa": g3,
            "pasa_todo": g1["pasa"] and g2["pasa"] and g3["pasa"],
            "params_libre": vars(p_libre), "params_aonly": vars(p_aonly),
            "n_seeds": len(seeds)}


# ---------------------------------------------------------------------------
# Candidatas de tabla + selección por mínimo cambio L1

def spec_a_efectos(spec: Dict[str, Tuple[float, float, float]]):
    return build_separable_effects(
        base={s: v[0] for s, v in spec.items()},
        delta_region={s: {"B": v[1]} for s, v in spec.items() if v[1]},
        delta_phase={s: {1: v[2]} for s, v in spec.items() if v[2]})


def invariantes_ok(spec: Dict[str, Tuple[float, float, float]]) -> bool:
    """Separabilidad + D-022 (retenida en nivel distinto) + S3 control."""
    eff = spec_a_efectos(spec)
    if not separable_invariant_holds(eff):
        return False
    if any(eff[("S3", r, p)] != 0 for r in ("A", "B") for p in (0, 1)):
        return False
    for s in EVALUATED:
        vividas = {_magnitude_level(eff[(s, r, p)]) for r, p in LIVED_CELLS}
        if _magnitude_level(eff[(s, *RETAINED_CELL)]) in vividas:
            return False
    return True


def l1(a: Dict[str, Tuple[float, float, float]],
       b: Dict[str, Tuple[float, float, float]]) -> float:
    """Distancia L1 entre dos tablas, sobre las 16 celdas."""
    ea, eb = spec_a_efectos(a), spec_a_efectos(b)
    return sum(abs(ea[k] - eb[k]) for k in ea)


def prefiltro_analitico(spec: Dict[str, Tuple[float, float, float]],
                        margen: float = 2.0) -> bool:
    """Condición NECESARIA barata, antes de gastar 24 simulaciones.

    Simular cada candidata cuesta ~7 min; el espacio tiene cientos. Este
    filtro descarta por aritmética las que no pueden pasar el gate 3, sin
    reemplazarlo: pasar el prefiltro NO implica pasar el gate — el mundo
    simulado decide, porque el traslado, el metabolismo y la ventana de fase
    no están en esta cuenta.

    Exige dos cosas:
      1. B-clara tiene que ganarle a A-clara por al menos `margen`, o no hay
         razón de cruzar (es el defecto actual: A rinde +8 y B +7).
      2. A tiene que seguir siendo vivible en AMBAS fases: si el mejor valor
         de A-oscura fuera <= 0, el mundo se volvería intransitable cuando la
         barrera cierra B, y el gate 1 caería. Arreglar B rompiendo el mundo
         es justamente lo que el gate 1 prohíbe.
    """
    eff = spec_a_efectos(spec)
    simbolos = [s for s in spec if s != "S3"]
    mejor = lambda r, p: max(eff[(s, r, p)] for s in simbolos)
    if mejor("B", 0) < mejor("A", 0) + margen:
        return False
    if mejor("A", 0) <= 0 or mejor("A", 1) <= 0:
        return False
    return True


def candidatas(base_spec: Dict[str, Tuple[float, float, float]],
               deltas: Tuple[float, ...] = (-4, -3, -2, -1, 0, 1, 2, 3, 4),
               simbolos: Tuple[str, ...] = EVALUATED
               ) -> List[Dict[str, Tuple[float, float, float]]]:
    """Tablas candidatas ordenadas por CAMBIO L1 CRECIENTE respecto de la actual.

    Se varían δ_región Y δ_fase de los símbolos evaluados. δ_región es el
    término que el gate 3 interroga (cuánto rinde B), pero variarlo SOLO deja
    el espacio vacío: subir B-clara por encima de A-clara empuja B-oscura al
    mismo nivel de magnitud que B-clara y rompe D-022, porque
    B-oscura = B-clara + δ_fase. La celda retenida solo vuelve a separarse
    moviendo δ_fase. Base y S3 (el control) quedan fijos.

    El orden por L1 es lo que vuelve el rediseño reproducible: se toma la
    PRIMERA que pase los tres gates, no la que mejor se vea después de mirar
    los resultados.
    """
    import itertools
    out = []
    pares = list(itertools.product(deltas, repeat=2))       # (δδ_región, δδ_fase)
    for combo in itertools.product(pares, repeat=len(simbolos)):
        spec = dict(base_spec)
        for s, (ddr, ddp) in zip(simbolos, combo):
            b, dr, dp = base_spec[s]
            spec[s] = (b, dr + ddr, dp + ddp)
        if not invariantes_ok(spec):
            continue
        out.append(spec)
    out.sort(key=lambda s: l1(s, base_spec))
    return out
