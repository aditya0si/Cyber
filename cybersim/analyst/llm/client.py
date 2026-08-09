"""LLM client seam (docs/04 §2.4, docs/11 §7, docs/21 Task 6.1).

The analyst never talks to a provider SDK directly — it calls `LLMClient`
which returns STRICT JSON dicts; our Pydantic models own validation.
"""

from __future__ import annotations

from typing import Any, Protocol


class LLMClient(Protocol):
    """Structured-output chat completion."""

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.0,
        max_tokens: int = 2048,
    ) -> dict[str, Any]:
        """Return a JSON object; the implementation MUST never raise on
        malformed provider output — it returns `{}` and callers detect."""
        ...

    @property
    def model_name(self) -> str: ...


__all__ = ["LLMClient"]
