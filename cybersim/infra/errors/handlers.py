"""RFC 9457 Problem Details exceptions + handler (docs/08 §3)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cybersim.infra.errors.codes import ErrorCode, error_status


@dataclass
class AppError(Exception):
    """A domain-level error carrying the stable `code` + RFC9457 body."""

    code: ErrorCode
    detail: str = ""
    title: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:  # pragma: no cover — trivial
        return f"[{self.code.value}] {self.detail}"


def problem_detail(
    code: ErrorCode,
    detail: str,
    *,
    instance: str = "",
    trace_id: str = "",
    violations: list[dict[str, str]] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Serialize an RFC 9457 problem body from a stable `code`."""
    body: dict[str, Any] = {
        "type": f"https://errors.cybersim.ai/v1/{code.value.replace('.', '/').lower()}",
        "title": _title_for(code),
        "status": error_status(code),
        "detail": detail,
        "code": code.value,
    }
    if instance:
        body["instance"] = instance
    if trace_id:
        body["trace_id"] = trace_id
    if violations:
        body["violations"] = violations
    if extra:
        body.update(extra)
    return body


def _title_for(code: ErrorCode) -> str:
    return {
        ErrorCode.VALIDATION: "Invalid request payload",
        ErrorCode.AUTH_MISSING: "Authentication required",
        ErrorCode.AUTH_INVALID: "Token invalid",
        ErrorCode.AUTH_EXPIRED: "Token expired",
        ErrorCode.AUTH_REFRESH_INVALID: "Refresh token invalid",
        ErrorCode.AUTH_REFRESH_REUSED: "Refresh token reuse detected",
        ErrorCode.AUTH_WS_TICKET_INVALID: "WebSocket ticket invalid",
        ErrorCode.FORBIDDEN: "Forbidden",
        ErrorCode.ORG_NOT_FOUND: "Organization not found",
        ErrorCode.USER_EXISTS: "User already exists",
        ErrorCode.USER_NOT_FOUND: "User not found",
        ErrorCode.LOGIN_FAILED: "Login failed",
        ErrorCode.SCENARIO_NOT_FOUND: "Scenario not found",
        ErrorCode.SIM_NOT_FOUND: "Simulation not found",
        ErrorCode.SIM_RUNNING: "Simulation already running",
        ErrorCode.SIM_CONCURRENCY_LIMIT: "Simulation concurrency limit reached",
        ErrorCode.SIM_STATUS_INVALID: "Simulation in invalid state for this action",
        ErrorCode.DETECTION_NOT_FOUND: "Detection not found",
        ErrorCode.ACTION_UNKNOWN: "Unknown response action",
        ErrorCode.ACTION_NOT_ALLOWED: "Action not allowed for this simulation",
        ErrorCode.ACTION_UNCONFIRMED: "Action requires explicit confirmation",
        ErrorCode.KNOWLEDGE_NOT_FOUND: "Knowledge entry not found",
        ErrorCode.MISSION_NOT_FOUND: "Mission not found",
        ErrorCode.BILLING_INVALID_STATE: "Billing state invalid",
        ErrorCode.IDEMPOTENCY_KEY_REQUIRED: "Idempotency key required",
        ErrorCode.RATE_LIMITED: "Rate limit exceeded",
        ErrorCode.NOT_IMPLEMENTED: "Not implemented",
    }[code]
