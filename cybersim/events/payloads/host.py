"""Host payloads (docs/06 §5)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class _BasePayload(BaseModel):
    model_config = ConfigDict(extra="allow")


class HostLoginAttemptPayload(_BasePayload):
    host: str
    account: str
    success: bool
    method: str = "ssh"


class HostSessionPayload(_BasePayload):
    host: str
    role: str | None = None
    creds: str | None = None
    access_scope: tuple[str, ...] = ()


class HostProcessSpawnPayload(_BasePayload):
    host: str
    caller: str
    cmdline: str
    target: str | None = None


class NetLateralHopPayload(_BasePayload):
    from_host: str
    to_host: str
    method: str = "ssh_reuse"
