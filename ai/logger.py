"""WorldLab — logger de eventos a JSONL (fase 0).

Base del replay y del visor: cada evento del mundo se escribe en una línea
JSON con schema estable. El visor HTML (fase 1) lee estos archivos.

Formato de línea (una por evento):
  {"day": 1, "tick": 0, "eid": "a0", "action": "move", "outcome": "ok",
   "detail": {...}}

El archivo de eventos es la fuente de verdad para reconstruir la simulación.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional


class JsonlLogger:
    """Escribe eventos del mundo a un archivo JSONL (append-only)."""

    def __init__(self, path: str, meta: Optional[Dict[str, Any]] = None):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self._fh = open(path, "w", encoding="utf-8")
        if meta:
            self._write({"type": "meta", **meta})

    def _write(self, obj: Dict[str, Any]) -> None:
        self._fh.write(json.dumps(obj, ensure_ascii=False, sort_keys=True) + "\n")

    def log_event(self, event: Any) -> None:
        self._write({
            "type": "event",
            "day": event.day,
            "tick": event.tick,
            "eid": event.eid,
            "action": event.action,
            "outcome": event.outcome,
            "detail": event.detail,
        })

    def log_snapshot(self, day: int, tick: int, state: Any) -> None:
        """Snapshot periódico del estado (para replay sin re-ejecutar)."""
        self._write({
            "type": "snapshot",
            "day": day,
            "tick": tick,
            "phase": state.phase(),          # cosmético para el visor (clara/oscura)
            "entities": [
                {"eid": e.eid, "kind": e.kind, "x": e.x, "y": e.y, "attrs": e.attrs}
                for e in state.entities.values()
            ],
            "agents": {
                aid: {"energy": round(a.energy, 3),
                      "inventory": {k: round(v, 3) for k, v in a.inventory.items()}}
                for aid, a in state.agents.items()
            },
        })

    def log_trace(self, day: int, tick: int, eid: str, trace: Dict[str, Any]) -> None:
        """Agent trace: observación, objetivo, predicción, acción propuesta.
        Registro de SALIDA del agente, no prueba de procesos internos (v0.1 §29)."""
        self._write({"type": "trace", "day": day, "tick": tick, "eid": eid, **trace})

    def close(self) -> None:
        self._fh.close()


def read_jsonl(path: str) -> List[Dict[str, Any]]:
    """Lee un archivo JSONL completo (para replay/análisis)."""
    out: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out
