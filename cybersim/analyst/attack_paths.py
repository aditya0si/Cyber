"""Helper for the rule-based analyst: graph-path → attack_path anchors (docs/10 §3.5)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from cybersim.events.schema import CanonicalEvent
from cybersim.graph.types import AttackPath, EnvironmentGraph, FootholdState, NodeKind


def attack_path_to_data(
    env: EnvironmentGraph,
    *,
    src_node_id: str | None,
    rendered_paths: Sequence[AttackPath] | None = None,
) -> list[dict[str, Any]]:
    """Project graph `AttackPath`s onto UI-facing AttackPathNode dicts.

    Priorities paths that `closes_at_node_kind == NodeKind.DATA`. Returns
    `[]` if `src_node_id` is missing or no path closes at DATA — caller is
    expected to clamp severity downward in that case (docs/05 §6.1).
    """
    if rendered_paths is None or src_node_id is None:
        return []
    closing = [p for p in rendered_paths if p.closes_at_node_kind == NodeKind.DATA]
    if not closing:
        return []
    closing.sort(key=lambda p: p.length)
    chosen = closing[0]
    out: list[dict[str, Any]] = []
    for nid in chosen.nodes:
        node = env.get_node(nid)
        label = node.label if node else nid
        kind = node.kind if node else NodeKind.ASSET
        fh = node.foothold_state if node else FootholdState.CLEAN
        out.append(
            {
                "node_id": nid,
                "label": label,
                "kind": kind,
                "foothold_state": fh.value,
            }
        )
    return out


def primary_events_for_query(events: list[CanonicalEvent], max_count: int = 5) -> list[str]:
    """Pick the first handful of `event_id`s from non-benign events for an
    evidence citation. Maintains the ID signature used in defaults.
    """
    ids: list[str] = []
    for ev in events:
        if ev.raw_context.get("benign", False):
            continue
        if ev.event_id not in ids:
            ids.append(ev.event_id)
        if len(ids) >= max_count:
            break
    return ids


__all__ = ["attack_path_to_data", "primary_events_for_query"]
