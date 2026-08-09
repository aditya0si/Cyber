"""Package (supply-chain) payloads (docs/06 §6)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class _BasePayload(BaseModel):
    model_config = ConfigDict(extra="allow")


class BuildDependencyResolvePayload(_BasePayload):
    name: str
    version: str
    resolved_tree: tuple[str, ...] = ()


class PackageInstalledPayload(_BasePayload):
    name: str
    version: str
    integrity_hash: str
    registry: str = "default"


class PackageLifecycleHookPayload(_BasePayload):
    hook: str
    cmdline: str
    package: str | None = None
