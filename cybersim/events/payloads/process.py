"""Process payloads (docs/06 §6)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class _BasePayload(BaseModel):
    model_config = ConfigDict(extra="allow")


class ProcessExecPayload(_BasePayload):
    caller_package: str | None = None
    cmdline: str
    cwd: str | None = None
    parent_pid: int | None = None


class ProcessEnvExfilPayload(_BasePayload):
    """Cybersim never emits real secret values; only *patterns/signals* (docs/06 §6.4)."""

    var_patterns_seen: tuple[str, ...] = ()
    path_touched: str | None = None
