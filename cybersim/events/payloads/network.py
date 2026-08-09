"""Network payloads (docs/06 §5)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _BasePayload(BaseModel):
    model_config = ConfigDict(extra="allow")


class NetConnectionPayload(_BasePayload):
    src: str
    dst: str
    port: int | None = None
    proto: str = "tcp"
    flags: str | None = None
    state: str | None = None


class NetScanProbePayload(_BasePayload):
    target_host: str
    ports: tuple[int, ...] = ()
    script: str = "syn_scan"


class NetServiceDiscoveredPayload(_BasePayload):
    host: str
    port: int = Field(ge=0, le=65535)
    service: str
    banner_fingerprint: str | None = None
