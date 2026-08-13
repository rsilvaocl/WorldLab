"""Tests de D-022: requisito de discriminación de niveles (spec v1.1 de Opus).

Para cada símbolo EVALUADO (S1, S2, S4), el nivel de magnitud de la celda
retenida (B-oscura) debe ser DISTINTO del de las tres celdas vividas. Si la
retenida cae en el mismo nivel que una vivida, un agente que solo memoriza
acierta sin componer nada y el probe deja de medir modelado.

S3 queda EXCLUIDO del score de composición: sus cuatro celdas valen 0 por
definición (es material, no alimento) y su papel es el de control
"esto no se come".

Este test es PERMANENTE: falla si alguna edición de valores rompe la
separación de niveles (exigencia explícita de la spec v1.1).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.world_state import build_separable_effects
from ai.probe import _magnitude_level

# valores de la spec v1.1 (D-022, §3.1) — NO editar sin romper el test
EFFECT_SPEC = {
    "S1": (+8.0,  -9.0, -4.0),
    "S2": (-2.0,  +9.0, +3.0),
    "S3": ( 0.0,   0.0,  0.0),   # control: nunca alimenta, fuera del score
    "S4": (+1.0,  +6.0, -9.0),
}

LIVED_CELLS = [("A", 0), ("A", 1), ("B", 0)]   # B-oscura es la retenida
RETAINED_CELL = ("B", 1)
EVALUATED = ["S1", "S2", "S4"]                  # S3 excluido del score


def effects():
    return build_separable_effects(
        base={s: spec[0] for s, spec in EFFECT_SPEC.items()},
        delta_region={s: {"B": spec[1]} for s, spec in EFFECT_SPEC.items() if spec[1]},
        delta_phase={s: {1: spec[2]} for s, spec in EFFECT_SPEC.items() if spec[2]})


def test_separabilidad_se_mantiene():
    """Los efectos siguen siendo separables (invariante permanente previo)."""
    from ai.world_state import separable_invariant_holds
    assert separable_invariant_holds(effects())


def test_retenida_nivel_distinto_de_vividas():
    """D-022: la celda retenida debe caer en un nivel distinto al de las 3 vividas."""
    eff = effects()
    for rkind in EVALUATED:
        lived_levels = {_magnitude_level(eff[(rkind, r, p)]) for r, p in LIVED_CELLS}
        retained_level = _magnitude_level(eff[(rkind, *RETAINED_CELL)])
        assert retained_level not in lived_levels, (
            f"{rkind}: retenida en nivel {retained_level}, igual que una vivida "
            f"{sorted(lived_levels)} — memorizar bastaría para acertar, "
            f"el probe no mide composición")


def test_s3_excluido_del_score():
    """S3 es material (control 'no se come'): sus 4 celdas valen 0 y queda fuera."""
    eff = effects()
    levels = {_magnitude_level(eff[("S3", r, p)]) for r, p in [("A", 0), ("A", 1), ("B", 0), ("B", 1)]}
    assert levels == {3}, f"S3 debe ser 0 en las 4 celdas (nivel 3), se obtuvo {levels}"


def test_fase_tiene_efecto_propio():
    """δ_fase ≠ 0 en ≥2 recursos: si no, B-oscura == B-clara y no hay nada que componer."""
    n_with_phase_effect = sum(1 for s, spec in EFFECT_SPEC.items() if spec[2] != 0)
    assert n_with_phase_effect >= 2


def test_tabla_resultante_esperada():
    """Valores finales de la spec v1.1 (sanity check de la tabla 2x2)."""
    eff = effects()
    expected = {
        ("S1", "A", 0): 8, ("S1", "A", 1): 4, ("S1", "B", 0): -1, ("S1", "B", 1): -5,
        ("S2", "A", 0): -2, ("S2", "A", 1): 1, ("S2", "B", 0): 7, ("S2", "B", 1): 10,
        ("S3", "A", 0): 0, ("S3", "A", 1): 0, ("S3", "B", 0): 0, ("S3", "B", 1): 0,
        ("S4", "A", 0): 1, ("S4", "A", 1): -8, ("S4", "B", 0): 7, ("S4", "B", 1): -2,
    }
    for key, val in expected.items():
        assert abs(eff[key] - val) < 1e-9, f"{key}: esperado {val}, got {eff[key]}"


def test_baseline_sigue_sin_acertar_retenida_por_memoria():
    """El control del piloto: una tabla de promedios observados NO predice la
    celda nunca vivida. Con los nuevos valores, la retenida sigue fuera del
    alcance de la memoria (nivel distinto al de las vividas — probado arriba)."""
    eff = effects()
    # la retenida debe ser matemáticamente derivable por separabilidad:
    # B-oscura = A-oscura + (B-clara - A-clara)
    for rkind in EVALUATED:
        derived = eff[(rkind, "A", 1)] + (eff[(rkind, "B", 0)] - eff[(rkind, "A", 0)])
        assert abs(derived - eff[(rkind, "B", 1)]) < 1e-9, f"{rkind} no es separable"
