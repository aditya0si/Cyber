"""Analyst runtime state schema (docs/11 §2).

All keys are optional (`total=False`) — LangGraph merges partial updates
returned by each node; the runtime seeds the identity keys.
"""

from __future__ import annotations

from typing import Any, TypedDict

from cybersim.events.schema import CanonicalEvent


class AnalystState(TypedDict, total=False):
    """Per-window state carried through analyst nodes (docs/11 §2)."""

    # ---- identity (seeded by the runtime) ---------------------------------
    org_id: str
    simulation_id: str
    window_seq: int
    events: list[CanonicalEvent]
    simulator_id: str
    degraded: bool

    # ---- deterministic nodes ---------------------------------------------
    window_stats: dict[str, Any]
    candidate: list[CanonicalEvent]

    # ---- LLM nodes ---------------------------------------------------------
    triage: dict[str, Any]
    graph_paths: list[dict[str, Any]]
    attack_path_summary: list[dict[str, Any]]
    knowledge_hits: list[dict[str, Any]]
    evidence: list[Any]
    risk: dict[str, Any]
    recommended_actions: list[Any]

    # ---- validation / emit -------------------------------------------------
    validation: dict[str, Any]
    proposal: Any
    proposed_detection: dict[str, Any] | None
    telemetry: dict[str, Any]


__all__ = ["AnalystState"]
