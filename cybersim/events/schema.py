from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
import datetime

class CanonicalEvent(BaseModel):
    """A single normalized security event matching the Round 1 Contract (docs/00 §5)."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str
    timestamp: str          # ISO 8601
    event_type: str         # e.g. "LOGIN_FAILED", "LOGIN_SUCCESS", "PRIVILEGE_ESCALATION", "DB_ACCESS"
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    source_ip: str
    target_asset: str       # e.g. "auth-api", "app-server", "database"
    actor: str              # user/account identifier involved
    raw_context: dict[str, Any] = Field(default_factory=dict)

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, v: str) -> str:
        try:
            datetime.datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("timestamp must be in ISO8601 format")
        return v

def assemble(*args: Any, **kwargs: Any) -> CanonicalEvent:
    raw_context = dict(kwargs)
    event_id = kwargs.get("event_id", "test-id")
    
    sim_time_ms = kwargs.get("sim_time_ms", 0)
    dt = datetime.datetime.fromtimestamp(sim_time_ms / 1000.0, tz=datetime.timezone.utc)
    timestamp = kwargs.get("timestamp", dt.isoformat())
    event_type = kwargs.get("event_type", kwargs.get("raw_type", "unknown"))
    
    sev = kwargs.get("severity_hint")
    if hasattr(sev, "value"):
        sev_str = sev.value.upper()
    elif isinstance(sev, str):
        sev_str = sev.upper()
    else:
        sev_str = "LOW"
        
    if sev_str == "INFO":
        sev_str = "LOW"
        
    severity = kwargs.get("severity", sev_str)
    source_ip = kwargs.get("source_ip", "unknown")
    target_asset = kwargs.get("target_asset", "unknown")
    actor = kwargs.get("actor", "unknown")
    
    return CanonicalEvent(
        event_id=event_id,
        timestamp=timestamp,
        event_type=event_type,
        severity=severity,  # type: ignore[arg-type]
        source_ip=source_ip,
        target_asset=target_asset,
        actor=actor,
        raw_context=raw_context,
    )
