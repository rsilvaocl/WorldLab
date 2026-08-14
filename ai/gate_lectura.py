"""WorldLab — gate de LECTURA y cálculo de potencia (spec de Terra, 14/08).

GATE DE LECTURA. El contraste `memoria` vs `memoria_corrupta` no es
interpretable mientras la representación de memoria no pase recuperación de
información VIVIDA. Con la memoria literal cronológica, dos modelos distintos
(gemma2:9b y deepseek-v4-flash) recuperan 5/9 y 3/9 de celdas que acaban de
vivir y tienen escritas en el prompt, mientras ambos dan 9/9 leyendo la tabla
plana del oráculo. El cuello no es retención: es indexación de un log crudo.

Se pregunta SOLO por celdas realmente vividas, estratificado por símbolo,
región y fase, con la misma memoria, el mismo system prompt y el mismo formato
que la Fase E/P. El outcome es exactitud de nivel de magnitud (D-010).

Umbrales PRE-REGISTRADOS por Terra, antes de ver datos:
  - >= 0.75 de exactitud agregada, Y
  - >= 0.60 en CADA una de las tres celdas vividas.

Si falla, no se corre ni se interpreta el probe retenido para esa
representación de memoria. El resultado pasa a ser: "la memoria literal cruda
no es operativamente accesible para este agente" — que es un resultado, no un
fracaso.

Por qué el gate NO excluye mundos que fallen: excluir selectivamente sesga el
estimando. Es una fase de CALIBRACIÓN previa sobre la representación, no un
filtro de casos.

POTENCIA. La unidad estadística es el mundo/seed, no el agente ni el probe.
Contraste primario: `memoria_indexada − sin_memoria`, pareado por seed.
Efecto mínimo relevante Δ = 0.25 absoluto, bilateral, α = 0.05, potencia 0.90.
Se usa el límite superior del bootstrap al 80% de σ_Δ, no su media puntual,
para no subpotenciar por una estimación ruidosa del smoke.
"""

from __future__ import annotations

import json
import math
import os
import random
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .probe import _magnitude_level

CELDAS_VIVIDAS: Tuple[Tuple[str, int], ...] = (("A", 0), ("A", 1), ("B", 0))
SIMBOLOS: Tuple[str, ...] = ("S1", "S2", "S4")

# --- umbrales del gate, fijados por Terra ANTES de ver datos ---------------
GATE_AGREGADO = 0.75
GATE_POR_CELDA = 0.60

# --- parámetros de potencia, fijados por Terra -----------------------------
MDE = 0.25            # efecto mínimo relevante, absoluto
ALPHA = 0.05          # bilateral
POTENCIA = 0.90
Z_ALPHA = 1.96        # z_{1-α/2}
Z_BETA = 1.282        # z_{potencia}
N_MINIMO = 16


def correr_gate_lectura(agente: Any, verdad: Dict[Tuple[str, str, int], float],
                        simbolos: Tuple[str, ...] = SIMBOLOS,
                        celdas: Tuple[Tuple[str, int], ...] = CELDAS_VIVIDAS
                        ) -> Dict[str, Any]:
    """Pregunta SOLO por celdas vividas y evalúa por nivel de magnitud.

    Usa `agente.predict_effect`, el mismo camino que la Fase P: si el gate
    usara otro prompt, mediría otra cosa que la que después se puntúa.
    """
    filas: List[Dict[str, Any]] = []
    for rkind in simbolos:
        for region, phase in celdas:
            pred = agente.predict_effect(rkind, region, phase)
            real = verdad[(rkind, region, phase)]
            ok = (pred is not None
                  and _magnitude_level(pred) == _magnitude_level(real))
            filas.append({"rkind": rkind, "region": region, "phase": phase,
                          "predicho": pred, "real": real, "correcto": bool(ok)})

    def tasa(sub: Sequence[Dict[str, Any]]) -> float:
        return sum(1 for f in sub if f["correcto"]) / len(sub) if sub else 0.0

    por_celda = {f"{r}-{p}": tasa([f for f in filas
                                   if (f["region"], f["phase"]) == (r, p)])
                 for r, p in celdas}
    agregada = tasa(filas)
    return {
        "exactitud_agregada": round(agregada, 3),
        "por_celda": {k: round(v, 3) for k, v in por_celda.items()},
        "umbral_agregado": GATE_AGREGADO,
        "umbral_por_celda": GATE_POR_CELDA,
        "pasa": (agregada >= GATE_AGREGADO
                 and all(v >= GATE_POR_CELDA for v in por_celda.values())),
        "filas": filas,
    }


def agregar_gate(resultados: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Gate sobre varios agentes/seeds: se evalúa la REPRESENTACIÓN, no cada caso."""
    filas = [f for r in resultados for f in r["filas"]]
    if not filas:
        return {"pasa": False, "exactitud_agregada": 0.0, "por_celda": {}}
    def tasa(sub):
        return sum(1 for f in sub if f["correcto"]) / len(sub) if sub else 0.0
    por_celda = {f"{r}-{p}": round(tasa([f for f in filas
                                         if (f["region"], f["phase"]) == (r, p)]), 3)
                 for r, p in CELDAS_VIVIDAS}
    agregada = tasa(filas)
    return {
        "n_agentes": len(resultados),
        "n_preguntas": len(filas),
        "exactitud_agregada": round(agregada, 3),
        "por_celda": por_celda,
        "pasa": (agregada >= GATE_AGREGADO
                 and all(v >= GATE_POR_CELDA for v in por_celda.values())),
    }


# ---------------------------------------------------------------------------
# Potencia

def sigma_bootstrap_p80(diferencias: Sequence[float], n_boot: int = 5000,
                        seed: int = 0) -> Dict[str, float]:
    """σ de las diferencias pareadas + límite superior del bootstrap al 80%.

    Terra: usar el límite superior, no la media puntual, para no subpotenciar
    por una estimación ruidosa del smoke.
    """
    xs = list(diferencias)
    if len(xs) < 2:
        raise ValueError("hacen falta al menos 2 seeds para estimar σ")
    rng = random.Random(seed)

    def sd(v: Sequence[float]) -> float:
        m = sum(v) / len(v)
        return math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1))

    punt = sd(xs)
    reps = sorted(sd([rng.choice(xs) for _ in xs]) for _ in range(n_boot))
    return {"sigma_puntual": round(punt, 4),
            "sigma_p80": round(reps[int(0.80 * n_boot)], 4)}


def n_requerido(sigma: float, mde: float = MDE) -> int:
    """N de seeds para el contraste pareado, con el piso de 16 que fijó Terra.

        N = max(16, ceil( ((z_α + z_β) / Δ * σ_Δ)^2 ))
    """
    n = math.ceil(((Z_ALPHA + Z_BETA) / mde * sigma) ** 2)
    return max(N_MINIMO, n)


def plan_de_potencia(diferencias: Sequence[float], mde: float = MDE,
                     seed: int = 0) -> Dict[str, Any]:
    """Estimación completa a partir de las diferencias pareadas del piloto.

    σ_Δ == 0 NO devuelve el piso de 16: sería un fallo silencioso. Una varianza
    exactamente nula entre mundos no es "muy poca varianza", es la señal de que
    el seed no está variando nada que el probe pueda ver — y entonces el mundo
    no es la unidad estadística. Ocurrió de verdad: la Fase E estandariza la
    exposición, así que el contenido de la memoria es idéntico en todo seed y
    con temperature=0 la respuesta también. N no está definido en ese caso.
    """
    s = sigma_bootstrap_p80(diferencias, seed=seed)
    if s["sigma_puntual"] == 0.0:
        return {
            "n_seeds_observadas": len(diferencias),
            "diferencia_media": round(sum(diferencias) / len(diferencias), 4),
            **s,
            "mde": mde, "alpha": ALPHA, "potencia": POTENCIA,
            "n_requerido": None,
            "degenerado": True,
            "motivo": ("σ_Δ = 0 exacto: los seeds no difieren en nada que el "
                       "probe observe. El mundo no es la unidad estadística "
                       "bajo exposición dirigida; N no está definido."),
        }
    return {
        "n_seeds_observadas": len(diferencias),
        "diferencia_media": round(sum(diferencias) / len(diferencias), 4),
        **s,
        "mde": mde, "alpha": ALPHA, "potencia": POTENCIA,
        "n_con_sigma_puntual": n_requerido(s["sigma_puntual"], mde),
        "n_requerido": n_requerido(s["sigma_p80"], mde),
        "nota": ("la unidad es el mundo/seed; el contraste es "
                 "memoria_indexada − sin_memoria pareado por seed"),
    }
