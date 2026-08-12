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

    @classmethod
    def from_events(cls, events: List[Any], max_items: int = 60,
                    label: str = "memory_corrupta") -> "LiteralMemory":
        """Crea una memoria poblada con eventos que el agente NO vivió
        (p.ej. de otro seed) — la condición `llm_memoria_corrupta`."""
        mem = cls(max_items=max_items, label=label)
        for ev in events[-max_items:]:
            mem.record(ev)
        return mem
