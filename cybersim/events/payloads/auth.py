"""Auth payloads (docs/06 §3.3)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class _BasePayload(BaseModel):
    model_config = ConfigDict(extra="allow")


class AuthAttemptPayload(_BasePayload):
    username: str
    success: bool
    user_agent: str | None = None
    mfa_used: bool = False


class AuthSuccessPayload(_BasePayload):
    account_id: str
    factor: str = "password"
    new_geo: str | None = None


class SessionCreatedPayload(_BasePayload):
    account_id: str
    session_id: str
    scope: tuple[str, ...] = ()
