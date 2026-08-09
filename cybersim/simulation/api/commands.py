"""API simulator apply_command (docs/06 §4.5)."""

from __future__ import annotations

from typing import Any

from cybersim.simulation.base import RawEvent, ResponseCommand
from cybersim.simulation.core.context import SimContext


def apply_command(cmd: ResponseCommand, ctx: SimContext, state: dict[str, Any]) -> list[RawEvent]:
    action = cmd.action_id
    t = ctx.clock.now_ms()
    summary = ""
    if action == "block_source_ip":
        ip = cmd.params.get("ip", "203.0.113.42")
        state.setdefault("blocked_ips", set()).add(str(ip))
        summary = f"blocked source IP {ip}"
    elif action == "rate_limit_route":
        route = cmd.params.get("route", "/api/orders/{id}")
        state.setdefault("rate_limited_routes", set()).add(str(route))
        summary = f"rate limit set on {route}"
    elif action == "fix_idor_authz":
        state["idor_authz_fixed"] = True
        summary = "object-level authorization enforced"
    elif action == "restrict_returned_fields":
        state["fields_restricted"] = True
        summary = "API responses restricted to minimal field sets"
    elif action == "revoke_token":
        state["tokens_revoked"] = True
        summary = "attacker token revoked"
    else:
        return []
    return [
        RawEvent(
            id=ctx.rng.uuid_v7(t),
            sim_time_ms=t,
            origin="exec",
            type="response.applied",
            payload={
                "action_id": action,
                "applied": True,
                "effect_summary": summary,
                "mutating_edge_ids": (),
            },
        )
    ]


__all__ = ["apply_command"]
