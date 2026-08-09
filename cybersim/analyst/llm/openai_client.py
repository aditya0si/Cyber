"""OpenAI-backed LLM client (docs/04 §2.4, docs/11 §7).

Uses the OpenAI Chat Completions surface with `response_format` JSON mode;
we parse defensively: `complete_json` returns the parsed dict or `{}` on any
failure (callers fall back to rule-based analysis).
"""

from __future__ import annotations

import json
import re
from typing import Any

from openai import OpenAI


class OpenAIClient:
    """Structured-output client over the OpenAI API."""

    def __init__(
        self, api_key: str, model: str = "gpt-4o-mini", base_url: str | None = None
    ) -> None:
        self._client = OpenAI(api_key=api_key, base_url=base_url) if api_key else None
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
        if self._client is None:
            return {}
        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
            content = resp.choices[0].message.content or ""
            return _parse_json_fenced(content)
        except Exception:
            return {}


def _parse_json_fenced(content: str) -> dict[str, Any]:
    """Parse an LLM's JSON, tolerating fenced ```json blocks and leading noise."""
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
