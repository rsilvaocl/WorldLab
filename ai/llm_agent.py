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
from .memory import LiteralMemory

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
                 model_name: str = "", near_trigger_radius: int = 0,
                 memory: Optional[LiteralMemory] = None):
        self.eid = eid
        self.client = client
        self.goal = goal
        self.system_rules = system_rules
        self.think_every = think_every        # ticks entre decisiones de respaldo
        self.hunger_threshold = hunger_threshold
        self.radius = radius
        self.model_name = model_name or client.describe()
        self.near_trigger_radius = near_trigger_radius  # 0 = trigger desactivado
        self.memory = memory                  # registro literal de eventos propios (o corrupto)
        self.total_calls = 0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0

    def record_outcome(self, ev) -> None:
        """El motor le entrega el resultado real de su acción para la memoria."""
        if self.memory is not None:
            self.memory.record(ev)

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

    def decide(self, world: WorldState):
        """Devuelve (action, kwargs, trace, horizonte). Si no piensa, rest."""
        think, reason = self._should_think(world)
        if not think:
            return "rest", {}, None, None

        observation = self._build_observation(world)
        action, kwargs, raw = self._ask_model(observation)

        # D-018: el agente elige su propio horizonte de despertar (en ticks)
        horizonte = self._parse_horizonte(raw)

        trace = {
            "observation": observation,
            "reason": reason,
            "goal": self.goal,
            "proposed_action": {"action": action, "args": kwargs},
            "sleep_ticks": horizonte,
            "model": self.model_name,
            "raw_response": raw,
        }
        return action, kwargs, trace, horizonte

    @staticmethod
    def _parse_horizonte(raw) -> Optional[int]:
        """sleep_ticks válido: entero 1..96; inválido => 1 (despertar pronto)."""
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                return 1
        if not isinstance(raw, dict):
            return 1
        try:
            h = int(raw.get("sleep_ticks", 1))
            return max(1, min(96, h))
        except (TypeError, ValueError):
            return 1

    # ------------------------------------------------------------------
    def _build_observation(self, world: WorldState) -> Dict[str, Any]:
        agent = world.agents[self.eid]
        vis = world.visible_to(self.eid, radius=self.radius)
        obs = {
            "day": world.day,
            "tick": world.tick,
            "energy": round(agent.energy, 1),
            "inventory": {k: round(v, 1) for k, v in agent.inventory.items()},
            "position": vis.get("position", [0, 0]),
            "region": vis.get("region", ""),
            "phase": vis.get("phase", 0),
            "visible": vis.get("visible", []),
            "heard": vis.get("heard", []),
        }
        # memoria literal: registro de eventos propios (o corruptos, condición aparte)
        if self.memory is not None:
            obs["memory"] = self.memory.render()
        return obs

    def _make_prediction(self, world: WorldState) -> Dict[str, Any]:
        """ELIMINADO del flujo de decisión (crítica #5 y #12 de Opus/Claude).

        El world model NO se presta: si le damos predicciones nuestras, después
        no podemos preguntarnos si lo construyó él. Donde se mide su predicción
        es en predict_effect() — pregunta sin decir nada (forced-choice)."""
        return {"risk_note": "world model NO prestado (el agente no recibe predicciones)"}

    def _ask_model(self, observation: Dict[str, Any]) -> Tuple[str, Dict[str, Any], str]:
        system = self._system_prompt()
        user = (
            "Estado actual:\n" + json.dumps(observation, ensure_ascii=False) +
            "\n\nResponde SOLO con JSON: {\"action\": \"...\", \"args\": {...}, \"sleep_ticks\": N}\n"
            "donde sleep_ticks (1..96) = en cuántos ticks quieres volver a decidir. "
            "Si no hay nada urgente, pide dormir más (ahorras energía y costos)."
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
