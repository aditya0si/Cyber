"""Graph type system (docs/05 §3, docs/10 §2.1).

Node/edge taxonomy, foothold-state machine, and value-types shared by the
simulator framework, normalizer, and graph engine. No NetworkX dependency here —
the repository impl (Phase 3) uses these types as the public surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class NodeKind(StrEnum):
    ASSET = "ASSET"
    SERVICE = "SERVICE"
    CREDENTIAL = "CREDENTIAL"
    DATA = "DATA"
    NETWORK_ZONE = "NETWORK_ZONE"
    EDGE_DEVICE = "EDGE_DEVICE"
    # Overlay-layer attack-narrative node types (added per 02b §Part 1).
    USER = "USER"
    ATTACK = "ATTACK"
    EVENT = "EVENT"
    VULNERABILITY = "VULNERABILITY"


class AssetType(StrEnum):
    GATEWAY = "gateway"
    LOAD_BALANCER = "load_balancer"
    WEB_SERVER = "web_server"
    API_SERVER = "api_server"
    DATABASE = "database"
    AUTH_SERVICE = "auth_service"
    IDENTITY_PROVIDER = "identity_provider"
    WORKER = "worker"
    CACHE = "cache"
    WORKSTATION = "workstation"
    BASTION = "bastion"
    DEPENDENCY = "dependency"
    PACKAGE_REGISTRY = "package_registry"
    PACKAGE = "package"
    USER_ACCOUNT = "user_account"


class EdgeType(StrEnum):
    CONNECTS_TO = "CONNECTS_TO"
    EXPOSES = "EXPOSES"
    RUNS = "RUNS"
    AUTHENTICATES_WITH = "AUTHENTICATES_WITH"
    STORES = "STORES"
    TRUSTS = "TRUSTS"
    DEPENDS_ON = "DEPENDS_ON"
    FETCHES_FROM = "FETCHES_FROM"
    LATERAL_TO = "LATERAL_TO"
    READS = "READS"
    WRITES = "WRITES"
    IMPACTS = "IMPACTS"


class FootholdState(StrEnum):
    CLEAN = "clean"
    RECON = "recon"
    ATTEMPTED = "attempted"
    FOOTHOLD = "foothold"
    COMPROMISED = "compromised"
    CONTAINED = "contained"
    QUARANTINED = "quarantined"

    def is_compromised(self) -> bool:
        return self in (FootholdState.FOOTHOLD, FootholdState.COMPROMISED)


@dataclass(frozen=True)
class GraphNode:
    node_id: str
    kind: NodeKind
    type: AssetType | None
    label: str
    attrs: dict[str, Any] = field(default_factory=dict)
    foothold_state: FootholdState = FootholdState.CLEAN


@dataclass(frozen=True)
class GraphEdge:
    edge_id: str
    from_node: str
    to_node: str
    type: EdgeType
    attrs: dict[str, Any] = field(default_factory=dict)
    active: bool = True


@dataclass(frozen=True)
class OverlayNode:
    """Attacker-side annotation anchored on a graph node (docs/05 §3.3)."""

    node_id: str  # overlay-local id (e.g., "ov_login")
    parent_node_id: str  # graph node id it annotates
    state: FootholdState
    flags: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EdgeTransition:
    """A single step in an `AttackPath` — typed edge traversed by the attacker."""

    edge_id: str
    from_node: str
    to_node: str
    type: EdgeType
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AttackPath:
    """An attacker-side chain across the environment+overlay graph.

    `closes_at_node_kind` is `NodeKind.DATA` when the path reaches sensitive
    data (an exfil-candidate); for defensive scoring we ask graph-engine to
    surface these to set severity floors (docs/05 §6.1, docs/11 §3.4).
    """

    nodes: list[str]
    edges: list[EdgeTransition]
    closes_at_node_kind: NodeKind
    length: int

    def __post_init__(self) -> None:
        if self.length != len(self.edges):
            object.__setattr__(self, "length", len(self.edges))


@dataclass
class EnvironmentGraph:
    """Light container for an environment+overlay graph (Phase 1 minimal).

    Phase 3 (`graph/repo.py`) introduces the `GraphRepository` abstraction
    with NetworkX impl; this dataclass serves as the public transport type for
    simulator `init()` results and snapshot/delta payloads.
    """

    nodes: dict[str, GraphNode] = field(default_factory=dict)
    edges: dict[str, GraphEdge] = field(default_factory=dict)
    overlay: dict[str, OverlayNode] = field(default_factory=dict)

    def add_node(self, node: GraphNode) -> None:
        self.nodes[node.node_id] = node

    def add_edge(self, edge: GraphEdge) -> None:
        self.edges[edge.edge_id] = edge

    def get_node(self, node_id: str) -> GraphNode | None:
        return self.nodes.get(node_id)

    def edge(self, edge_id: str) -> GraphEdge | None:
        return self.edges.get(edge_id)

    def neighbors(self, node_id: str, types: list[EdgeType] | None = None) -> list[str]:
        kind_filter = set(types) if types else None
        out: list[str] = []
        for edge in self.edges.values():
            if edge.from_node != node_id or not edge.active:
                continue
            if kind_filter is not None and edge.type not in kind_filter:
                continue
            out.append(edge.to_node)
        return out
