"""Analyst tool surface (docs/11 §4).

The LLM sees ONLY these tools; they're bound to tenant-scoped repositories.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from cybersim.graph.repo_nx import NetworkXGraphRepository
from cybersim.graph.types import EdgeType, FootholdState, NodeKind


class AnalystTools:
    """Graph + state tools bound to one simulation (docs/11 §4)."""

    def __init__(self, repo: NetworkXGraphRepository, simulation_id: str) -> None:
        self._repo = repo
        self._sim_id = simulation_id

    def get_attack_paths(
        self,
        node_kinds: Sequence[str] = ("DATA",),
        hops: int = 4,
        max_paths: int = 5,
        src: str | None = None,
    ) -> list[dict[str, Any]]:
        kinds = {NodeKind[k] for k in node_kinds if k in NodeKind.__members__}
        try:
            paths = self._repo.attack_paths(
                self._sim_id,
                src=src,
                dst_kinds=kinds,
                max_paths=max_paths,
                hops=hops,
            )
        except KeyError:
            return []
        return [
            {
                "nodes": p.nodes,
                "closes_at": p.closes_at_node_kind.value,
                "length": p.length,
            }
            for p in paths
        ]

    def get_neighbors(self, node_id: str, types: Sequence[str] | None = None) -> list[str]:
        edge_types = [EdgeType[t] for t in types if t in EdgeType.__members__] if types else None
        try:
            return self._repo.neighbors(self._sim_id, node_id, types=edge_types)
        except KeyError:
            return []

    def get_foothold_state(self, node_id: str) -> str | None:
        try:
            node = self._repo.get_node(self._sim_id, node_id)
        except KeyError:
            return None
        if node is None:
            return None
        return node.foothold_state.value if node.foothold_state else None

    def update_foothold(self, node_id: str, state: str) -> bool:
        if state not in FootholdState.__members__:
            return False
        try:
            self._repo.update_foothold(self._sim_id, node_id, FootholdState[state])
            return True
        except KeyError:
            return False
