"""Tests de métricas de comunicación simbólica: MI + nulo por permutación."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.metrics import mutual_information, mi_permutation_null


def test_mi_zero_for_independent():
    """Símbolos y outcomes independientes => MI ≈ 0."""
    symbols = ["k1", "k2", "k3", "k4"] * 25
    outcomes = ["A", "B", "C", "D"] * 25  # correlación fija de posición, no de valor
    # barajar outcomes para independencia real
    import random
    rng = random.Random(7)
    shuffled_out = outcomes[:]
    rng.shuffle(shuffled_out)
    mi = mutual_information(symbols, shuffled_out)
    assert mi < 0.05


def test_mi_positive_for_dependent():
    """Símbolo determinista del outcome => MI claramente > 0."""
    symbols = [f"k{(i % 4) + 1}" for i in range(100)]
    outcomes = [f"O{(i % 4) + 1}" for i in range(100)]  # misma estructura
    mi = mutual_information(symbols, outcomes)
    assert mi > 0.5


def test_permutation_null_detects_signal():
    """Con señal real, el p-valor es bajo (la MI observada supera al nulo)."""
    symbols = [f"k{(i % 4) + 1}" for i in range(200)]
    outcomes = [f"O{(i % 4) + 1}" for i in range(200)]
    observed, p = mi_permutation_null(symbols, outcomes, n_perm=200, seed=1)
    assert p <= 0.05


def test_permutation_null_no_signal_high_p():
    """Sin señal, el p-valor es alto (la MI observada no supera al nulo)."""
    rng = __import__("random").Random(3)
    symbols = [f"k{rng.randint(1, 4)}" for _ in range(200)]
    outcomes = [f"O{rng.randint(1, 4)}" for _ in range(200)]
    observed, p = mi_permutation_null(symbols, outcomes, n_perm=200, seed=1)
    assert p > 0.05
