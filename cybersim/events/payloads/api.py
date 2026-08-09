"""API payloads (docs/06 §4)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _BasePayload(BaseModel):
    model_config = ConfigDict(extra="allow")


class APIRequestPayload(_BasePayload):
    method: str
    route: str
    status: int | None = None
    user_id: str | None = None
    token_present: bool = False
    ms: int | None = None


class APIAuthzPayload(_BasePayload):
    route: str
    decision: str  # "allow" | "deny"
    reason: str | None = None


class APIRateWindowPayload(_BasePayload):
    route: str
    hits: int = Field(ge=0)
    denied: int = Field(default=0, ge=0)


class APIDataResponsePayload(_BasePayload):
    route: str
    fields_returned: list[str] = Field(default_factory=list)
    rows: int = Field(default=0, ge=0)
    scope_exceeded: bool = False
