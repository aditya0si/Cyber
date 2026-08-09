"""Graph types & neighbor lookups (docs/05 §3, docs/10 §2.1)."""

from __future__ import annotations

import pytest

from cybersim.graph.types import (
    AssetType,
    AttackPath,
    EdgeType,
    EnvironmentGraph,
    FootholdState,
    GraphEdge,
    GraphNode,
    NodeKind,
)


def _env() -> EnvironmentGraph:
    g = EnvironmentGraph()
    g.add_node(GraphNode("lb1", NodeKind.ASSET, AssetType.LOAD_BALANCER, "LB"))
    g.add_node(GraphNode("login_ep", NodeKind.SERVICE, None, "/api/login"))
    g.add_node(GraphNode("users_db", NodeKind.ASSET, AssetType.DATABASE, "DB"))
    g.add_edge(GraphEdge("e1", "lb1", "login_ep", EdgeType.EXPOSES))
    g.add_edge(GraphEdge("e2", "login_ep", "users_db", EdgeType.READS))
    g.add_edge(GraphEdge("e3", "lb1", "users_db", EdgeType.CONNECTS_TO, active=False))
    return g


def test_add_node_overwrites_same_id() -> None:
    g = _env()
    new = GraphNode("lb1", NodeKind.ASSET, AssetType.LOAD_BALANCER, "LB-updated")
    g.add_node(new)
    assert g.get_node("lb1").label == "LB-updated"


def test_neighbors_filters_active_only() -> None:
    g = _env()
    assert g.neighbors("lb1") == ["login_ep"]  # inactive e3 excluded


def test_neighbors_filters_by_edge_type() -> None:
    g = _env()
    assert g.neighbors("lb1", types=[EdgeType.EXPOSES]) == ["login_ep"]
    assert g.neighbors("lb1", types=[EdgeType.CONNECTS_TO]) == []


def test_foothold_state_is_compromised_predicate() -> None:
    assert FootholdState.FOOTHOLD.is_compromised()
    assert FootholdState.COMPROMISED.is_compromised()
    assert not FootholdState.ATTEMPTED.is_compromised()
    assert not FootholdState.CONTAINED.is_compromised()


def test_attack_path_length_auto_computed() -> None:
    from cybersim.graph.types import EdgeTransition

    transitions = [
        EdgeTransition("e1", "lb1", "login_ep", EdgeType.EXPOSES),
        EdgeTransition("e2", "login_ep", "users_db", EdgeType.READS),
    ]
    # passing length=99 will be overridden by post_init
    p = AttackPath(
        nodes=["lb1", "login_ep", "users_db"],
        edges=transitions,
        closes_at_node_kind=NodeKind.DATA,
        length=99,
    )
    assert p.length == 2
    assert p.closes_at_node_kind == NodeKind.DATA


def test_environment_graph_has_unique_node_ids() -> None:
    g = _env()
    assert sorted(g.nodes.keys()) == ["lb1", "login_ep", "users_db"]


@pytest.mark.parametrize(
    ("node_kind", "expected"),
    [
        (NodeKind.ASSET, "ASSET"),
        (NodeKind.SERVICE, "SERVICE"),
        (NodeKind.CREDENTIAL, "CREDENTIAL"),
        (NodeKind.DATA, "DATA"),
    ],
)
def test_node_kind_str_values(node_kind: NodeKind, expected: str) -> None:
    assert node_kind.value == expected
