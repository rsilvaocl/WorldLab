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

from typing import Any, Dict, List, Optional


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

    def render(self) -> List[Dict[str, Any]]:
        """Los últimos eventos, en orden, tal cual (sin resumen)."""
        return list(self.items)

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

    def render(self) -> List[Dict[str, Any]]:
        filas = []
        for (rkind, region, phase), gains in sorted(
                self.indice().items(),
                key=lambda kv: (str(kv[0][0]), str(kv[0][1]), kv[0][2])):
            filas.append({
                "resource": rkind, "region": region, "phase": phase,
                "veces": len(gains),
                "energy_gain_observado": gains,   # la lista, sin promediar
            })
        return filas

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
