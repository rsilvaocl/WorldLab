"""WorldLab — memoria literal (spec §4.4).

Registro LITERAL de los eventos propios del agente: acción, contexto (región y
fase), resultado. Nada más. Sin campo de "aprendizaje", sin notas libres, sin
resúmenes — escribir conclusiones sería prestarle el andamio del razonamiento
y después no podríamos distinguir el modelo que construyó él del que le dimos.

Condiciones (spec §4.3):
- `llm_memoria`: memoria con los eventos del propio agente (mismo seed).
- `llm_memoria_corrupta`: MISMO VOLUMEN de registro, con hechos de OTRO seed.
  Si rinde igual que la memoria verdadera, lo que ayudaba era el volumen de
  contexto, no la información. Es el control que puede tumbar el resultado.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Renderer canónico (D-035, Terra 14/08)
#
# La fase va SIEMPRE en prosa —"fase 0 (clara)"— y nunca como entero suelto en
# un campo. Medido sobre 32 ontologías, mismo contenido y único cambio el
# render: con `"phase": 0` la recuperación agregada es 0,663 y A-oscura 0,490;
# en prosa, 0,962 y 0,990. No es límite del modelo: un entero suelto en un
# campo JSON no se liga, la misma fase en lenguaje natural sí.
#
# Por qué es corrección y no ajuste: la tabla del oráculo ya escribía la fase
# en prosa desde D-030, mientras la memoria la serializaba como entero porque
# así viene el evento del motor. Nadie decidió esa asimetría, y hacía que la
# comparación entre condiciones incluyera el formato. Mantener JSON en memoria
# y prosa en oráculo habría convertido el formato en tratamiento.
#
# CANÓNICO significa que lo usan TODAS las representaciones: literal, indexada
# y corrupta. Si dos brazos se comparan, la diferencia tiene que ser la
# estructura de recuperación, nunca JSON vs lenguaje natural.

FASE_NOMBRE = {0: "clara", 1: "oscura"}


def frase(resource: Any, region: Any, phase: Any, ganancias: List[Any],
          veces: int) -> str:
    """Una experiencia propia en prosa. Transformación FIEL y sin inferencia:
    no promedia, no infiere, no menciona celdas no vividas."""
    nombre = FASE_NOMBRE.get(phase, str(phase))
    vals = ", ".join(f"{g:+g}" for g in ganancias)
    return (f"Consumi {resource} en region {region} durante fase {phase} "
            f"({nombre}): energia observada [{vals}] en {veces} ocasion"
            f"{'es' if veces != 1 else ''}")


class LiteralMemory:
    def __init__(self, max_items: int = 60, label: str = "memory"):
        self.max_items = max_items
        self.label = label
        self.items: List[Dict[str, Any]] = []

    def record(self, ev: Any) -> None:
        """Registra un evento del motor tal como ocurrió (literal, sin interpretar)."""
        self.items.append({
            "day": ev.day,
            "tick": ev.tick,
            "action": ev.action,
            "outcome": ev.outcome,
            "region": ev.detail.get("region"),
            "phase": ev.detail.get("phase"),
            "resource": ev.detail.get("resource"),
            "energy_gain": ev.detail.get("energy_gain"),
        })
        if len(self.items) > self.max_items:
            self.items = self.items[-self.max_items:]

    def render(self) -> List[str]:
        """Los últimos eventos, en orden cronológico, con el renderer canónico.

        Sigue siendo un LOG episódico —un renglón por evento, sin agrupar— para
        que la diferencia con `IndexedMemory` sea la estructura de recuperación
        y no el formato (D-035)."""
        return [frase(it.get("resource"), it.get("region"), it.get("phase"),
                      [it.get("energy_gain")], 1)
                for it in self.items
                if it.get("action") == "consume" and it.get("outcome") == "ok"]

    def __len__(self) -> int:
        return len(self.items)

    def indice(self) -> Dict[Any, List[Optional[float]]]:
        """Los MISMOS eventos agrupados por (recurso, región, fase).

        No agrega nada que el agente no haya observado: es un reordenamiento
        de su propio registro. Base de IndexedMemory y de la corrupción, que
        debe compartir índice para ser comparable.
        """
        idx: Dict[Any, List[Optional[float]]] = {}
        for it in self.items:
            if it.get("action") != "consume" or it.get("outcome") != "ok":
                continue
            key = (it.get("resource"), it.get("region"), it.get("phase"))
            idx.setdefault(key, []).append(it.get("energy_gain"))
        return idx

    @classmethod
    def from_events(cls, events: List[Any], max_items: int = 60,
                    label: str = "memory_corrupta") -> "LiteralMemory":
        """Crea una memoria poblada con eventos que el agente NO vivió
        (p.ej. de otro seed) — la condición `llm_memoria_corrupta`."""
        mem = cls(max_items=max_items, label=label)
        for ev in events[-max_items:]:
            mem.record(ev)
        return mem


class IndexedMemory(LiteralMemory):
    """`memoria_indexada` — experiencias propias AGRUPADAS por celda (Terra, 14/08).

    CONSTRUCTO DISTINTO de `memoria_literal`, no un arreglo silencioso de ella:

      memoria_literal  — log episódico cronológico. Mide retención +
                         recuperación + agregación hechas por el LLM.
      memoria_indexada — las MISMAS experiencias propias, agrupadas por
                         (símbolo, región, fase), preservando la lista de
                         outcomes y su conteo. Mide uso de experiencia
                         ACCESIBLE.
      memoria_agregada — n, valores y media por celda. Mide aprendizaje
                         empírico con resumen externo. Brazo diagnóstico
                         aparte; NO se implementa acá.

    Por qué es admisible bajo D-020: no presta un modelo del mundo ni efectos
    no observados. Contiene exclusivamente lo que el agente vivió; no filtra
    B-oscura porque el agente nunca estuvo ahí. Lo que cambia es la
    ACCESIBILIDAD, no la información.

    Por qué hacía falta: la memoria literal no pasa el gate de lectura. Dos
    modelos distintos (gemma2:9b y deepseek-v4-flash) recuperan 5/9 y 3/9 de
    celdas que acaban de vivir y tienen escritas en el prompt, mientras ambos
    dan 9/9 leyendo la tabla plana del oráculo. El cuello no es retención: es
    indexación de un log crudo.

    NO promedia: la aritmética la sigue haciendo el agente. Ese es el límite
    exacto entre indexada y agregada.
    """

    def render(self) -> List[str]:
        """Agrupado por celda, con el renderer canónico (D-035). NO promedia."""
        return [frase(rkind, region, phase, gains, len(gains))
                for (rkind, region, phase), gains in self.filas()]

    def filas(self) -> List[Tuple[Tuple[Any, Any, Any], List[Any]]]:
        """El índice ordenado, antes de renderizar. Separar las dos capas es lo
        que permite corromper en la capa SEMÁNTICA y recién después aplicar el
        renderer canónico (exigencia de Terra): corromper el texto ya renderizado
        introduciría diferencias accidentales de estilo o longitud."""
        return sorted(self.indice().items(),
                      key=lambda kv: (str(kv[0][0]), str(kv[0][1]), kv[0][2]))

    @classmethod
    def corrupta_desde(cls, fuente: "LiteralMemory", seed: int = 0,
                       label: str = "memory_indexada_corrupta") -> "IndexedMemory":
        """Control de contenido: MISMO índice y MISMO volumen, outcomes permutados.

        Terra: para que `memoria_corrupta` siga siendo un control válido debe
        compartir índice y volumen con la condición que contrasta. Así la
        diferencia identifica CONTENIDO, no legibilidad ni longitud — que es
        justamente lo que la versión cronológica no podía separar.
        """
        import random as _random
        rng = _random.Random(seed)
        mem = cls(max_items=fuente.max_items, label=label)
        items = [dict(it) for it in fuente.items
                 if it.get("action") == "consume" and it.get("outcome") == "ok"]
        gains = [it.get("energy_gain") for it in items]
        rng.shuffle(gains)                      # permuta: mismo multiconjunto
        for it, g in zip(items, gains):
            it["energy_gain"] = g
            mem.items.append(it)
        return mem
