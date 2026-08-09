"""API simulator (docs/06 §4, docs/21 Task 7.1)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from cybersim.graph.types import (
    AssetType,
    EdgeType,
    EnvironmentGraph,
    GraphEdge,
    GraphNode,
    NodeKind,
)
from cybersim.simulation.api import beats as api_beats
from cybersim.simulation.api.commands import apply_command as _apply_command
from cybersim.simulation.base import RawEvent, ResponseCommand, SimBeat
from cybersim.simulation.catalog import env_template_for_scenario
from cybersim.simulation.core.context import SimContext

_EDGE_KIND = {
    "EXPOSES": EdgeType.EXPOSES,
    "READS": EdgeType.READS,
    "WRITES": EdgeType.WRITES,
    "CONNECTS_TO": EdgeType.CONNECTS_TO,
    "AUTHENTICATES_WITH": EdgeType.AUTHENTICATES_WITH,
    "STORES": EdgeType.STORES,
    "RUNS": EdgeType.RUNS,
}


class APISimulator:
    """The MVP API simulator (docs/06 §4)."""

    id = "api"

    def __init__(self) -> None:
        self._env: EnvironmentGraph | None = None
        self._state: dict[str, Any] = {}

    @property
    def environment(self) -> EnvironmentGraph:
        if self._env is None:
            raise RuntimeError("init() not called before reading environment")
        return self._env

    def init(self, ctx: SimContext) -> None:
        self._env = _build_env(ctx.scenario_id)
        self._state = {}

    def beats(self, ctx: SimContext) -> Iterator[SimBeat]:
        for beat in api_beats.phases(ctx):
            yield self._post_process(beat, ctx)

    def _post_process(self, beat: SimBeat, ctx: SimContext) -> SimBeat:
        if not self._state:
            return beat
        out: list[RawEvent] = []
        for ev in beat.events:
            if ev.benign:
                out.append(ev)
                continue
            if self._state.get("blocked_ips") and ev.src_ip in self._state["blocked_ips"]:
                ev = ev.model_copy(update={"payload": {**ev.payload, "status": 403}})
            elif self._state.get("idor_authz_fixed") and ev.type == "api.request":
                route_params = ev.payload.get("route_params")
                if isinstance(route_params, dict):
                    ev = ev.model_copy(
                        update={
                            "payload": {
                                **ev.payload,
                                "status": 403,
                                "authz_denied": True,
                            }
                        }
                    )
            elif self._state.get("fields_restricted") and ev.type == "api.data_response":
                ev = ev.model_copy(
                    update={
                        "payload": {
                            **ev.payload,
                            "fields_returned": ["id"],
                        }
                    }
                )
            out.append(ev)
        return SimBeat(sim_time_ms=beat.sim_time_ms, events=out)

    def apply_command(self, cmd: ResponseCommand, ctx: SimContext) -> list[RawEvent]:
        if self._env is None:
            raise RuntimeError("init() must be called before apply_command()")
        return _apply_command(cmd, ctx, self._state)


def _build_env(scenario_id: str) -> EnvironmentGraph:
    env = env_template_for_scenario(scenario_id)
    g = EnvironmentGraph()
    for asset in env.assets:
        g.add_node(
            GraphNode(
                node_id=asset.id,
                kind=NodeKind.ASSET,
                type=AssetType(asset.type),
                label=asset.label or asset.id,
                attrs=dict(asset.attrs),
            )
        )
    service_to_asset: dict[str, str] = {}
    for svc in env.services:
        service_to_asset[svc.id] = svc.asset
        g.add_node(
            GraphNode(
                node_id=svc.id,
                kind=NodeKind.SERVICE,
                type=None,
                label=svc.endpoint or svc.id,
                attrs={"kind": svc.kind, "endpoint": svc.endpoint, **svc.attrs},
            )
        )
        g.add_edge(
            GraphEdge(
                edge_id=f"edge:{svc.asset}:{svc.id}:EXPOSES",
                from_node=svc.asset,
                to_node=svc.id,
                type=EdgeType.EXPOSES,
            )
        )
    for cred in env.credentials:
        g.add_node(
            GraphNode(
                node_id=cred.id,
                kind=NodeKind.CREDENTIAL,
                type=None,
                label=cred.id,
                attrs=dict(cred.attrs),
            )
        )
        g.add_edge(
            GraphEdge(
                edge_id=f"edge:{cred.owner}:{cred.id}:STORES",
                from_node=cred.owner,
                to_node=cred.id,
                type=EdgeType.STORES,
            )
        )
    for data in env.data:
        g.add_node(
            GraphNode(
                node_id=data.id,
                kind=NodeKind.DATA,
                type=None,
                label=data.id,
                attrs=dict(data.attrs),
            )
        )
        if data.store:
            g.add_edge(
                GraphEdge(
                    edge_id=f"edge:{data.store}:{data.id}:STORES",
                    from_node=data.store,
                    to_node=data.id,
                    type=EdgeType.STORES,
                )
            )
    for e in env.edges:
        edge_type = _EDGE_KIND.get(e.type)
        if edge_type is None:
            raise ValueError(f"unknown edge type in env template: {e.type!r}")
        g.add_edge(
            GraphEdge(
                edge_id=f"edge:{e.from_}:{e.to}:{e.type}",
                from_node=e.from_,
                to_node=e.to,
                type=edge_type,
                attrs=dict(e.attrs),
            )
        )
    # SERVICE-level READS/WRITES inheritance (docs/05 §3.5).
    for asset_edge in list(g.edges.values()):
        if asset_edge.type not in (EdgeType.READS, EdgeType.WRITES):
            continue
        for svc_id, svc_asset in service_to_asset.items():
            if svc_asset != asset_edge.from_node:
                continue
            eid = f"edge:{svc_id}:{asset_edge.to_node}:{asset_edge.type.value}"
            if eid not in g.edges:
                g.add_edge(
                    GraphEdge(
                        edge_id=eid,
                        from_node=svc_id,
                        to_node=asset_edge.to_node,
                        type=asset_edge.type,
                        attrs=dict(asset_edge.attrs),
                    )
                )
    return g


__all__ = ["APISimulator"]
