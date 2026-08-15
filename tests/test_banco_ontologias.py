"""Tests del banco de ontologías (composicion-bank-v1, spec de Terra).

Lo que protegen es la validez inferencial del banco: que todas las ontologías
cumplan las invariantes ANTES de cualquier llamada a un modelo, que sean
materialmente distintas, que el banco no premie contestar siempre lo mismo, y
que esté congelado en disco — el archivo versionado es la prueba de que no se
seleccionó ninguna tabla mirando respuestas.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from ai.banco_ontologias import (
    CELDAS_VIVIDAS, CELDA_RETENIDA, EVALUADOS, MAX_AZAR_CONSTANTE, N_BANCO,
    azar_constante, bootstrap_ic, cargar, efectos, generar_banco,
    invariantes_ok, permutacion_pareada, validar_banco,
)
from ai.probe import _magnitude_level
from ai.world_state import separable_invariant_holds

BANCO = Path(__file__).resolve().parent.parent / "data" / "banco" / "composicion_bank_v1.json"


def test_el_banco_congelado_existe_y_esta_versionado():
    """El archivo en disco es la prueba de que el banco precede a los datos."""
    assert BANCO.exists(), (
        "falta el banco congelado: sin él no hay garantía de que las tablas no "
        "se hayan elegido mirando respuestas de modelos")
    d = json.loads(BANCO.read_text(encoding="utf-8"))
    assert d["familia"] == "composicion-bank-v1"
    assert d["n"] == N_BANCO


def test_el_banco_congelado_es_reproducible_desde_su_seed():
    """Cualquiera puede regenerarlo y obtener exactamente el mismo banco."""
    d = json.loads(BANCO.read_text(encoding="utf-8"))
    regenerado = generar_banco(n=d["n"], seed=d["seed"])
    guardado = cargar(str(BANCO))
    assert regenerado == guardado


def test_todas_las_ontologias_del_banco_son_validas():
    for i, sp in enumerate(cargar(str(BANCO))):
        assert invariantes_ok(sp), f"ontología {i} no cumple las invariantes"


def test_separabilidad_en_todas():
    for sp in cargar(str(BANCO)):
        assert separable_invariant_holds(efectos(sp))


def test_D022_en_todas_la_retenida_cae_en_otro_nivel():
    """Si la retenida empata en nivel con una vivida, memorizar bastaría."""
    for i, sp in enumerate(cargar(str(BANCO))):
        eff = efectos(sp)
        for s in EVALUADOS:
            vividas = {_magnitude_level(eff[(s, r, p)]) for r, p in CELDAS_VIVIDAS}
            ret = _magnitude_level(eff[(s, *CELDA_RETENIDA)])
            assert ret not in vividas, f"ontología {i}, símbolo {s}"


def test_S3_es_control_plano_en_todas():
    for sp in cargar(str(BANCO)):
        eff = efectos(sp)
        assert all(eff[("S3", r, p)] == 0 for r in ("A", "B") for p in (0, 1))


def test_las_ontologias_son_materialmente_distintas():
    banco = cargar(str(BANCO))
    huellas = {tuple(sorted((s, *v) for s, v in sp.items())) for sp in banco}
    assert len(huellas) == len(banco)


def test_contestar_siempre_lo_mismo_NO_gana():
    """El nivel de azar de este banco no es 1/6: es la mejor estrategia
    constante. Si rindiera alto, el banco premiaría una heurística vacía."""
    az = azar_constante(cargar(str(BANCO)))
    assert az["acierto"] <= MAX_AZAR_CONSTANTE
    assert len(az["distribucion"]) >= 4, "los niveles retenidos deben repartirse"


def test_la_validacion_completa_pasa():
    assert validar_banco(cargar(str(BANCO)))["pasa"]


def test_un_banco_sesgado_es_rechazado():
    """Control negativo del validador: si todas las retenidas cayeran en el
    mismo nivel, contestar siempre ese nivel daría 1.0 y el banco no mediría
    composición."""
    sesgado = [{"S1": (0.0, 0.0, 0.0), "S2": (0.0, 0.0, 0.0),
                "S3": (0.0, 0.0, 0.0), "S4": (0.0, 0.0, 0.0)}] * 4
    az = azar_constante(sesgado)
    assert az["acierto"] == 1.0
    assert not validar_banco(sesgado, n=4)["pasa"]


def test_el_generador_es_determinista():
    assert generar_banco(n=8, seed=123) == generar_banco(n=8, seed=123)
    assert generar_banco(n=8, seed=123) != generar_banco(n=8, seed=124)


# --- inferencia ------------------------------------------------------------

def test_permutacion_detecta_un_efecto_real():
    difs = [0.4, 0.35, 0.5, 0.3, 0.45, 0.4, 0.55, 0.3] * 4
    r = permutacion_pareada(difs, n_perm=4000, seed=1)
    assert r["n_ontologias"] == 32
    assert r["p_valor"] < 0.01


def test_permutacion_NO_detecta_ruido_centrado_en_cero():
    difs = [0.2, -0.2, 0.1, -0.1, 0.3, -0.3, 0.0, 0.05] * 4
    r = permutacion_pareada(difs, n_perm=4000, seed=1)
    assert r["p_valor"] > 0.20


def test_el_bootstrap_remuestrea_ontologias():
    difs = [0.4, 0.35, 0.5, 0.3, 0.45, 0.4, 0.55, 0.3] * 4
    ic = bootstrap_ic(difs, n_boot=4000, seed=1)
    assert ic["ic_bajo"] < sum(difs) / len(difs) < ic["ic_alto"]
    assert ic["ic_bajo"] > 0, "un efecto claro no debe cruzar cero"


def test_un_IC_que_cruza_cero_se_ve():
    difs = [0.2, -0.2, 0.1, -0.1, 0.3, -0.3, 0.0, 0.05] * 4
    ic = bootstrap_ic(difs, n_boot=4000, seed=1)
    assert ic["ic_bajo"] < 0 < ic["ic_alto"]


# --- banco v2: el confirmatorio (D-035) ------------------------------------

BANCO_V2 = Path(__file__).resolve().parent.parent / "data" / "banco" / "composicion_bank_v2.json"


def test_el_banco_v2_existe_con_su_seed_preregistrada():
    """Condición de Terra: el v1 pasa a ser banco de CALIBRACIÓN del
    instrumento y la inferencia de composición corre sobre un banco nuevo con
    seed registrada antes de llamar a ningún modelo."""
    assert BANCO_V2.exists()
    d = json.loads(BANCO_V2.read_text(encoding="utf-8"))
    assert d["seed"] == 20260815
    assert d["n"] == N_BANCO
    assert generar_banco(n=d["n"], seed=d["seed"]) == cargar(str(BANCO_V2))


def test_el_v2_es_DISJUNTO_del_v1():
    """Sin esto, reutilizaríamos para inferencia las mismas tablas sobre las que
    se auditó el renderer — que es la selección post hoc que se quiere evitar."""
    huella = lambda banco: {tuple(sorted((s, *v) for s, v in sp.items())) for sp in banco}
    assert not (huella(cargar(str(BANCO_V2))) & huella(cargar(str(BANCO)))), (
        "el banco confirmatorio comparte ontologías con el de calibración")


def test_el_v2_pasa_su_propia_validacion():
    v = validar_banco(cargar(str(BANCO_V2)))
    assert v["pasa"]
    assert v["azar_constante"]["acierto"] <= MAX_AZAR_CONSTANTE


def test_la_unilateral_tiene_mas_potencia_cuando_la_direccion_esta_declarada():
    """La réplica declara la dirección de antemano (D-036): la bilateral
    regalaría la mitad de la potencia por no usar una hipótesis ya escrita."""
    from ai.banco_ontologias import permutacion_unilateral
    difs = [-0.15, -0.2, -0.1, -0.25, -0.05, -0.18] * 5 + [0.05, 0.0]
    uni = permutacion_unilateral(difs, n_perm=4000, seed=1)
    bil = permutacion_pareada(difs, n_perm=4000, seed=1)
    assert uni["cola"] == "menor"
    assert uni["p_valor"] <= bil["p_valor"]


def test_la_unilateral_NO_premia_un_efecto_en_la_direccion_contraria():
    from ai.banco_ontologias import permutacion_unilateral
    difs = [0.3] * 16 + [0.25] * 16          # efecto fuerte, dirección opuesta
    assert permutacion_unilateral(difs, n_perm=4000, seed=1)["p_valor"] > 0.9
