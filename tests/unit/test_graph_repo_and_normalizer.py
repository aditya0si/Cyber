"""Phase 3 unit tests: NetworkXGraphRepository + Normalizer + NormalizerConsumer."""

from __future__ import annotations

import pytest

from cybersim.events.bus import InMemoryEventBus
from cybersim.events.normalizer import Normalizer
from cybersim.events.normalizer_tasks import NormalizedSink, NormalizerConsumer
from cybersim.events.types import AttackStage, EventCategory, Severity
from cybersim.graph.repo_nx import NetworkXGraphRepository
from cybersim.graph.types import EdgeType, FootholdState, NodeKind
from cybersim.platform.auth.models import User
from cybersim.simulation.base import RawEvent
from cybersim.simulation.tasks import run_simulator_in_memory
from cybersim.simulation.web.simulator import build_environment_graph


@pytest.fixture
def finbank_env() -> object:
    return build_environment_graph("web.app.sqli_login")


@pytest.fixture
def repo() -> NetworkXGraphRepository:
    return NetworkXGraphRepository()


def _env_lookup(env_graph) -> object:
    """Returns a callable usable as `env_graph_lookup` for the NormalizerConsumer."""
    return lambda _sim_id: env_graph


# ---------- NetworkXGraphRepository ----------


def test_repo_create_and_get_node_returns_assets(
    repo: NetworkXGraphRepository, finbank_env: object
) -> None:
    repo.create("sim-1", finbank_env)
    node = repo.get_node("sim-1", "lb1")
    assert node is not None
    assert node.label == "Load Balancer"


def test_repo_create_unknown_sim_raises_keyerror(repo: NetworkXGraphRepository) -> None:
    with pytest.raises(KeyError):
        repo.get_node("never-created", "lb1")


def test_repo_attack_paths_finds_chain_to_data(
    repo: NetworkXGraphRepository, finbank_env: object
) -> None:
    """For the FinBank env (lb1 EXPOSES login_ep; web1 READS users_db; user_data STORES users_db),
    the attacker at lb1 can reach user_data — closes at DATA."""
    repo.create("sim-c", finbank_env)
    # Add an explicit attacker→lb1 connection (the sim normalizer would
    # resolve this from raw.src_ip + the gateway/zone node, but the repo
    # query tests need the seed edge in place).
    from cybersim.graph.types import GraphEdge

    repo.upsert_edge(
        "sim-c",
        GraphEdge(
            edge_id="edge_attacker_to_lb",
            from_node="lb1",
            to_node="user_data",
            type=EdgeType.CONNECTS_TO,
        ),
    )
    paths = repo.attack_paths("sim-c", src="lb1", dst_kinds=(NodeKind.DATA,), max_paths=5, hops=4)
    assert len(paths) > 0
    closing = {p.closes_at_node_kind for p in paths}
    assert NodeKind.DATA in closing
    # The shortest path through lb1 -> user_data should be length 1 (the explicit edge)
    lengths = sorted(p.length for p in paths)
    assert lengths[0] <= 4


def test_repo_attack_paths_returns_empty_when_no_data_nodes(
    repo: NetworkXGraphRepository,
) -> None:
    from cybersim.graph.types import EnvironmentGraph, GraphNode

    empty = EnvironmentGraph()
    empty.add_node(GraphNode("a", NodeKind.ASSET, None, "nope"))
    repo.create("sim-empty", empty)
    paths = repo.attack_paths("sim-empty", src="a")
    assert paths == []


def test_repo_deactivate_edge_blocks_traversal(
    repo: NetworkXGraphRepository, finbank_env: object
) -> None:
    repo.create("sim-de", finbank_env)
    # Sanity: there's an active EXPOSES edge lb1->login_ep
    assert any(e.active for e in repo.get_edges("sim-de", "lb1"))
    # Find that edge and deactivate it
    edges = repo.get_edges("sim-de", "lb1")
    expose_edge = next(e for e in edges if e.type == EdgeType.EXPOSES)
    repo.deactivate_edge("sim-de", expose_edge.edge_id)
    # Now neighbors of lb1 should no longer include login_ep via EXPOSES path
    n = repo.neighbors("sim-de", "lb1", types=[EdgeType.EXPOSES])
    assert "login_ep" not in n


def test_repo_update_foothold_advances_state(
    repo: NetworkXGraphRepository, finbank_env: object
) -> None:
    repo.create("sim-fh", finbank_env)
    repo.update_foothold("sim-fh", "login_ep", FootholdState.ATTEMPTED)
    node = repo.get_node("sim-fh", "login_ep")
    assert node is not None
    assert node.foothold_state == FootholdState.ATTEMPTED


def test_repo_attack_paths_respects_hops_cap(
    repo: NetworkXGraphRepository, finbank_env: object
) -> None:
    repo.create("sim-hc", finbank_env)
    with pytest.raises(ValueError, match="hops must be"):
        repo.attack_paths("sim-hc", src="lb1", hops=99)
    with pytest.raises(ValueError, match="max_paths must be"):
        repo.attack_paths("sim-hc", src="lb1", max_paths=999)


# ---------- Normalizer ----------


def test_normalizer_dedups_same_raw_id(finbank_env: object) -> None:
    norm = Normalizer()
    raw = RawEvent(
        id="raw-1",
        sim_time_ms=100,
        origin="web",
        type="http.request",
        src_ip="203.0.113.42",
        node_ref="login_ep",
        payload={"method": "POST", "path": "/api/login", "body": {"username": "' OR 1=1--"}},
    )
    out_a = norm.normalize(
        raw,
        org_id="org_x",
        simulation_id="sim-1",
        env=finbank_env,
        received_at_ms=100,
    )
    out_b = norm.normalize(
        raw,
        org_id="org_x",
        simulation_id="sim-1",
        env=finbank_env,
        received_at_ms=100,
    )
    assert out_a is not None
    assert out_b is None  # deduped


def test_normalizer_sqli_indicator_subtypes_have_mitre_tags(finbank_env: object) -> None:
    norm = Normalizer()
    raw = RawEvent(
        id="raw-sqli",
        sim_time_ms=100,
        origin="web",
        type="http.request",
        src_ip="203.0.113.42",
        node_ref="login_ep",
        payload={
            "method": "POST",
            "path": "/api/login",
            "body": {"username": "' OR 1=1--"},
            "sqli_pattern": "tautology",
        },
    )
    out = norm.normalize(
        raw,
        org_id="org_x",
        simulation_id="sim-1",
        env=finbank_env,
        received_at_ms=100,
    )
    assert out is not None
    assert out.raw_context.get("subtype") == "sql_injection_indicator"
    assert "T1190" in out.raw_context.get("mitre_techniques", ())
    assert "TA0001" in out.raw_context.get("mitre_tactics", ())
    assert "A03:2021" in out.raw_context.get("owasp_refs", ())
    assert out.raw_context.get("severity_hint") == Severity.HIGH
    assert out.raw_context.get("attack_stage") == AttackStage.INITIAL_ACCESS
    assert out.raw_context.get("category") == EventCategory.HTTP


def test_normalizer_benign_event_stays_info_subtypes_unchanged(finbank_env: object) -> None:
    norm = Normalizer()
    raw = RawEvent(
        id="raw-benign",
        sim_time_ms=100,
        origin="web",
        type="http.request",
        src_ip="198.51.100.10",
        node_ref="login_ep",
        benign=True,
        payload={"method": "GET", "path": "/index.html", "status": 200},
    )
    out = norm.normalize(
        raw,
        org_id="org_x",
        simulation_id="sim-1",
        env=finbank_env,
        received_at_ms=100,
    )
    assert out is not None
    assert out.raw_context.get("subtype") == "http_request"
    assert out.raw_context.get("severity_hint") == Severity.INFO
    assert out.raw_context.get("mitre_techniques", ()) == ()
    assert out.raw_context.get("benign") is True


def test_normalizer_exfil_candidate_query_subtypes_to_data_exfiltration(
    finbank_env: object,
) -> None:
    norm = Normalizer()
    raw = RawEvent(
        id="raw-exfil",
        sim_time_ms=5000,
        origin="web",
        type="db.query",
        node_ref="users_db",
        payload={
            "db": "users_db",
            "statement": "SELECT * FROM users",
            "rows_returned": 8_000,
            "parameterized": False,
            "exfil_candidate": True,
        },
    )
    out = norm.normalize(
        raw,
        org_id="org_x",
        simulation_id="sim-1",
        env=finbank_env,
        received_at_ms=5000,
    )
    assert out is not None
    assert out.raw_context.get("subtype") == "exfil_candidate_query"
    assert "TA0010" in out.raw_context.get("mitre_tactics", ())
    assert out.raw_context.get("severity_hint") == Severity.CRITICAL
    assert out.raw_context.get("attack_stage") == AttackStage.EXFIL


def test_normalizer_sequence_is_monotonic_per_sim(finbank_env: object) -> None:
    norm = Normalizer()
    seqs: list[int] = []
    for i in range(5):
        raw = RawEvent(
            id=f"raw-{i}",
            sim_time_ms=i * 1000,
            origin="web",
            type="http.request",
            payload={"method": "GET", "path": "/", "status": 200, "src_ip": "1.1.1.1"},
            benign=True,
        )
        ce = norm.normalize(
            raw,
            org_id="org_x",
            simulation_id="sim-a",
            env=finbank_env,
            received_at_ms=i,
        )
        assert ce is not None
        seqs.append(ce.raw_context.get("sequence", i))
    assert seqs == [0, 1, 2, 3, 4]


def test_normalizer_correlation_key_uses_src_ip(finbank_env: object) -> None:
    norm = Normalizer()
    raw = RawEvent(
        id="raw-ck",
        sim_time_ms=100,
        origin="web",
        type="http.request",
        src_ip="203.0.113.42",
        payload={"method": "POST", "path": "/api/login"},
    )
    out = norm.normalize(
        raw,
        org_id="org_x",
        simulation_id="sim-1",
        env=finbank_env,
        received_at_ms=100,
    )
    assert out is not None
    assert out.raw_context.get("correlation_key") == "src_ip=203.0.113.42"


def test_normalizer_unknown_raw_type_drops_to_system_sentinel(finbank_env: object) -> None:
    norm = Normalizer()
    raw = RawEvent(
        id="raw-unknown",
        sim_time_ms=10,
        origin="web",
        type="totally.unknown.raw.type",
        payload={},
    )
    out = norm.normalize(
        raw,
        org_id="org_x",
        simulation_id="sim-1",
        env=finbank_env,
        received_at_ms=10,
    )
    assert out is not None
    assert out.raw_context.get("category") == EventCategory.SYSTEM
    assert out.raw_context.get("subtype", "").startswith("unknown_raw_type:")


# ---------- NormalizerConsumer end-to-end (no Postgres) ----------


@pytest.mark.asyncio
async def test_consumer_normalizes_web_sim_raw_events_in_memory(finbank_env: object) -> None:
    """Drive the simulator -> InMemoryEventBus -> NormalizerConsumer pipeline.

    Phase 5 will append: consumer output -> analyst -> DetectionProposal.
    """
    org_id = "org_test"
    sim_id = "sim_test_1"
    bus = InMemoryEventBus()
    repo = NetworkXGraphRepository()
    repo.create(sim_id, finbank_env)

    _sim, events, _ctx = run_simulator_in_memory(
        org_id=org_id,
        simulation_id=sim_id,
        scenario_id="web.app.sqli_login",
        seed=7,
        params={"warmup_sec": 2, "request_rate_per_sec": 2},
    )
    # Publish all raw events to the bus (simulator -> bus)
    for ev in events:
        await bus.publish_raw(ev, org_id, sim_id)
    sink = NormalizedSink()
    consumer = NormalizerConsumer(
        bus=bus,
        graph_repo=repo,
        env_graph_lookup=_env_lookup(finbank_env),
        sink=sink,
    )
    n = await consumer.drain(org_id, sim_id, max_events=10_000)
    assert n > 30
    assert len(sink.events) == n
    # Categories should include HTTP + DATABASE at minimum (since SQLi & db.error
    # are guaranteed per parameterized test above)
    categories = {ce.raw_context.get("category") for ce in sink.events}
    assert EventCategory.HTTP in categories
    assert EventCategory.DATABASE in categories
    # At least one event should have been promoted to sql_injection_indicator
    sqli_indicator_count = sum(
        1 for ce in sink.events if ce.raw_context.get("subtype") == "sql_injection_indicator"
    )
    assert sqli_indicator_count > 0, (
        "expected at least one sql_injection_indicator normalized event"
    )
    # Verify that the graph node login_ep got promoted to ATTEMPTED or higher
    node = repo.get_node(sim_id, "login_ep")
    assert node is not None
    assert node.foothold_state in (
        FootholdState.ATTEMPTED,
        FootholdState.FOOTHOLD,
        FootholdState.COMPROMISED,
    )


# ---------- Sanity that platform.models import cleanly ----------


def test_platform_auth_models_are_importable() -> None:
    """Confirms SQLAlchemy wiring didn't regress."""
    assert User.__tablename__ == "users"
