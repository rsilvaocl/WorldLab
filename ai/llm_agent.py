"""WorldLab — agente LLM (fase 2).

Conecta un modelo de lenguaje al mundo. Principios:
  - El LLM NUNCA modifica el mundo: propone (action, kwargs), el motor valida.
  - Piensa solo ante eventos (concepto §22 / Opus): no cada frame.
    Triggers: hambre (energía < umbral), agente adyacente, o cada think_every ticks.
  - El prompt es estable en el prefijo (reglas+acciones+objetivo, cache hits)
    y variable en el sufijo (percepción+estado).
  - Registra agent trace (observación, objetivo, predicción, acción) como
    salida del agente, no como prueba de procesos internos (v0.1 §29).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from .model_adapter import LLMClient
from .world_state import WorldState

# Acciones válidas -> kwargs esperados por el motor
VALID_ACTIONS = {
    "move": {"dx": int, "dy": int},
    "gather": {"target_eid": str, "amount": (int, float)},
    "consume": {"rkind": str, "amount": (int, float)},
    "drop": {"rkind": str, "amount": (int, float)},
    "pickup": {"target_eid": str},
    "give": {"target_eid": str, "rkind": str, "amount": (int, float)},
    "build": {"structure": str, "x": int, "y": int},
    "talk": {"message": str},
    "rest": {},
}


class LLMAgent:
    def __init__(self, eid: str, client: LLMClient, goal: str,
                 system_rules: str = "", think_every: int = 12,
                 hunger_threshold: float = 30.0, radius: int = 6,
                 model_name: str = "", near_trigger_radius: int = 0):
        self.eid = eid
        self.client = client
        self.goal = goal
        self.system_rules = system_rules
        self.think_every = think_every        # ticks entre decisiones de respaldo
        self.hunger_threshold = hunger_threshold
        self.radius = radius
        self.model_name = model_name or client.describe()
        self.near_trigger_radius = near_trigger_radius  # 0 = trigger desactivado
        self.total_calls = 0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0

    # ------------------------------------------------------------------
    def _should_think(self, world: WorldState) -> Tuple[bool, str]:
        agent = world.agents.get(self.eid)
        if agent is None:
            return False, "muerto"
        if agent.energy < self.hunger_threshold:
            return True, "hambre"
        # otro agente adyacente (trigger opcional, desactivado por defecto)
        if self.near_trigger_radius > 0:
            ent = agent.entity
            for other in world.agents.values():
                if other.entity.eid == self.eid:
                    continue
                if abs(other.entity.x - ent.x) + abs(other.entity.y - ent.y) <= self.near_trigger_radius:
                    return True, "otro_agente_cerca"
        if world.tick % self.think_every == 0:
            return True, "respaldo_cada_tick"
        return False, ""

    def decide(self, world: WorldState) -> Tuple[str, Dict[str, Any], Optional[Dict[str, Any]]]:
        """Devuelve (action, kwargs, trace). Si no piensa, (rest, {}, None)."""
        think, reason = self._should_think(world)
        if not think:
            return "rest", {}, None

        observation = self._build_observation(world)
        prediction = self._make_prediction(world)
        action, kwargs, raw = self._ask_model(observation, prediction)

        trace = {
            "observation": observation,
            "reason": reason,
            "goal": self.goal,
            "prediction": prediction,
            "proposed_action": {"action": action, "args": kwargs},
            "model": self.model_name,
            "raw_response": raw,
        }
        return action, kwargs, trace

    # ------------------------------------------------------------------
    def _build_observation(self, world: WorldState) -> Dict[str, Any]:
        agent = world.agents[self.eid]
        vis = world.visible_to(self.eid, radius=self.radius)
        # inventario y energía
        return {
            "day": world.day,
            "tick": world.tick,
            "energy": round(agent.energy, 1),
            "inventory": {k: round(v, 1) for k, v in agent.inventory.items()},
            "position": vis.get("position", [0, 0]),
            "visible": vis.get("visible", []),
        }

    def _make_prediction(self, world: WorldState) -> Dict[str, Any]:
        """World model v0: predicción simple de consecuencias inmediatas
        (se comparará contra el resultado real en el análisis)."""
        agent = world.agents[self.eid]
        ent = agent.entity
        # predecir qué pasaría si se mueve hacia cada recurso visible
        options = []
        for v in world.visible_to(self.eid, radius=self.radius).get("visible", []):
            if v["kind"] == "resource":
                options.append({
                    "target": v["eid"],
                    "kind": v["kind"],
                    "dist": abs(v["dx"]) + abs(v["dy"]),
                    "expected_energy_gain": 5.0 if v["kind"] == "food" else 1.0,
                })
        return {
            "options": sorted(options, key=lambda o: o["dist"])[:3],
            "risk_note": "sin world model entrenado (fase 2 básica)",
        }

    def _ask_model(self, observation: Dict[str, Any],
                   prediction: Dict[str, Any]) -> Tuple[str, Dict[str, Any], str]:
        system = self._system_prompt()
        user = (
            "Estado actual:\n" + json.dumps(observation, ensure_ascii=False) +
            "\n\nPredicciones disponibles (no vinculantes):\n" +
            json.dumps(prediction, ensure_ascii=False) +
            "\n\nResponde SOLO con JSON: {\"action\": \"...\", \"args\": {...}}"
        )
        try:
            raw = self.client.chat_json([
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ])
        except Exception as e:
            # si el modelo falla, el agente descansa (el mundo sigue)
            return "rest", {}, f"ERROR: {e}"
        self.total_calls += 1
        self.total_prompt_tokens += self.client.last_usage.get("prompt_tokens", 0)
        self.total_completion_tokens += self.client.last_usage.get("completion_tokens", 0)

        action = raw.get("action", "rest")
        args = raw.get("args", {})
        if action not in VALID_ACTIONS:
            action = "rest"
            args = {}
        if not isinstance(args, dict):
            args = {}
        # filtrar kwargs inválidos (el motor valida el resto)
        allowed = VALID_ACTIONS.get(action, {})
        kwargs = {k: v for k, v in args.items() if k in allowed}
        return action, kwargs, json.dumps(raw, ensure_ascii=False)

    def predict_effect(self, rkind: str, region: str, phase: int) -> Optional[float]:
        """FORCED-CHOICE PROBE (crítica #11 de Claude): pregunta al agente qué
        cree que pasaría si consumiera `rkind` en (region, phase), SIN ejecutar
        nada. Para la situación retenida (nunca vivida) solo puede acertar
        componiendo reglas aprendidas. Devuelve el cambio de energía predicho."""
        system = (
            "Eres un agente autónomo en un mundo 2D. "
            "Responde SOLO con JSON: {\"energy_change\": <número con signo>, \"reason\": \"...\"}"
        )
        user = (
            f"PREGUNTA HIPOTÉTICA (no es una acción, solo responde):\n"
            f"Si consumieras 1 unidad del recurso '{rkind}' estando en la región "
            f"{region} durante la fase {'oscura' if phase == 1 else 'clara'}, "
            f"¿cuánto cambiaría tu energía? Da el número con signo (+ sube, - baja, 0 nada)."
        )
        try:
            raw = self.client.chat_json([
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ])
        except Exception as e:
            return None
        self.total_calls += 1
        self.total_prompt_tokens += self.client.last_usage.get("prompt_tokens", 0)
        self.total_completion_tokens += self.client.last_usage.get("completion_tokens", 0)
        val = raw.get("energy_change")
        if val is None:
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    def _system_prompt(self) -> str:
        base = self.system_rules or (
            "Eres un agente autónomo en un mundo 2D.\n"
            "Reglas del mundo:\n"
            "- El mundo valida tus acciones: las imposibles se rechazan.\n"
            "- gather solo funciona si el recurso está a 1 casilla de distancia (adyacente). "
            "Si el recurso está más lejos, primero usa move para acercarte (dx,dy son pasos de 1 casilla).\n"
            "- consume convierte inventario en energía; come cuando tengas hambre.\n"
            "- drop/pickup/give funcionan solo en tu celda o casilla adyacente.\n"
            "- build construye una estructura en una casilla adyacente libre, consumiendo los materiales de su receta (definida en el mundo; tú solo eliges structure, x, y).\n"
            "- Solo percibes lo que está cerca (radio de visión limitado); lo que no ves, no sabes que existe.\n"
            "- La comunicación es SIMBÓLICA: talk emite símbolos del alfabeto del mundo (k1..k4), sin significado asignado. Costan energía; hablar solo cuando aporte. Lo que otros dicen llega a tu percepción como 'heard' si están cerca.\n"
            "Acciones disponibles (JSON): move{dx,dy}, gather{target_eid,amount}, "
            "consume{rkind,amount}, drop{rkind,amount}, pickup{target_eid}, "
            "give{target_eid,rkind,amount}, build{structure,x,y}, talk{message}, rest.\n"
            "Tu objetivo: " + self.goal + "\n"
            "Decide una sola acción para este instante. "
            "Responde SOLO con JSON válido, sin texto adicional."
        )
        return base

    def stats(self) -> Dict[str, Any]:
        return {
            "eid": self.eid,
            "model": self.model_name,
            "calls": self.total_calls,
            "prompt_tokens": self.total_prompt_tokens,
            "completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_prompt_tokens + self.total_completion_tokens,
        }
