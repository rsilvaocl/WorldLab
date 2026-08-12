"""WorldLab — probe de composición (D-005, cuarta decisión de Opus).

El cruce retenido: el agente vive A-clara, A-oscura y B-clara, pero NUNCA
B-oscura. Al final se le pregunta por la situación nunca vivida y se compara
su predicción contra la respuesta correcta objetiva del motor.

- La predicción correcta solo puede venir de COMPONER las dos reglas
  aprendidas (región + fase) — imposible por memoria (nunca estuvo ahí).
- Respuesta correcta generada por el motor (ground_truth_effect), sin
  codificación subjetiva, sin Heider-Simmel.
- Es forced-choice (crítica #11 de Claude): se pregunta, NO se ejecuta la
  elección del agente; el ground truth se calcula aparte.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple


class CompositionProbe:
    """Ejecuta el probe de composición para un agente y registra resultados."""

    def __init__(self, world: Any, agent: Any, output_dir: str,
                 experiment_id: str):
        self.world = world
        self.agent = agent
        self.output_dir = output_dir
        self.experiment_id = experiment_id
        os.makedirs(output_dir, exist_ok=True)

    def run(self, rkind: str, region: str, phase: int) -> Dict[str, Any]:
        """Pregunta al agente por (rkind, region, phase) y compara con el motor."""
        truth = self.world.ground_truth_effect(rkind, region, phase)
        predicted = self.agent.predict_effect(rkind, region, phase)

        sign_correct = None
        if predicted is not None:
            sign_correct = (predicted > 0) == (truth > 0)
            error = abs(predicted - truth)
        else:
            error = None

        result = {
            "experiment": self.experiment_id,
            "eid": self.agent.eid,
            "probe_type": "composition",
            "rkind": rkind,
            "region": region,
            "phase": phase,
            "never_lived": self._never_lived(region, phase),
            "predicted_energy_change": predicted,
            "truth_energy_change": truth,
            "sign_correct": sign_correct,
            "absolute_error": round(error, 2) if error is not None else None,
        }
        self._append(result)
        return result

    def _never_lived(self, region: str, phase: int) -> bool:
        """¿La (region, phase) es inaccesible por barrera? (cruce retenido)."""
        return bool(self.world.config.phase_barriers.get((phase, region), False))

    def _append(self, result: Dict[str, Any]) -> None:
        path = os.path.join(self.output_dir, f"{self.experiment_id}_probes.jsonl")
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n")


def run_probe_set(world: Any, agent: Any, output_dir: str, experiment_id: str,
                  rkind: str = "S1") -> List[Dict[str, Any]]:
    """Corre los 4 probes del cruce: A-clara, A-oscura, B-clara, B-oscura.
    B-oscura es el probe de composición (nunca vivido); los otros 3 son
    controles de aprendizaje (deberían acertarse si el agente aprendió)."""
    probe = CompositionProbe(world, agent, output_dir, experiment_id)
    results = []
    for region in ("A", "B"):
        for phase in (0, 1):
            results.append(probe.run(rkind, region, phase))
    return results
