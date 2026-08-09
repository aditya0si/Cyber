"""NetworkX-backed GraphRepository impl (docs/10 §3).

Stores env graph + overlay as in-process MultiDiGraph. Path queries combine
active env edges (allowed) and attacker-side overlays (used). Bounds:
- `hops <= 6`, `max_paths <= 10` (docs/10 §6).
- capacity via `LruCache` (default 256 sims).
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from itertools import islice, pairwise
from threading import RLock
from typing import Any

import networkx as nx

from cybersim.graph.cache import LruCache
from cybersim.graph.types import (
    AttackPath,
    EdgeTransition,
    EdgeType,
    EnvironmentGraph,
    FootholdState,
    GraphEdge,
    GraphNode,
    NodeKind,
    OverlayNode,
)

_HOPS_HARD_LIMIT = 6
_PATHS_HARD_LIMIT = 10


class _SimGraph:
    """In-process holder: env MultiDiGraph + overlay MultiDiGraph + seq counter."""

    __slots__ = ("env", "lock", "overlay", "seq")

    def __init__(self, env: EnvironmentGraph) -> None:
        self.env = nx.MultiDiGraph()
        self.overlay = nx.MultiDiGraph()
        self.seq = 0
        self.lock = RLock()
        for nid, node in env.nodes.items():
            self.env.add_node(nid, **_node_data(node))
        for _eid, edge in env.edges.items():
            self.env.add_edge(
                edge.from_node,
                edge.to_node,
                key=edge.edge_id,
                edge_id=edge.edge_id,
                type=edge.type,
                attrs=edge.attrs,
                active=edge.active,
            )


def _node_data(node: GraphNode) -> dict[str, Any]:
    return dict(
        kind=node.kind,
        type=node.type,
        label=node.label,
        attrs=node.attrs,
        foothold_state=node.foothold_state,
    )


def _env_edge_view(g: nx.MultiDiGraph, active_only: bool = True):  # type: ignore[no-untyped-def]
    """Yield (from, to, key, data) for env edges filtered by active flag."""
    for u, v, k, d in g.edges(keys=True, data=True):
        if active_only and not d.get("active", True):
            continue
        yield u, v, k, d


class NetworkXGraphRepository:
    """`GraphRepository` backed by NetworkX in-memory graphs (docs/10 §3.2)."""

    def __init__(self, cache_capacity: int = 256) -> None:
        self._cache: LruCache = LruCache(capacity=cache_capacity)

    # ---- lifecycle -------------------------------------------------------
    def create(self, simulation_id: str, env_graph: EnvironmentGraph) -> None:
        sg = _SimGraph(env_graph)
        self._cache.put(simulation_id, sg)

    def load(self, simulation_id: str) -> EnvironmentGraph:
        sg = self._cache.get_or_load(simulation_id, lambda: _SimGraph(EnvironmentGraph()))
        return self._to_env_view(sg)

    def drop(self, simulation_id: str) -> None:
        self._cache.drop(simulation_id)

    # ---- env mutations ---------------------------------------------------
    def upsert_node(self, simulation_id: str, node: GraphNode) -> None:
        sg = self._require(simulation_id)
        with sg.lock:
            sg.env.add_node(node.node_id, **_node_data(node))
            sg.seq += 1

    def upsert_edge(self, simulation_id: str, edge: GraphEdge) -> None:
        sg = self._require(simulation_id)
        with sg.lock:
            sg.env.add_edge(
                edge.from_node,
                edge.to_node,
                key=edge.edge_id,
                edge_id=edge.edge_id,
                type=edge.type,
                attrs=edge.attrs,
                active=edge.active,
            )
            sg.seq += 1

    def deactivate_edge(self, simulation_id: str, edge_id: str) -> None:
        sg = self._require(simulation_id)
        with sg.lock:
            for _u, _v, k, d in sg.env.edges(keys=True, data=True):
                if k == edge_id:
                    d["active"] = False
                    sg.seq += 1
                    return
            raise KeyError(f"no such edge: {edge_id!r}")

    def update_foothold(
        self,
        simulation_id: str,
        node_id: str,
        state: FootholdState,
        flags: dict[str, Any] | None = None,
    ) -> None:
        sg = self._require(simulation_id)
        with sg.lock:
            if node_id not in sg.env:
                raise KeyError(f"no such node: {node_id!r}")
            sg.env.nodes[node_id]["foothold_state"] = state
            if flags:
                attrs = dict(sg.env.nodes[node_id].get("attrs", {}))
                attrs.update(flags)
                sg.env.nodes[node_id]["attrs"] = attrs
            sg.seq += 1

    # ---- overlay ----------------------------------------------------------
    def append_overlay(self, simulation_id: str, overlay: OverlayNode) -> None:
        sg = self._require(simulation_id)
        with sg.lock:
            sg.overlay.add_node(
                overlay.node_id,
                parent=overlay.parent_node_id,
                state=overlay.state,
                flags=dict(overlay.flags),
            )
            sg.seq += 1

    def add_overlay_edge(
        self,
        simulation_id: str,
        *,
        kind: str,
        from_id: str,
        to_id: str,
        via_env_edge_id: str | None = None,
        evidence_event_id: str | None = None,
    ) -> None:
        sg = self._require(simulation_id)
        with sg.lock:
            sg.overlay.add_edge(
                from_id,
                to_id,
                key=f"{kind}:{via_env_edge_id or from_id}-{to_id}",
                kind=kind,
                via_env_edge_id=via_env_edge_id,
                evidence_event_id=evidence_event_id,
            )
            sg.seq += 1

    # ---- queries ----------------------------------------------------------
    def get_node(self, simulation_id: str, node_id: str) -> GraphNode | None:
        sg = self._require(simulation_id)
        with sg.lock:
            if node_id not in sg.env:
                return None
            d = sg.env.nodes[node_id]
            return GraphNode(
                node_id=node_id,
                kind=d["kind"],
                type=d.get("type"),
                label=d["label"],
                attrs=dict(d.get("attrs", {})),
                foothold_state=d.get("foothold_state", FootholdState.CLEAN),
            )

    def get_edges(
        self, simulation_id: str, node_id: str, active_only: bool = True
    ) -> list[GraphEdge]:
        sg = self._require(simulation_id)
        with sg.lock:
            out: list[GraphEdge] = []
            for u, v, k, d in sg.env.edges(node_id, keys=True, data=True):
                if active_only and not d.get("active", True):
                    continue
                out.append(
                    GraphEdge(
                        edge_id=k,
                        from_node=u,
                        to_node=v,
                        type=d["type"],
                        attrs=dict(d.get("attrs", {})),
                        active=d.get("active", True),
                    )
                )
            return out

    def neighbors(
        self,
        simulation_id: str,
        node_id: str,
        types: list[EdgeType] | None = None,
    ) -> list[str]:
        sg = self._require(simulation_id)
        with sg.lock:
            out: list[str] = []
            for _u, v, _k, d in sg.env.edges(node_id, keys=True, data=True):
                if not d.get("active", True):
                    continue
                if types is not None and d["type"] not in types:
                    continue
                out.append(v)
            return list(dict.fromkeys(out))  # dedupe but preserve order

    def can_reach(self, simulation_id: str, src: str, dst: str, *, hops: int = 4) -> bool:
        if hops > _HOPS_HARD_LIMIT:
            raise ValueError(f"hops must be <= {_HOPS_HARD_LIMIT}")
        sg = self._require(simulation_id)
        with sg.lock:
            try:
                length = nx.shortest_path_length(sg.env, src, dst)
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                return False
            return bool(length <= hops)

    def attack_paths(
        self,
        simulation_id: str,
        *,
        src: str | None = None,
        dst_kinds: Iterable[NodeKind] = (NodeKind.DATA,),
        max_paths: int = 5,
        hops: int = 4,
    ) -> list[AttackPath]:
        if hops > _HOPS_HARD_LIMIT:
            raise ValueError(f"hops must be <= {_HOPS_HARD_LIMIT}")
        if max_paths > _PATHS_HARD_LIMIT:
            raise ValueError(f"max_paths must be <= {_PATHS_HARD_LIMIT}")
        sg = self._require(simulation_id)
        dst_kind_set = set(dst_kinds)
        targets: list[str] = []
        with sg.lock:
            for nid, d in sg.env.nodes(data=True):
                if d["kind"] in dst_kind_set:
                    targets.append(nid)
            if not targets:
                return []
            if src is None:
                # Pick first overlay foothold node OR fall back to NETWORK_ZONE;
                # if neither, return [] since a path must originate somewhere.
                srcs: list[str] = []
                try:
                    srcs = list(sg.overlay.nodes(data=False))
                except Exception:
                    srcs = []
                if not srcs:
                    srcs = [
                        nid
                        for nid, d in sg.env.nodes(data=True)
                        if d.get("kind") == NodeKind.NETWORK_ZONE
                    ]
                if not srcs:
                    return []
            else:
                srcs = [src]
            paths: list[AttackPath] = []
            for s in srcs:
                if s not in sg.env:
                    continue
                for target in targets:
                    if target == s:
                        continue
                    try:
                        gen = nx.all_simple_paths(sg.env, s, target, cutoff=hops)
                    except (nx.NetworkXNoPath, nx.NodeNotFound):
                        continue
                    for path_nodes in islice(gen, max_paths):
                        # Compose edge transitions along the path
                        transitions: list[EdgeTransition] = []
                        for u, v in pairwise(path_nodes):
                            # take first matching edge (any type)
                            for _uu, _vv, _k, d in sg.env.edges(u, keys=True, data=True):
                                if _vv == v and d.get("active", True):
                                    transitions.append(
                                        EdgeTransition(
                                            edge_id=_k,
                                            from_node=u,
                                            to_node=v,
                                            type=d["type"],
                                            attrs=dict(d.get("attrs", {})),
                                        )
                                    )
                                    break
                        # What node kind does this path close at?
                        target_kind = sg.env.nodes[target]["kind"]
                        paths.append(
                            AttackPath(
                                nodes=path_nodes,
                                edges=transitions,
                                closes_at_node_kind=target_kind,
                                length=len(transitions),
                            )
                        )
                        if len(paths) >= max_paths:
                            return paths
            return paths

    # ---- snapshot/delta/view ---------------------------------------------
    def graph_view(self, simulation_id: str) -> EnvironmentGraph:
        sg = self._require(simulation_id)
        return self._to_env_view(sg)

    def snapshot(self, simulation_id: str, at_seq: int) -> bytes:
        sg = self._require(simulation_id)
        with sg.lock:
            payload = {
                "simulation_id": simulation_id,
                "at_seq": at_seq,
                "nodes": [_node_view(nid, sg.env.nodes[nid]) for nid in sg.env.nodes()],
                "edges": [
                    _edge_view(u, v, k, d) for u, v, k, d in sg.env.edges(keys=True, data=True)
                ],
                "overlay": [
                    {
                        "node_id": nid,
                        "parent": d.get("parent"),
                        "state": d.get("state"),
                        "flags": d.get("flags", {}),
                    }
                    for nid, d in sg.overlay.nodes(data=True)
                ],
            }
        return json.dumps(payload).encode("utf-8")

    def delta(self, simulation_id: str, from_seq: int, to_seq: int) -> dict[str, Any]:
        # Phase 3 stub: full snapshot delta. Real per-seq tracking lives in Phase 9.
        snap = self.snapshot(simulation_id, to_seq)
        return {
            "from_seq": from_seq,
            "to_seq": to_seq,
            "full_snapshot": json.loads(snap),
        }

    # ---- internals --------------------------------------------------------
    def _require(self, simulation_id: str) -> _SimGraph:
        sg = self._cache.get(simulation_id)
        if sg is None:
            raise KeyError(f"no graph for simulation_id={simulation_id!r}; create() first")
        return sg  # type: ignore[no-any-return]

    def _to_env_view(self, sg: _SimGraph) -> EnvironmentGraph:
        g = EnvironmentGraph()
        with sg.lock:
            for nid, d in sg.env.nodes(data=True):
                g.add_node(
                    GraphNode(
                        node_id=nid,
                        kind=d["kind"],
                        type=d.get("type"),
                        label=d.get("label", nid),
                        attrs=dict(d.get("attrs", {})),
                        foothold_state=d.get("foothold_state", FootholdState.CLEAN),
                    )
                )
            for _u, _v, k, d in sg.env.edges(keys=True, data=True):
                g.add_edge(
                    GraphEdge(
                        edge_id=k,
                        from_node=_u,
                        to_node=_v,
                        type=d["type"],
                        attrs=dict(d.get("attrs", {})),
                        active=d.get("active", True),
                    )
                )
        return g


def _node_view(nid: str, d: dict[str, Any]) -> dict[str, Any]:
    kind = d.get("kind")
    type_v = d.get("type")
    fh = d.get("foothold_state")
    return {
        "id": nid,
        "kind": getattr(kind, "value", kind),
        "type": getattr(type_v, "value", type_v),
        "label": d.get("label", nid),
        "attrs": d.get("attrs", {}),
        "foothold_state": getattr(fh, "value", fh) if fh is not None else "clean",
    }


def _edge_view(u: str, v: str, k: str, d: dict[str, Any]) -> dict[str, Any]:
    type_v = d.get("type")
    return {
        "id": k,
        "from": u,
        "to": v,
        "type": getattr(type_v, "value", type_v),
        "attrs": d.get("attrs", {}),
        "active": d.get("active", True),
    }


__all__ = ["NetworkXGraphRepository"]
