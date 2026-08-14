"""WorldLab — banco de ontologías para `composicion-bank-v1` (Terra, 14/08).

EL PROBLEMA QUE RESUELVE. Bajo exposición dirigida (Fase E, D-033) los seeds
dejaron de ser observaciones: la exposición está estandarizada, los efectos del
mundo son deterministas (D-009/D-015) y con temperature=0 el prompt y la
respuesta son idénticos en todo seed. Medido: σ_Δ = 0,0 exacto en 8 seeds. No
es poca varianza — es que ocho seeds son ocho ejecuciones del MISMO ítem.

LA SALIDA (Terra): mantener la Fase E exactamente estandarizada y hacer variar
la ONTOLOGÍA. Cada tabla genera prompts, memorias y respuestas materialmente
distintos, con la exposición igual de controlada. La unidad inferencial vuelve
a ser legítima: la ontología, no el seed ni el agente.

Esto NO reemplaza el mundo ecológico. Son dos familias declaradas:
  ecologia-v1        — supervivencia y navegación, tabla actual congelada, sin
                       pretensión de composición poblacional.
  composicion-bank-v1 — este banco, para medir generalización composicional.

REGLA QUE LO HACE HONESTO: el banco se genera y se CONGELA en disco antes de
cualquier llamada a un modelo. No se selecciona ni se descarta una tabla según
las respuestas de nadie. El archivo versionado es la prueba.

Cada ontología satisface, verificado antes de cualquier llamada:
  - separabilidad (efecto = base + δ_región + δ_fase);
  - B-oscura retenida y nunca expuesta;
  - D-022: el nivel de magnitud de la retenida difiere del de las tres vividas;
  - mismos símbolos, misma geometría, mismo protocolo E/P;
  - S3 control, plano en cero y fuera del score.

NIVEL DE AZAR DE ESTE BANCO. No es 1/6. Como la respuesta se puntúa por nivel
de magnitud, la referencia correcta es la MEJOR ESTRATEGIA CONSTANTE: contestar
siempre el mismo nivel. `azar_constante()` la calcula sobre el banco concreto,
y el banco se rechaza si esa estrategia rinde demasiado — un banco donde
contestar siempre lo mismo funciona no mide composición.
"""

from __future__ import annotations

import collections
import json
import os
import random
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .probe import _magnitude_level
from .world_state import build_separable_effects, separable_invariant_holds

SIMBOLOS: Tuple[str, ...] = ("S1", "S2", "S3", "S4")
EVALUADOS: Tuple[str, ...] = ("S1", "S2", "S4")     # S3 es control (D-022)
CELDAS_VIVIDAS: Tuple[Tuple[str, int], ...] = (("A", 0), ("A", 1), ("B", 0))
CELDA_RETENIDA: Tuple[str, int] = ("B", 1)

N_BANCO = 32              # mínimo de Terra: cubre σ_Δ ≈ 0,44 con potencia 0,90
MAX_AZAR_CONSTANTE = 0.40  # si contestar siempre lo mismo rinde más, el banco no sirve


Spec = Dict[str, Tuple[float, float, float]]        # símbolo -> (base, δ_región, δ_fase)


def efectos(spec: Spec) -> Dict[Tuple[str, str, int], float]:
    return build_separable_effects(
        base={s: v[0] for s, v in spec.items()},
        delta_region={s: {"B": v[1]} for s, v in spec.items() if v[1]},
        delta_phase={s: {1: v[2]} for s, v in spec.items() if v[2]})


def invariantes_ok(spec: Spec) -> bool:
    """Todas las condiciones que Terra exige ANTES de cualquier llamada."""
    if set(spec) != set(SIMBOLOS):
        return False
    eff = efectos(spec)
    if not separable_invariant_holds(eff):
        return False
    if any(eff[("S3", r, p)] != 0 for r in ("A", "B") for p in (0, 1)):
        return False
    for s in EVALUADOS:
        vividas = {_magnitude_level(eff[(s, r, p)]) for r, p in CELDAS_VIVIDAS}
        if _magnitude_level(eff[(s, *CELDA_RETENIDA)]) in vividas:
            return False
    return True


def azar_constante(banco: Sequence[Spec]) -> Dict[str, Any]:
    """Rendimiento de la MEJOR estrategia constante sobre el banco.

    Es el nivel de azar real de este benchmark: si contestar siempre el mismo
    nivel de magnitud acierta mucho, el banco premia una heurística vacía y no
    mide composición. Se calcula sobre la celda retenida, que es lo que se
    puntúa.
    """
    niveles = [_magnitude_level(efectos(sp)[(s, *CELDA_RETENIDA)])
               for sp in banco for s in EVALUADOS]
    if not niveles:
        return {"mejor_nivel": None, "acierto": 0.0, "distribucion": {}}
    cuenta = collections.Counter(niveles)
    mejor, n = cuenta.most_common(1)[0]
    return {
        "mejor_nivel": mejor,
        "acierto": round(n / len(niveles), 3),
        "distribucion": {str(k): v for k, v in sorted(cuenta.items())},
    }


def generar_banco(n: int = N_BANCO, seed: int = 20260814,
                  rango_base: Tuple[int, int] = (-9, 9),
                  rango_delta: Tuple[int, int] = (-12, 12)) -> List[Spec]:
    """Banco determinista de `n` ontologías válidas y materialmente distintas.

    Determinista por seed para que sea reproducible y auditable: cualquiera
    puede regenerarlo y obtener el mismo banco. No mira ninguna respuesta de
    ningún modelo — no puede, se genera antes de que exista una.
    """
    rng = random.Random(seed)
    banco: List[Spec] = []
    vistos: set = set()
    intentos = 0
    while len(banco) < n and intentos < 400_000:
        intentos += 1
        spec: Spec = {"S3": (0.0, 0.0, 0.0)}
        for s in EVALUADOS:
            spec[s] = (float(rng.randint(*rango_base)),
                       float(rng.randint(*rango_delta)),
                       float(rng.randint(*rango_delta)))
        if not invariantes_ok(spec):
            continue
        huella = tuple(sorted((s, *v) for s, v in spec.items()))
        if huella in vistos:
            continue
        vistos.add(huella)
        banco.append(spec)
    if len(banco) < n:
        raise RuntimeError(f"solo se generaron {len(banco)} de {n} ontologías")
    return banco


def validar_banco(banco: Sequence[Spec], n: int = N_BANCO) -> Dict[str, Any]:
    """Chequeo completo del banco. Se corre ANTES de la primera llamada."""
    todas_ok = all(invariantes_ok(sp) for sp in banco)
    az = azar_constante(banco)
    huellas = {tuple(sorted((s, *v) for s, v in sp.items())) for sp in banco}
    return {
        "n": len(banco),
        "todas_validas": todas_ok,
        "todas_distintas": len(huellas) == len(banco),
        "azar_constante": az,
        "pasa": (len(banco) == n and todas_ok and len(huellas) == len(banco)
                 and az["acierto"] <= MAX_AZAR_CONSTANTE),
    }


# ---------------------------------------------------------------------------
# Congelado en disco

def guardar(banco: Sequence[Spec], path: str, seed: int) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "familia": "composicion-bank-v1",
            "seed": seed,
            "n": len(banco),
            "nota": ("Generado y CONGELADO antes de cualquier llamada a un "
                     "modelo. No se seleccionó ni descartó ninguna tabla según "
                     "respuestas de nadie."),
            "validacion": validar_banco(banco, n=len(banco)),
            "ontologias": [{s: list(v) for s, v in sp.items()} for sp in banco],
        }, f, ensure_ascii=False, indent=2)


def cargar(path: str) -> List[Spec]:
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    return [{s: tuple(v) for s, v in o.items()} for o in d["ontologias"]]


# ---------------------------------------------------------------------------
# Inferencia: permutación pareada + bootstrap

def permutacion_pareada(difs: Sequence[float], n_perm: int = 20000,
                        seed: int = 0) -> Dict[str, Any]:
    """Prueba principal (Terra): permutación pareada sobre las diferencias.

    Bajo la nula, el signo de cada diferencia es intercambiable. No asume
    normalidad, que con 32 proporciones acotadas es lo prudente.
    """
    xs = list(difs)
    if not xs:
        raise ValueError("sin diferencias")
    obs = sum(xs) / len(xs)
    rng = random.Random(seed)
    extremos = 0
    for _ in range(n_perm):
        m = sum(x if rng.random() < 0.5 else -x for x in xs) / len(xs)
        if abs(m) >= abs(obs) - 1e-12:
            extremos += 1
    return {"diferencia_media": round(obs, 4),
            "p_valor": round((extremos + 1) / (n_perm + 1), 4),
            "n_ontologias": len(xs)}


def bootstrap_ic(difs: Sequence[float], n_boot: int = 20000, seed: int = 0,
                 nivel: float = 0.95) -> Dict[str, float]:
    """IC percentil de la diferencia media, remuestreando ONTOLOGÍAS."""
    xs = list(difs)
    rng = random.Random(seed)
    medias = sorted(sum(rng.choice(xs) for _ in xs) / len(xs)
                    for _ in range(n_boot))
    lo = medias[int((1 - nivel) / 2 * n_boot)]
    hi = medias[int((1 + nivel) / 2 * n_boot) - 1]
    return {"ic_bajo": round(lo, 4), "ic_alto": round(hi, 4), "nivel": nivel}
