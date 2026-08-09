"""HTTP payloads (docs/06 §3.3)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _BasePayload(BaseModel):
    model_config = ConfigDict(extra="allow")


class HTTPRequestPayload(_BasePayload):
    method: str
    path: str
    status: int | None = None
    src_ip: str | None = None
    query: dict[str, str] | None = None
    headers: dict[str, str] | None = None
    body: dict[str, Any] | list[Any] | str | None = None
    ms: int | None = None


class HTTPErrorPayload(_BasePayload):
    path: str
    status: int = Field(ge=400)
    detail: str | None = None
    sqli_pattern: str | None = None
