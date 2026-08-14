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
                 memory: Optional[LiteralMemory] = None,
                 force_sleep: Optional[int] = None,
                 geometry: str = ""):
        self.eid = eid
        self.client = client
        self.goal = goal
        self.system_rules = system_rules
        # D-032: geometría de las regiones. Va en la MECÁNICA, idéntica en
        # las 4 condiciones — nunca en system_rules, que es lo que
        # distingue al oráculo. Dice dónde, no qué vale.
        self.geometry = geometry
        self.think_every = think_every        # ticks entre decisiones de respaldo
        self.hunger_threshold = hunger_threshold
        self.radius = radius
        self.model_name = model_name or client.describe()
        self.near_trigger_radius = near_trigger_radius  # 0 = trigger desactivado
        self.memory = memory                  # registro literal de eventos propios (o corrupto)
        # ABLATION (no experimento): si se fija, el horizonte del modelo se
        # IGNORA y se usa este valor. Sirve para separar "no sabe qué hacer"
        # de "no tuvo turnos para hacerlo": con sleep=24 el agente dispone de
        # 60 decisiones en 30 días y necesita ~83 acciones solo para cubrir el
        # metabolismo. Lo que el modelo pidió igual se registra en el trace.
        self.force_sleep = force_sleep
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
        action, kwargs, raw = self._ask_model(
            observation, energy_per_tick=world.config.energy_per_tick)

        # D-018: el agente elige su propio horizonte de despertar (en ticks)
        horizonte_modelo = self._parse_horizonte(raw)
        horizonte = horizonte_modelo if self.force_sleep is None else self.force_sleep

        trace = {
            "observation": observation,
            "reason": reason,
            "goal": self.goal,
            "proposed_action": {"action": action, "args": kwargs},
            "sleep_ticks": horizonte,
            "model": self.model_name,
            "raw_response": raw,
        }
        if self.force_sleep is not None:
            # el horizonte NO lo eligió el agente: la corrida queda marcada y
            # se conserva lo que habría pedido, para poder analizarlo después.
            trace["sleep_forced"] = self.force_sleep
            trace["sleep_ticks_modelo"] = horizonte_modelo
        return action, kwargs, trace, horizonte

    @staticmethod
    def _parse_horizonte(raw) -> Optional[int]:
        """sleep_ticks válido: entero 1..24; inválido => 1 (despertar pronto).

        Tope 24 (fix de Opus): una fase dura 24 ticks; un horizonte de 96
        permitía dormir 4 días seguidos sin observar nunca una de las dos
        fases — y la fase es una de las dos dimensiones que debe aprender
        para componer. Un tope de 24 garantiza que ninguna fase quede
        invisible (requisito del experimento, no muleta de supervivencia)."""
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                return 1
        if not isinstance(raw, dict):
            return 1
        try:
            h = int(raw.get("sleep_ticks", 1))
            return max(1, min(24, h))
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
            # D-026: botones ejecutables AHORA con args ya rellenados. No dice
            # qué hacen — solo que existen. Elimina el ruido de saber escribir
            # la API del motor (91-96% de rechazos en el piloto).
            "acciones_disponibles": world.available_actions(self.eid),
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

    @staticmethod
    def context_line(observation: Dict[str, Any]) -> str:
        """Reafirma en prosa la región y la fase que YA están en la observación.

        No agrega información: son los campos `region` y `phase` del mismo
        JSON, repetidos en texto. Es legibilidad, de la misma clase que el
        barajado del menú (D-029) y la tabla plana (D-030), y va idéntico en
        las 4 condiciones.

        Por qué hace falta: `gemma2:9b` recupera la tabla perfecto cuando la
        región viene en el TEXTO de la pregunta (bench 16/16) y aplica un
        desfase consistente de +2 filas cuando la región viene solo en el
        JSON — contesta la etiqueta de una celda con el valor de otra
        ("región A ... fase 0 (clara): +7", línea que no existe). El bucle de
        acción es el caso "región solo en el JSON", así que sin esta línea el
        agente come veneno creyendo que gana +7.
        """
        region = observation.get("region", "")
        phase = int(observation.get("phase", 0))
        nombre = "clara" if phase == 0 else "oscura"
        return f"Estás en la región {region}, en la fase {phase} ({nombre})."

    def _ask_model(self, observation: Dict[str, Any],
                   energy_per_tick: float = 0.5) -> Tuple[str, Dict[str, Any], str]:
        system = self._system_prompt()
        # El costo se LEE de la config del mundo, no se escribe a mano: el
        # texto anterior afirmaba 0.5 mientras el piloto corría a 0.3 (mismo
        # defecto que D-020 — un número inventado en el prompt).
        met = round(float(energy_per_tick), 3)
        user = (
            "Estado actual:\n" + json.dumps(observation, ensure_ascii=False) +
            "\n" + self.context_line(observation) +
            "\n\nResponde SOLO con JSON: {\"action\": \"...\", \"args\": {...}, \"sleep_ticks\": N}\n"
            "donde sleep_ticks (1..24) = en cuántos ticks quieres volver a decidir. "
            f"El metabolismo te consume {met} de energía por tick, duermas o no: "
            f"dormir N ticks te cuesta N×{met} de energía y pierdes lo que pase mientras tanto."
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
        # El probe DEBE llevar lo que la condición le da al agente. Antes
        # construía un prompt desnudo: sin system_rules y sin memoria, las tres
        # condiciones recibían mensajes BYTE-IDÉNTICOS (118 y 221 caracteres) y
        # el probe no podía distinguirlas — medía a un modelo adivinando, no la
        # manipulación experimental. Es el bloque que define cada condición:
        #   oraculo     -> su tabla (system_rules)
        #   memoria     -> su registro literal de eventos vividos
        #   sin_memoria -> nada, que es justamente su condición
        # No se agrega mecánica ni geometría: la pregunta ya nombra el símbolo,
        # la región y la fase, así que el resto sería ruido.
        system = "Eres un agente autónomo en un mundo 2D. "
        if self.system_rules:
            system += ("\nConocimiento especial del mundo:\n"
                       + self.system_rules + "\n")
        system += ('Responde SOLO con JSON: '
                   '{"energy_change": <número con signo>, "reason": "..."}')

        partes = []
        if self.memory is not None:
            partes.append(
                "Tu registro literal de lo que te pasó (acción, región, fase, "
                "resultado):\n"
                + json.dumps(self.memory.render(), ensure_ascii=False))
        partes.append(
            f"PREGUNTA HIPOTÉTICA (no es una acción, solo responde):\n"
            f"Si consumieras 1 unidad del recurso '{rkind}' estando en la región "
            f"{region} durante la fase {'oscura' if phase == 1 else 'clara'}, "
            f"¿cuánto cambiaría tu energía? Da el número con signo (+ sube, - baja, 0 nada).")
        user = "\n\n".join(partes)
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
        # D-026: el contrato agente-motor (acciones disponibles + mecánica) va
        # SIEMPRE, incluso con system_rules (oráculo). Antes el oráculo perdía
        # la regla "dx,dy son pasos de 1 casilla" al reemplazar TODO el prompt
        # base — por eso proponía move con distancias imposibles (μ=4.45,
        # 88% >1) y "solo caminaba". No prestar world model: esto no revela
        # efectos, solo los botones y la mecánica — igual para las 4
        # condiciones.
        mechanics = (
            "Mecánica del mundo (contrato agente-motor):\n"
            "- En tu observación, 'acciones_disponibles' lista SOLO las acciones "
            "ejecutables en este instante, con sus argumentos ya rellenados. "
            "Elige una de ESA lista y respeta sus args. Si una acción no está, "
            "no es posible ahora.\n"
            "- move da pasos de UNA casilla (dx,dy ∈ {-1,0,1}); mueve de a 1, "
            "nunca saltes casillas.\n"
            "- gather solo funciona si el recurso está a 1 casilla de distancia (adyacente). "
            "Si el recurso está más lejos, primero usa move para acercarte.\n"
            "- consume convierte inventario en energía; come cuando tengas hambre.\n"
            "- drop/pickup/give funcionan solo en tu celda o casilla adyacente.\n"
            "- build construye en una casilla adyacente libre, consumiendo los materiales de su receta.\n"
            "- Solo percibes lo que está cerca (radio de visión limitado); lo que no ves, no sabes que existe.\n"
            + self.geometry +
            "- La comunicación es SIMBÓLICA: talk emite símbolos del alfabeto (k1..k4), sin significado. "
            "Costan energía; hablar solo cuando aporte.\n"
        )
        extra = ""
        if self.system_rules:
            extra = (
                "Conocimiento especial del mundo (además de la mecánica de arriba):\n"
                + self.system_rules + "\n"
            )
        base = (
            "Eres un agente autónomo en un mundo 2D.\n"
            + mechanics
            + extra
            + "Acciones disponibles (JSON): move{dx,dy}, gather{target_eid,amount}, "
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
