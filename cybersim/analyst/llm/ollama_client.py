"""Ollama-backed LLM client using the OpenAI-compatible API endpoint.

Ollama exposes a /v1/chat/completions endpoint compatible with openai-python;
we just point the base_url at the local Ollama server and use the model name
as-is (e.g. "gemma3:4b", "llama3.2:3b", etc.).

JSON mode: Ollama supports `format="json"` on its native endpoint but the
OpenAI-compat endpoint honours `response_format={"type":"json_object"}` for
models that support it. We defensively strip markdown fences either way.
"""

from __future__ import annotations

import json
import re
from typing import Any

from openai import OpenAI


class OllamaClient:
    """Structured-output client using a local Ollama server."""

    def __init__(
        self,
        model: str = "gemma3:4b",
        base_url: str = "http://localhost:11434/v1",
        # Ollama doesn't require an API key but openai-python needs a non-empty string
        api_key: str = "ollama",
    ) -> None:
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    @property
    def model_name(self) -> str:
        return self._model

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.0,
        max_tokens: int = 2048,
    ) -> dict[str, Any]:
        """Return a JSON dict or {} on any failure."""
        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                # JSON mode — supported by newer Ollama versions; silently
                # ignored by older ones (we still strip fences defensively)
                response_format={"type": "json_object"},
            )
            content = resp.choices[0].message.content or ""
            return _parse_json_fenced(content)
        except Exception:
            return {}


def _parse_json_fenced(content: str) -> dict[str, Any]:
    cleaned = content.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
    if fenced:
        cleaned = fenced.group(1).strip()
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    return {}


__all__ = ["OllamaClient"]
