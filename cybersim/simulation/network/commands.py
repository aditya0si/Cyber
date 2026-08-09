"""Network simulator apply_command (docs/06 §5.5)."""

from __future__ import annotations

from typing import Any

from cybersim.simulation.base import RawEvent, ResponseCommand
from cybersim.simulation.core.context import SimContext


def apply_command(cmd: ResponseCommand, ctx: SimContext, state: dict[str, Any]) -> list[RawEvent]:
    action = cmd.action_id
    t = ctx.clock.now_ms()
    summary = ""
    if action == "isolate_host":
        host = cmd.params.get("host", "10.0.0.15")
        state.setdefault("isolated_hosts", set()).add(str(host))
        summary = f"host {host} isolated"
    elif action == "block_egress":
        state["egress_blocked"] = True
        summary = "egress to internet blocked"
    elif action == "rotate_credentials_host":
        host = cmd.params.get("host", "10.0.0.15")
        state.setdefault("rotated_hosts", set()).add(str(host))
        summary = f"credentials rotated on {host}"
    elif action == "sinkhole_scan_domain":
        state["sinkhole"] = True
        summary = "scan source domain sinkholed"
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
