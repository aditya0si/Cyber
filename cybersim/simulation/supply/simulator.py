"""Supply Chain simulator (docs/06 §6, docs/21 Task 7.1)."""

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
from cybersim.simulation.base import RawEvent, ResponseCommand, SimBeat
from cybersim.simulation.catalog import env_template_for_scenario
from cybersim.simulation.core.context import SimContext
from cybersim.simulation.supply import beats as supply_beats
from cybersim.simulation.supply.commands import apply_command as _apply_command

_EDGE_KIND = {
    "EXPOSES": EdgeType.EXPOSES,
    "READS": EdgeType.READS,
    "WRITES": EdgeType.WRITES,
    "CONNECTS_TO": EdgeType.CONNECTS_TO,
    "AUTHENTICATES_WITH": EdgeType.AUTHENTICATES_WITH,
    "STORES": EdgeType.STORES,
    "DEPENDS_ON": EdgeType.DEPENDS_ON,
    "FETCHES_FROM": EdgeType.FETCHES_FROM,
    "RUNS": EdgeType.RUNS,
}


class SupplyChainSimulator:
    """The MVP Supply Chain simulator (docs/06 §6)."""

    id = "supply"

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
        for beat in supply_beats.phases(ctx):
            yield self._post_process(beat, ctx)

    def _post_process(self, beat: SimBeat, ctx: SimContext) -> SimBeat:
        if not self._state:
            return beat
        out: list[RawEvent] = []
        for ev in beat.events:
            if ev.benign:
                out.append(ev)
                continue
            if (self._state.get("hooks_blocked") and ev.type == "package.lifecycle.hook") or (
                self._state.get("package_removed")
                and ev.type
                in (
                    "package.lifecycle.hook",
                    "process.exec",
                    "process.env_exfil",
                )
            ):
                ev = ev.model_copy(update={"payload": {**ev.payload, "blocked": True}})
            elif self._state.get("registry_blocked") and ev.type == "build.dependency_resolve":
                ev = ev.model_copy(update={"payload": {**ev.payload, "fetch_failed": True}})
            elif self._state.get("egress_blocked", False) and ev.type == "net.connection":
                ev = ev.model_copy(update={"payload": {**ev.payload, "blocked": True}})
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
    for svc in env.services:
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
    return g


__all__ = ["SupplyChainSimulator"]
