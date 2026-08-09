"""Web simulator `apply_command` (docs/06 §3.6 — Phase 2 returns response events only).

Env-graph mutation is the responsibility of Phase 3's `GraphRepository`.
Phase 2 keeps the simulator self-consistent: the command returns response
events and updates an internal blocked-IPs / patched endpoint set so
post-command beats reflect the change.
"""

from __future__ import annotations

from typing import Any

from cybersim.simulation.base import RawEvent, ResponseCommand
from cybersim.simulation.core.context import SimContext


def apply_command(cmd: ResponseCommand, ctx: SimContext, state: dict[str, Any]) -> list[RawEvent]:
    """Apply a response action; mutate `state` & emit `response.applied` events.

    `state` is a per-simulation scratch dict managed by `WebSimulator`.
    Returns at least one `RawEvent` of raw_type=`response.applied` so that
    downstream consumers see the action took effect.
    """
    action = cmd.action_id
    t = ctx.clock.now_ms()
    summary = ""
    if action == "block_source_ip":
        ip = cmd.params.get("ip", "203.0.113.42")
        state.setdefault("blocked_ips", set()).add(str(ip))
        summary = f"blocked source IP {ip}"
    elif action == "rate_limit_endpoint":
        endpoint = cmd.params.get("endpoint", "/api/login")
        state.setdefault("rate_limited", set()).add(str(endpoint))
        summary = f"rate limit set on {endpoint}"
    elif action == "disable_endpoint":
        endpoint = cmd.params.get("endpoint", "/api/login")
        state.setdefault("disabled", set()).add(str(endpoint))
        summary = f"endpoint {endpoint} disabled"
    elif action == "patch_sqli":
        state["sqli_patched"] = True
        summary = "SQLi vulnerability patched (parameterized queries)"
    elif action == "rotate_credentials":
        state["credentials_rotated"] = True
        summary = "credentials rotated (admin_creds invalidated)"
    elif action == "quarantine_host":
        host = cmd.params.get("host", "web1")
        state.setdefault("quarantined", set()).add(str(host))
        summary = f"host {host} quarantined"
    else:
        return []

    applied = RawEvent(
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
    return [applied]


__all__ = ["apply_command"]
