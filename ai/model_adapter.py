"""WorldLab — Model Adapter (fase 2).

Capa única para llamar modelos de lenguaje. La arquitectura es agnóstica
(concepto v0.1 §27): el agente no sabe si habla con Ollama local o con una API.

Backends:
  - "ollama":   http://localhost:11434/v1 (modelos locales, sin API key)
  - "openai":   OpenAI-compatible (DeepSeek, etc.) — base_url + api_key por env

Siempre pide JSON como respuesta y lo parsea de forma tolerante (el LLM
suele envolver el JSON en texto o markdown).
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, List, Optional

import urllib.request
import urllib.error


class ModelError(Exception):
    pass


class LLMClient:
    """Cliente LLM mínimo (sin dependencias externas)."""

    def __init__(self, backend: str = "ollama", model: Optional[str] = None,
                 base_url: Optional[str] = None, api_key: Optional[str] = None,
                 temperature: float = 0.7, timeout: float = 60.0,
                 max_retries: int = 2, max_tokens: Optional[int] = None):
        self.backend = backend
        self.temperature = temperature
        self.timeout = timeout
        self.max_retries = max_retries
        self.max_tokens = max_tokens
        self.last_usage: Dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0}

        if backend == "ollama":
            self.model = model or os.environ.get("WORLDLAB_OLLAMA_MODEL", "qwen3:8b")
            self.base_url = base_url or "http://localhost:11434/v1"
            self.api_key = api_key or "ollama"
        elif backend == "openai":
            self.model = model or os.environ.get("WORLDLAB_LLM_MODEL", "deepseek-chat")
            self.base_url = base_url or os.environ.get("WORLDLAB_LLM_BASE_URL",
                                                       "https://api.deepseek.com/v1")
            self.api_key = api_key or os.environ.get("WORLDLAB_LLM_API_KEY", "")
            if not self.api_key:
                raise ModelError("WORLDLAB_LLM_API_KEY no configurada para backend openai")
        else:
            raise ModelError(f"backend desconocido: {backend}")

    # ------------------------------------------------------------------
    def chat_json(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """Chat simple; espera JSON en la respuesta. Devuelve el JSON parseado."""
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "stream": False,
        }
        if self.max_tokens:
            payload["max_tokens"] = self.max_tokens
        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key}"},
            method="POST",
        )
        last_err = None
        for attempt in range(self.max_retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = json.loads(resp.read().decode())
                content = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
                self.last_usage = {
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                }
                return self._extract_json(content)
            except urllib.error.HTTPError as e:
                last_err = f"HTTP {e.code}: {e.read()[:200]!r}"
            except (urllib.error.URLError, KeyError, json.JSONDecodeError) as e:
                last_err = f"{type(e).__name__}: {e}"
            if attempt < self.max_retries:
                time.sleep(1.0 * (attempt + 1))
        raise ModelError(f"fallo tras {self.max_retries + 1} intentos: {last_err}")

    @staticmethod
    def _plus_signed_numbers(text: str) -> str:
        """Repara `+N` en posición de VALOR: JSON no admite el signo + delante
        de un número, pero nosotros se lo pedimos explícitamente al modelo
        ("da el número con signo", predict_effect / probes). Un modelo que
        OBEDECE la instrucción produce `{"energy_change": +1}` — JSON inválido
        — y su respuesta, posiblemente correcta, se registraba como
        `predicted_energy_change: null`, indistinguible de "no contestó".

        Solo se toca el `+` que sigue inmediatamente a `:`, `[` o `,` (posición
        de valor). Un `+` dentro de una cadena ("sube +1 de energía") no
        califica: el carácter previo es una letra o una comilla, no un
        delimitador.
        """
        return re.sub(r"([:\[,])(\s*)\+(?=\d)", r"\1\2", text)

    @staticmethod
    def _extract_json(content: str) -> Dict[str, Any]:
        """Extrae el primer objeto JSON del texto (tolera markdown/ruido)."""
        content = content.strip()
        # quitar fences de markdown
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
        # el signo + explícito solo se repara si el parseo limpio falla
        for candidate in (content, LLMClient._plus_signed_numbers(content)):
            try:
                obj = json.loads(candidate)
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                continue
        content = LLMClient._plus_signed_numbers(content)
        # buscar el primer {...} balanceado
        start = content.find("{")
        if start == -1:
            raise ModelError(f"no hay JSON en la respuesta: {content[:120]!r}")
        depth = 0
        for i in range(start, len(content)):
            if content[i] == "{":
                depth += 1
            elif content[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(content[start:i + 1])
                        if isinstance(obj, dict):
                            return obj
                    except json.JSONDecodeError:
                        break
        raise ModelError(f"JSON inválido en la respuesta: {content[:120]!r}")

    def describe(self) -> str:
        return f"{self.backend}:{self.model}"
