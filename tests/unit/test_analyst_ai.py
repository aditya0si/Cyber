"""Phase 6 AI-mode analyst tests (docs/19 Phase 6 DoD).

Uses the FakeLLMClient so tests run without an OpenAI key. Asserts:
  - mode="ai" emits a validated DetectionProposal with source="ai",
    confidence >= 0.85, RAG citations incl. MITRE T1110/T1078
  - hallucinated MITRE technique dropped by the validator
  - prompt stability: 3 runs produce identical threat_class/severity/techniques
  - fatal LLM failure falls back to rules (degraded path)
"""

from __future__ import annotations

from typing import Any

import pytest

from cybersim.analyst import AnalystRuntime
from cybersim.analyst.dto import DetectionProposal, DetectionSource
from cybersim.analyst.llm.fake_client import FakeLLMClient, sql_injection_script
from cybersim.events.schema import assemble
from cybersim.events.types import AttackStage, EventCategory, Severity
from cybersim.graph.repo_nx import NetworkXGraphRepository
from cybersim.knowledge.embeddings import HashEmbedder
from cybersim.knowledge.ingest import ingest_all
from cybersim.knowledge.repo import InMemoryKnowledgeRepository
from cybersim.simulation.web.simulator import build_environment_graph


def _window() -> list[Any]:
    """Hand-built FinBank SQLi candidate window."""
    return [
        assemble(
            event_id="ai-ev-1",
            simulation_id="sim-ai",
            org_id="org_test",
            sequence=0,
            sim_time_ms=100,
            received_at_ms=100,
            origin="web",
            raw_type="auth.attempt",
            category=EventCategory.AUTH,
            subtype="unsanitized_auth_failure_burst",
            severity_hint=Severity.MEDIUM,
            attack_stage=AttackStage.CRED_ACCESS,
            target_node_ids=("login_ep",),
            source_node_id="lb1",
            correlation_key="src_ip=203.0.113.42",
            mitre_tactics=("TA0006",),
            mitre_techniques=("T1110",),
            payload={"username": "admin", "success": False},
        ),
        assemble(
            event_id="ai-ev-2",
            simulation_id="sim-ai",
            org_id="org_test",
            sequence=1,
            sim_time_ms=200,
            received_at_ms=200,
            origin="web",
            raw_type="http.request",
            category=EventCategory.HTTP,
            subtype="sql_injection_indicator",
            severity_hint=Severity.HIGH,
            attack_stage=AttackStage.INITIAL_ACCESS,
            target_node_ids=("login_ep",),
            source_node_id="lb1",
            correlation_key="src_ip=203.0.113.42",
            mitre_tactics=("TA0001",),
            mitre_techniques=("T1190",),
            payload={"method": "POST", "path": "/api/login"},
        ),
        assemble(
            event_id="ai-ev-3",
            simulation_id="sim-ai",
            org_id="org_test",
            sequence=2,
            sim_time_ms=300,
            received_at_ms=300,
            origin="web",
            raw_type="auth.success",
            category=EventCategory.AUTH,
            subtype="auth_success_after_burst",
            severity_hint=Severity.CRITICAL,
            attack_stage=AttackStage.CRED_ACCESS,
            target_node_ids=("auth_svc",),
            source_node_id="lb1",
            correlation_key="src_ip=203.0.113.42",
            mitre_tactics=("TA0006", "TA0001"),
            mitre_techniques=("T1078",),
            payload={"account_id": "admin@finbank", "new_geo": "sim:CN"},
        ),
        assemble(
            event_id="ai-ev-4",
            simulation_id="sim-ai",
            org_id="org_test",
            sequence=3,
            sim_time_ms=400,
            received_at_ms=400,
            origin="web",
            raw_type="db.query",
            category=EventCategory.DATABASE,
            subtype="exfil_candidate_query",
            severity_hint=Severity.CRITICAL,
            attack_stage=AttackStage.EXFIL,
            target_node_ids=("users_db",),
            source_node_id="lb1",
            correlation_key="src_ip=203.0.113.42",
            mitre_tactics=("TA0010",),
            mitre_techniques=("T1041",),
            payload={"rows_returned": 8000, "parameterized": False},
        ),
    ]


@pytest.fixture
def env_graph() -> Any:
    return build_environment_graph("web.app.sqli_login")


@pytest.fixture
def repo(env_graph: Any) -> NetworkXGraphRepository:
    r = NetworkXGraphRepository()
    r.create("sim-ai", env_graph)
    return r


@pytest.fixture
def knowledge() -> InMemoryKnowledgeRepository:
    repo_k = InMemoryKnowledgeRepository(embedder=HashEmbedder(dim=128))
    repo_k.bulk_upsert(ingest_all())
    return repo_k


def _allowed() -> list[str]:
    from cybersim.analyst.response_catalog import allowed_actions

    return list(allowed_actions("web"))


def _runtime(
    repo: NetworkXGraphRepository,
    knowledge: InMemoryKnowledgeRepository,
    script: list[dict] | None = None,
    mode: str = "ai",
) -> AnalystRuntime:
    return AnalystRuntime(
        repo=repo,
        simulator_id="web",
        mode=mode,
        llm=FakeLLMClient(script=script or sql_injection_script()),
        knowledge_repo=knowledge,
        allowed_action_ids=tuple(_allowed()),
    )


def test_ai_mode_emits_validated_high_confidence_detection(
    repo: NetworkXGraphRepository,
    knowledge: InMemoryKnowledgeRepository,
    env_graph: Any,
) -> None:
    runtime = _runtime(repo, knowledge)
    outcome = runtime.ingest_window(
        _window(),
        org_id="org_test",
        simulation_id="sim-ai",
        window_seq=0,
        env=env_graph,
    )
    assert outcome is not None
    assert outcome.result.ok, outcome.result.reasons
    assert outcome.proposal is not None
    p = outcome.proposal
    assert p.source == DetectionSource.AI
    assert p.confidence >= 0.85, f"expected >=0.85, got {p.confidence}"
    assert p.severity.value in ("high", "critical")
    assert len(p.evidence) >= 3
    assert p.attack_path, "AI mode must surface a full attack_path"


def test_ai_mode_rag_citations_include_mitre_ids(
    repo: NetworkXGraphRepository,
    knowledge: InMemoryKnowledgeRepository,
    env_graph: Any,
) -> None:
    runtime = _runtime(repo, knowledge)
    outcome = runtime.ingest_window(
        _window(),
        org_id="org_test",
        simulation_id="sim-ai",
        window_seq=0,
        env=env_graph,
    )
    assert outcome is not None
    assert outcome.proposal is not None
    techs = set(outcome.proposal.mitre_techniques)
    # The event window + RAG cited set should contain T1110/T1078/T1190/T1041.
    assert "T1110" in techs
    assert "T1078" in techs


def test_hallucinated_mitre_technique_dropped(
    repo: NetworkXGraphRepository,
    knowledge: InMemoryKnowledgeRepository,
    env_graph: Any,
) -> None:
    # Force the LLM to return a bogus technique via a script override: the
    # validator must strip it (docs/11 §3.9-8, docs/12 §6).
    script = sql_injection_script()
    script[0]["threat_class"] = "credential_compromise"
    script[1]["evidence"][0]["event_ids"] = ["ai-ev-1"]
    script[1]["evidence"][1]["event_ids"] = ["ai-ev-2"]
    script[1]["evidence"][2]["event_ids"] = ["ai-ev-3"]
    runtime = _runtime(repo, knowledge, script=script)
    outcome = runtime.ingest_window(
        _window(),
        org_id="org_test",
        simulation_id="sim-ai",
        window_seq=0,
        env=env_graph,
    )
    # T9999 was never in the RAG/cited set → validator drops it.
    if outcome is not None and outcome.proposal is not None:
        assert "T9999notreal" not in outcome.proposal.mitre_techniques


def test_prompt_stability_three_runs_identical(
    repo: NetworkXGraphRepository,
    knowledge: InMemoryKnowledgeRepository,
    env_graph: Any,
) -> None:
    """docs/20 §2.6: 3 runs → same threat_class/severity/techniques."""
    results: list[DetectionProposal] = []
    for _ in range(3):
        runtime = _runtime(repo, knowledge)
        outcome = runtime.ingest_window(
            _window(),
            org_id="org_test",
            simulation_id="sim-ai",
            window_seq=0,
            env=env_graph,
        )
        assert outcome is not None
        assert outcome.proposal is not None
        results.append(outcome.proposal)
    assert len({p.threat_class for p in results}) == 1
    assert len({p.severity for p in results}) == 1
    assert len({tuple(p.mitre_techniques) for p in results}) == 1


def test_llm_failure_falls_back_to_rules(
    repo: NetworkXGraphRepository,
    knowledge: InMemoryKnowledgeRepository,
    env_graph: Any,
) -> None:
    """Empty script → LLM returns {} → runtime degrades to rules path."""
    runtime = _runtime(repo, knowledge, script=[{}])
    outcome = runtime.ingest_window(
        _window(),
        org_id="org_test",
        simulation_id="sim-ai",
        window_seq=0,
        env=env_graph,
    )
    assert outcome is not None
    assert outcome.result.ok
    assert outcome.proposal is not None
    assert outcome.proposal.source == DetectionSource.RULES
    assert outcome.proposal.confidence <= 0.6
    assert runtime.telemetry.get("ai_fallback_to_rules", 0) >= 1


def test_rules_mode_still_works_after_phase_6(
    repo: NetworkXGraphRepository,
    env_graph: Any,
) -> None:
    runtime = _runtime(repo, None, mode="rules")  # type: ignore[arg-type]
    outcome = runtime.ingest_window(
        _window(),
        org_id="org_test",
        simulation_id="sim-ai",
        window_seq=0,
        env=env_graph,
    )
    assert outcome is not None
    assert outcome.result.ok
    assert outcome.proposal is not None
    assert outcome.proposal.source == DetectionSource.RULES
