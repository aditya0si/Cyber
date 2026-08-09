"""`GraphRepository` Protocol — the swap-out seam (docs/10 §2).

Implementations maintain per-simulation graphs in-memory + persist deltas to
Postgres via `GraphDAL`. The only legitimate entrypoint for reading the
attack graph — no business code imports `networkx` directly (docs/04 §2.8).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol, runtime_checkable

from cybersim.graph.types import (
    AttackPath,
    EdgeType,
    EnvironmentGraph,
    FootholdState,
    GraphEdge,
    GraphNode,
    NodeKind,
    OverlayNode,
)


@runtime_checkable
class GraphRepository(Protocol):
    """Abstract attack-graph operations (docs/10 §2)."""

    # ---- lifecycle -------------------------------------------------------
    def create(self, simulation_id: str, env_graph: EnvironmentGraph) -> None: ...
    def load(self, simulation_id: str) -> EnvironmentGraph: ...
    def drop(self, simulation_id: str) -> None: ...

    # ---- env mutations ---------------------------------------------------
    def upsert_node(self, simulation_id: str, node: GraphNode) -> None: ...
    def upsert_edge(self, simulation_id: str, edge: GraphEdge) -> None: ...
    def deactivate_edge(self, simulation_id: str, edge_id: str) -> None: ...
    def update_foothold(
        self,
        simulation_id: str,
        node_id: str,
        state: FootholdState,
        flags: dict[str, Any] | None = None,
    ) -> None: ...

    # ---- overlay (attacker-side) ---------------------------------------
    def append_overlay(self, simulation_id: str, overlay: OverlayNode) -> None: ...
    def add_overlay_edge(
        self,
        simulation_id: str,
        *,
        kind: str,
        from_id: str,
        to_id: str,
        via_env_edge_id: str | None = None,
        evidence_event_id: str | None = None,
    ) -> None: ...

    # ---- queries ---------------------------------------------------------
    def get_node(self, simulation_id: str, node_id: str) -> GraphNode | None: ...
    def get_edges(
        self, simulation_id: str, node_id: str, active_only: bool = True
    ) -> list[GraphEdge]: ...
    def neighbors(
        self,
        simulation_id: str,
        node_id: str,
        types: list[EdgeType] | None = None,
    ) -> list[str]: ...
    def can_reach(self, simulation_id: str, src: str, dst: str, *, hops: int = 4) -> bool: ...
    def attack_paths(
        self,
        simulation_id: str,
        *,
        src: str | None = None,
        dst_kinds: Iterable[NodeKind] = (NodeKind.DATA,),
        max_paths: int = 5,
        hops: int = 4,
    ) -> list[AttackPath]: ...
    def graph_view(self, simulation_id: str) -> EnvironmentGraph: ...
    def snapshot(self, simulation_id: str, at_seq: int) -> bytes: ...
    def delta(self, simulation_id: str, from_seq: int, to_seq: int) -> dict[str, Any]: ...


__all__ = ["GraphRepository"]
