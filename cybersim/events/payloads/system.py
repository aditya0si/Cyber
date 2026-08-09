"""System payloads (executor/source) — response.applied etc. (docs/06 §3.6)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ResponseAppliedPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    action_id: str
    applied: bool = True
    effect_summary: str | None = None
    mutating_edge_ids: tuple[str, ...] = ()
