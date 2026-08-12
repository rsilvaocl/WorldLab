"""WorldLab — métricas de comunicación simbólica (D-008).

Información mutua entre símbolos emitidos y outcomes posteriores, con nulo
por PERMUTACIÓN (exigencia de Opus): el estimador de MI está sesgado al alza
con alfabeto grande y pocos datos; la significancia se compara contra la
distribución de MI al barajar los símbolos, no contra cero.

Con alfabeto de 4 símbolos y ~17% de señalización por azar, el nulo por
permutación es lo que separa "emergió señalización" de "ruido con formato".
"""

from __future__ import annotations

import math
import random
from collections import Counter
from typing import Dict, Iterable, List, Sequence, Tuple


def mutual_information(symbols: Sequence[str], outcomes: Sequence[str]) -> float:
    """MI discreta (nats) entre dos secuencias de labels del mismo largo."""
    assert len(symbols) == len(outcomes) and len(symbols) > 0
    n = len(symbols)
    pairs = Counter(zip(symbols, outcomes))
    sym_counts = Counter(symbols)
    out_counts = Counter(outcomes)

    mi = 0.0
    for (s, o), c in pairs.items():
        p_so = c / n
        p_s = sym_counts[s] / n
        p_o = out_counts[o] / n
        if p_so > 0 and p_s > 0 and p_o > 0:
            mi += p_so * math.log(p_so / (p_s * p_o))
    return mi


def mi_permutation_null(symbols: Sequence[str], outcomes: Sequence[str],
                        n_perm: int = 1000, seed: int = 1) -> Tuple[float, float]:
    """MI observada + p-valor contra el nulo por permutación.

    Nulo: se barajan los símbolos (rompiendo cualquier asociación) y se
    recalcula la MI. p = fracción de permutaciones con MI >= observada.
    p bajo => la señalización es improbable por azar.
    """
    observed = mutual_information(symbols, outcomes)
    rng = random.Random(seed)
    sym_list = list(symbols)
    count_ge = 0
    for _ in range(n_perm):
        shuffled = sym_list[:]
        rng.shuffle(shuffled)
        if mutual_information(shuffled, outcomes) >= observed:
            count_ge += 1
    return observed, count_ge / n_perm
