"""Supply Chain simulator apply_command (docs/06 §6.6)."""

from __future__ import annotations

from typing import Any

from cybersim.simulation.base import RawEvent, ResponseCommand
from cybersim.simulation.core.context import SimContext


def apply_command(cmd: ResponseCommand, ctx: SimContext, state: dict[str, Any]) -> list[RawEvent]:
    action = cmd.action_id
    t = ctx.clock.now_ms()
    summary = ""
    if action == "pin_dependency_version":
        state["dep_pinned"] = True
        summary = "lib-jwt pinned to a known-safe version"
    elif action == "remove_malicious_package":
        state["package_removed"] = True
        summary = "malicious package removed from dependency tree"
    elif action == "block_registry_source":
        state["registry_blocked"] = True
        summary = "registry source blocked (FETCHES_FROM removed)"
    elif action == "block_post_install_hook":
        state["hooks_blocked"] = True
        summary = "post-install lifecycle hooks disabled"
    elif action == "force_reproducible_build":
        state["reproducible"] = True
        summary = "reproducible build enforced (locked material)"
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
