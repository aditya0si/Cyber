"""LLM model router (docs/11 §7)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cybersim.analyst.llm.client import LLMClient
from cybersim.analyst.llm.fake_client import FakeLLMClient
from cybersim.analyst.llm.openai_client import OpenAIClient


@dataclass(frozen=True)
class LLMRouter:
    """Routes to the right model per node, honoring token budgets.

    Phase 6: single-model MVP (triage model for all nodes). Phase 7 adds the
    mini/full split from docs/11 §7.
    """

    client: LLMClient

    def for_node(self, node: str) -> LLMClient:
        # MVP: same client for every node; per-node budgets land in Phase 7.
        return self.client


def build_router(
    *,
    provider: str = "openai",
    api_key: str = "",
    model: str = "gpt-4o-mini",
    script: list[dict[str, Any]] | None = None,
) -> LLMRouter:
    if provider == "fake" or not api_key:
        client: LLMClient = FakeLLMClient(script=script)
    elif provider == "openai":
        client = OpenAIClient(api_key=api_key, model=model)
    else:
        raise ValueError(f"unknown LLM provider {provider!r}")
    return LLMRouter(client=client)
