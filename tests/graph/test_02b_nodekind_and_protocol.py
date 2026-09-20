"""02b verification tests — NodeKind completeness + protocol enforcement."""

from __future__ import annotations

import inspect

import pytest

from cybersim.analyst.dto import RecommendedAction
from cybersim.events.schema import assemble
from cybersim.graph.event_mutator import apply_event_to_graph, apply_response_actions
from cybersim.graph.repo import GraphRepository
from cybersim.graph.repo_nx import NetworkXGraphRepository
from cybersim.graph.types import FootholdState, NodeKind
from cybersim.simulation.scenario import CredentialCompromiseScenario
from cybersim.simulation.web.simulator import build_environment_graph


@pytest.fixture
def repo():
    return NetworkXGraphRepository()


@pytest.fixture
def env():
    return build_environment_graph("web.app.sqli_login")


@pytest.fixture
def sim_id():
    return "demo"


# ── Test 1 ─────────────────────────────────────────────────────────────────────


def test_nodekind_includes_user_attack_event_vulnerability():
    """NodeKind enum must contain all four overlay-layer types from 00 §Section 6."""
    required = {"USER", "ATTACK", "EVENT", "VULNERABILITY"}
    existing = {m.name for m in NodeKind}
    missing = required - existing
    assert not missing, f"NodeKind is missing: {missing}"


# ── Test 2 ─────────────────────────────────────────────────────────────────────


def test_credential_compromise_scenario_creates_user_and_attack_nodes(repo, env, sim_id):
    """Running the 01 scenario through the graph layer must create USER and ATTACK nodes."""
    repo.create(sim_id, env)
    scenario = CredentialCompromiseScenario()
    scenario.start(delay=0)
    for event in scenario.get_events():
        apply_event_to_graph(event, repo, sim_id)

    # USER nodes (NodeKind.USER) — created on LOGIN_SUCCESS
    user_nodes = repo.find_nodes_by_kind(sim_id, NodeKind.USER)
    assert len(user_nodes) > 0, "Expected at least one USER-kind node after scenario"
    assert any("admin" in n.node_id.lower() or "service" in n.node_id.lower() for n in user_nodes)

    # ATTACK nodes (NodeKind.ATTACK) — created on LOGIN_FAILED burst
    attack_nodes = repo.find_nodes_by_kind(sim_id, NodeKind.ATTACK)
    assert len(attack_nodes) > 0, "Expected at least one ATTACK-kind node after scenario"
    assert any("brute" in n.node_id.lower() for n in attack_nodes)

    # EVENT nodes (NodeKind.EVENT) — created for each processed event
    event_nodes = repo.find_nodes_by_kind(sim_id, NodeKind.EVENT)
    assert len(event_nodes) > 0, "Expected at least one EVENT-kind node after scenario"


# ── Test 3 ─────────────────────────────────────────────────────────────────────


def test_apply_response_actions_uses_protocol_only():
    """apply_response_actions must not reference _require, .env, or .overlay as code."""
    import re

    import cybersim.graph.event_mutator as _mut_module

    full_source = inspect.getsource(_mut_module)

    # Strip docstrings and comments before checking — we only care about code
    # Use a simple heuristic: remove triple-quoted strings and # lines
    code_only = re.sub(r'""".*?"""', "", full_source, flags=re.DOTALL)
    code_only = re.sub(r"'''.*?'''", "", code_only, flags=re.DOTALL)
    code_only = re.sub(r"#.*", "", code_only)

    # These must not appear in executable code
    forbidden_patterns = [
        r"\._require\(",  # calling private method
        r"\.env\.nodes",  # direct NX env access
        r"\.env\.edges",
        r"\.overlay\.nodes",  # direct NX overlay access
        r"\.overlay\.edges",
        r"\.overlay\.remove_edge",
    ]
    for pattern in forbidden_patterns:
        match = re.search(pattern, code_only)
        assert match is None, (
            f"event_mutator.py code contains forbidden bypass pattern {pattern!r} "
            f"at position {match.start()}: ...{code_only[max(0, match.start() - 40) : match.end() + 40]!r}..."
        )


# ── Test 3b ────────────────────────────────────────────────────────────────────


def test_apply_response_actions_mock_boundary():
    """Hermetic mock-boundary proof: apply_response_actions only calls real protocol methods.

    MagicMock(spec=GraphRepository) exposes ONLY the methods declared on the
    Protocol.  Accessing _require, .env, .overlay — or any other non-protocol
    attribute — raises AttributeError immediately, catching alias tricks the
    regex test cannot.
    """
    from unittest.mock import MagicMock

    from cybersim.graph.types import FootholdState, GraphNode, NodeKind

    mock_repo = MagicMock(spec=GraphRepository)

    # find_nodes_by_kind must return iterable GraphNode lists.
    # For isolate_account: return one compromised USER node.
    compromised_user = GraphNode(
        node_id="user_admin",
        kind=NodeKind.USER,
        type=None,
        label="User (admin)",
        attrs={"status": "compromised"},
        foothold_state=FootholdState.COMPROMISED,
    )

    # For block_database: no DATA nodes in this fixture.
    # find_nodes_by_kind is called with (sim_id, NodeKind.USER) and (sim_id, NodeKind.CREDENTIAL)
    # for isolate_account, so we need to route by kind argument.
    def _find_nodes_by_kind(sim_id, kind):
        if kind == NodeKind.USER:
            return [compromised_user]
        return []

    mock_repo.find_nodes_by_kind.side_effect = _find_nodes_by_kind
    mock_repo.find_overlay_edges.return_value = []  # no USES edges to revoke

    sim_id = "mock-sim"
    actions = [RecommendedAction(action_id="isolate_account", order=1, rationale="boundary-test")]

    # This must not raise — if it does, apply_response_actions tried to access
    # a non-protocol attribute (AttributeError) or broke in some other way.
    apply_response_actions(mock_repo, sim_id, actions)

    # Collect all method names actually called on the mock
    called_methods = {c[0] for c in mock_repo.method_calls}

    # Must have called find_nodes_by_kind (to find compromised nodes)
    assert "find_nodes_by_kind" in called_methods, (
        f"Expected find_nodes_by_kind to be called; got: {called_methods}"
    )
    # Must have called upsert_node (to write the isolated state back)
    assert "upsert_node" in called_methods, (
        f"Expected upsert_node to be called; got: {called_methods}"
    )

    # Must NOT have called anything outside the protocol surface.
    # The full protocol method set:
    protocol_methods = {
        "create",
        "load",
        "drop",
        "upsert_node",
        "upsert_edge",
        "deactivate_edge",
        "update_foothold",
        "append_overlay",
        "add_overlay_edge",
        "get_node",
        "get_edges",
        "neighbors",
        "can_reach",
        "attack_paths",
        "graph_view",
        "snapshot",
        "delta",
        "find_nodes_by_kind",
        "find_overlay_edges",
        "remove_overlay_edge",
    }
    non_protocol_calls = called_methods - protocol_methods
    assert not non_protocol_calls, (
        f"apply_response_actions called non-protocol methods: {non_protocol_calls}"
    )


def test_containment_updates_reflected_via_protocol_query(repo, env, sim_id):
    """After apply_response_actions, isolation/block must be visible via protocol queries."""
    repo.create(sim_id, env)

    # Put a compromised user node in the graph
    event_login = assemble(
        event_id="ev1",
        timestamp="2026-08-10T10:00:00Z",
        event_type="LOGIN_SUCCESS",
        severity="HIGH",
        source_ip="192.168.1.100",
        target_asset="auth-api",
        actor="admin",
    )
    # Prime the LOGIN_FAILED attack node first (needed for RESULTED_IN edge)
    event_fail = assemble(
        event_id="ev0",
        timestamp="2026-08-10T09:59:00Z",
        event_type="LOGIN_FAILED",
        severity="LOW",
        source_ip="192.168.1.100",
        target_asset="auth-api",
        actor="unknown",
    )
    apply_event_to_graph(event_fail, repo, sim_id)
    apply_event_to_graph(event_login, repo, sim_id)

    # Confirm user is COMPROMISED before containment
    user_node = repo.get_node(sim_id, "user_admin")
    assert user_node is not None
    assert user_node.foothold_state == FootholdState.COMPROMISED

    # Run containment
    apply_response_actions(
        repo, sim_id, [RecommendedAction(action_id="isolate_account", order=1, rationale="test")]
    )

    # Query back through protocol — must see isolation
    user_nodes = repo.find_nodes_by_kind(sim_id, NodeKind.USER)
    isolated = [n for n in user_nodes if n.attrs.get("status") == "isolated"]
    assert len(isolated) > 0, (
        "Expected at least one USER node with status=isolated after containment"
    )

    # Also verify via get_node
    user_after = repo.get_node(sim_id, "user_admin")
    assert user_after is not None
    assert user_after.attrs.get("status") == "isolated"
    assert user_after.foothold_state == FootholdState.CONTAINED
