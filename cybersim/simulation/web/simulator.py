"""Web App simulator implementation (docs/06 §3, docs/21 Task 2.2)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from cybersim.events.payloads import (
    AuthAttemptPayload,
    AuthSuccessPayload,
    DBErrorPayload,
    DBQueryPayload,
    HTTPRequestPayload,
    ResponseAppliedPayload,
    SessionCreatedPayload,
)
from cybersim.graph.types import (
    AssetType,
    EdgeType,
    EnvironmentGraph,
    GraphEdge,
    GraphNode,
    NodeKind,
)
from cybersim.simulation.base import RawEvent, ResponseCommand, SimBeat, Simulator
from cybersim.simulation.catalog import env_template_for_scenario
from cybersim.simulation.core.context import SimContext
from cybersim.simulation.web import beats as web_beats
from cybersim.simulation.web.commands import apply_command as _apply_command

_ENV_EDGE_TO_KIND = {
    "EXPOSES": EdgeType.EXPOSES,
    "READS": EdgeType.READS,
    "WRITES": EdgeType.WRITES,
    "CONNECTS_TO": EdgeType.CONNECTS_TO,
    "AUTHENTICATES_WITH": EdgeType.AUTHENTICATES_WITH,
    "STORES": EdgeType.STORES,
    "TRUSTS": EdgeType.TRUSTS,
    "DEPENDS_ON": EdgeType.DEPENDS_ON,
    "FETCHES_FROM": EdgeType.FETCHES_FROM,
    "LATERAL_TO": EdgeType.LATERAL_TO,
    "IMPACTS": EdgeType.IMPACTS,
    "RUNS": EdgeType.RUNS,
}
_ENV_EDGE_MARKERS = (
    "EXPOSES",
    "READS",
    "WRITES",
    "CONNECTS_TO",
    "AUTHENTICATES_WITH",
    "STORES",
    "TRUSTS",
    "DEPENDS_ON",
    "FETCHES_FROM",
    "LATERAL_TO",
    "IMPACTS",
    "RUNS",
)


def build_environment_graph(scenario_id: str) -> EnvironmentGraph:
    """Build an initial `EnvironmentGraph` from the scenario's env template."""
    env = env_template_for_scenario(scenario_id)
    g = EnvironmentGraph()

    # Assets
    for asset in env.assets:
        a_type = AssetType(asset.type)
        g.add_node(
            GraphNode(
                node_id=asset.id,
                kind=NodeKind.ASSET,
                type=a_type,
                label=asset.label or asset.id,
                attrs=dict(asset.attrs),
            )
        )
    # Services — kind=SERVICE; EXPOSES edge from owning asset
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
        eid = f"edge:{svc.asset}:{svc.id}:EXPOSES"
        g.add_edge(
            GraphEdge(
                edge_id=eid,
                from_node=svc.asset,
                to_node=svc.id,
                type=EdgeType.EXPOSES,
                attrs={},
            )
        )
    # Credentials — kind=CREDENTIAL; STORES edge from owner
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
        eid = f"edge:{cred.owner}:{cred.id}:STORES"
        g.add_edge(
            GraphEdge(
                edge_id=eid,
                from_node=cred.owner,
                to_node=cred.id,
                type=EdgeType.STORES,
                attrs={},
            )
        )
    # Data — kind=DATA
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
            eid = f"edge:{data.store}:{data.id}:STORES"
            g.add_edge(
                GraphEdge(
                    edge_id=eid,
                    from_node=data.store,
                    to_node=data.id,
                    type=EdgeType.STORES,
                    attrs={},
                )
            )
    # Edges from YAML
    for e in env.edges:
        edge_type_str = e.type
        edge_type = _ENV_EDGE_TO_KIND.get(edge_type_str)
        if edge_type is None:
            raise ValueError(f"unknown edge type in env template: {edge_type_str!r}")
        eid = f"edge:{e.from_}:{e.to}:{edge_type_str}"
        g.add_edge(
            GraphEdge(
                edge_id=eid,
                from_node=e.from_,
                to_node=e.to,
                type=edge_type,
                attrs=dict(e.attrs),
            )
        )

    # ---- inferred SERVICE-level READS/WRITES (hosted-on asset inheritance)
    # For each ASSET-level READS/WRITES edge, mirror it onto each SERVICE
    # hosted on that asset so attack-path queries like
    # lb1 -> login_ep -> users_db -> user_data close at DATA (docs/05 §3.5).
    service_to_asset: dict[str, str] = {svc.id: svc.asset for svc in env.services}
    for asset_edge in list(g.edges.values()):
        if asset_edge.type not in (EdgeType.READS, EdgeType.WRITES):
            continue
        asset_id = asset_edge.from_node
        target_id = asset_edge.to_node
        for svc_id, svc_asset in service_to_asset.items():
            if svc_asset != asset_id:
                continue
            eid = f"edge:{svc_id}:{target_id}:{asset_edge.type.value}"
            if eid in g.edges:
                continue
            g.add_edge(
                GraphEdge(
                    edge_id=eid,
                    from_node=svc_id,
                    to_node=target_id,
                    type=asset_edge.type,
                    attrs=dict(asset_edge.attrs),
                )
            )
    return g


PAYLOAD_VALIDATORS: dict[str, type] = {
    "http.request": HTTPRequestPayload,
    "http.error": HTTPRequestPayload,  # http_error is HTTPRequestPayload-shaped w/ status≥400
    "db.query": DBQueryPayload,
    "db.error": DBErrorPayload,
    "auth.attempt": AuthAttemptPayload,
    "auth.success": AuthSuccessPayload,
    "session.created": SessionCreatedPayload,
    "response.applied": ResponseAppliedPayload,
}


class WebSimulator:
    """The MVP Web App simulator (docs/06 §3)."""

    id = "web"

    def __init__(self) -> None:
        self._env: EnvironmentGraph | None = None
        self._state: dict[str, Any] = {}
        self._attacker_ip = web_beats.ATTACKER_IP

    @property
    def environment(self) -> EnvironmentGraph:
        if self._env is None:
            raise RuntimeError("init() not called before reading environment")
        return self._env

    def init(self, ctx: SimContext) -> None:
        """Build the env graph from the scenario referenced by ctx.scenario_id."""
        self._env = build_environment_graph(ctx.scenario_id)
        self._state = {}
        self._attacker_ip = str(ctx.params.get("attacker_ip", web_beats.ATTACKER_IP))

    def beats(self, ctx: SimContext) -> Iterator[SimBeat]:
        """Yield beats through the SQLi kill chain (docs/06 §3.4).

        Post-command beats honour `self._state`: blocked_ips return 403,
        rate-limited endpoints dropped when over cap, disabled endpoints 503,
        patched SQLi converts payloads to parameterized queries.
        """
        for beat in web_beats.phases(ctx, self._attacker_ip):
            yield self._post_process(beat, ctx)

    def _post_process(self, beat: SimBeat, ctx: SimContext) -> SimBeat:
        """Mutate beat events to reflect any response actions in state."""
        if not self._state:
            return beat
        new_events: list[RawEvent] = []
        for ev in beat.events:
            if ev.benign:
                new_events.append(ev)
                continue
            if self._state.get("blocked_ips") and ev.src_ip in self._state["blocked_ips"]:
                ev = ev.model_copy(
                    update={"payload": {**ev.payload, "status": 403, "blocked": True}}
                )
            elif self._state.get("disabled") and ev.node_ref in self._state["disabled"]:
                ev = ev.model_copy(
                    update={"payload": {**ev.payload, "status": 503, "disabled": True}}
                )
            elif (
                ev.type == "db.query"
                and self._state.get("sqli_patched")
                and not ev.payload.get("parameterized", True)
            ):
                ev = ev.model_copy(
                    update={
                        "payload": {
                            **ev.payload,
                            "parameterized": True,
                            "rows_returned": 0,
                            "exfil_candidate": False,
                        }
                    }
                )
            elif (
                ev.type == "auth.success"
                and self._state.get("credentials_rotated")
                and ev.payload.get("account_id") == "admin@finbank"
            ):
                ev = ev.model_copy(
                    update={
                        "payload": {
                            **ev.payload,
                            "invalidated": True,
                            "factor": "rotated",
                        }
                    }
                )
            new_events.append(ev)
        return SimBeat(sim_time_ms=beat.sim_time_ms, events=new_events)

    def apply_command(self, cmd: ResponseCommand, ctx: SimContext) -> list[RawEvent]:
        """Delegate to the command module (docs/06 §3.6)."""
        if self._env is None:
            raise RuntimeError("init() must be called before apply_command()")
        return _apply_command(cmd, ctx, self._state)


# Assertion that WebSimulator conforms to the Simulator Protocol statically.
_Sim: Simulator = WebSimulator()


__all__ = ["WebSimulator", "build_environment_graph"]
