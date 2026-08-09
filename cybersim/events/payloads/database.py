"""Database payloads (docs/06 §3.3)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class _BasePayload(BaseModel):
    model_config = ConfigDict(extra="allow")


class DBQueryPayload(_BasePayload):
    db: str | None = None
    statement: str = ""
    rows_returned: int | None = None
    error: str | None = None
    parameterized: bool = True


class DBErrorPayload(_BasePayload):
    db: str | None = None
    code: str | None = None
    message: str
    query_ref: str | None = None
