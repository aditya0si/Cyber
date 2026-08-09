"""Phase 9 mission tests (docs/14 §4, docs/19 Phase 9 DoD)."""

from __future__ import annotations

import time
from typing import Any

from fastapi.testclient import TestClient

from cybersim.api.main import create_app
from cybersim.events.schema import assemble
from cybersim.events.types import AttackStage, EventCategory, Severity
from cybersim.graph.mitre import ThreatClass
from cybersim.missions.catalog import get_mission
from cybersim.missions.scoring import score_mission

# ---------- scoring unit tests ----------


def _event(
    event_id: str, subtype: str, sim_time_ms: int, stage: AttackStage | None, benign: bool = False
) -> Any:
    return assemble(
        event_id=event_id,
        simulation_id="m1",
        org_id="o",
        sequence=0,
        sim_time_ms=sim_time_ms,
        received_at_ms=sim_time_ms,
        origin="web",
        raw_type="x",
        category=EventCategory.SYSTEM,
        subtype=subtype,
        severity_hint=Severity.INFO,
        attack_stage=stage,
        benign=benign,
        payload={},
    )


def _detection(tc: ThreatClass, severity: Severity, evidence_event_ids: tuple[str, ...]) -> Any:
    from cybersim.analyst.dto import (
        ConfidenceBand,
        DetectionProposal,
        DetectionSource,
        EvidenceItem,
        EvidenceKind,
    )

    return DetectionProposal(
        simulation_id="m1",
        org_id="o",
        window_seq=0,
        threat_class=tc,
        title=tc.value,
        severity=severity,
        confidence=0.6,
        confidence_band=ConfidenceBand.MEDIUM,
        attack_path=[],
        evidence=[
            EvidenceItem(
                label=f"ev-{eid}", kind=EvidenceKind.EVENT_BURST, weight=0.5, event_ids=(eid,)
            )
            for eid in evidence_event_ids
        ],
        rationale="test",
        recommended_actions=[],
        source=DetectionSource.RULES,
    )


def test_detection_within_achieved_when_early() -> None:
    mission = get_mission("mission.finbank_breach")
    events = [
        _event("e1", "sql_injection_indicator", 10_000, AttackStage.INITIAL_ACCESS),
        _event("e2", "exfil_candidate_query", 20_000, AttackStage.EXFIL),
    ]
    detections = [
        _detection(ThreatClass.SQL_INJECTION, Severity.HIGH, ("e1",)),
    ]
    result = score_mission(mission, events=events, detections=detections, actions=[])
    by_id = {o.objective_id: o for o in result.objectives}
    assert by_id["detect_injection"].achieved, by_id["detect_injection"].detail
    assert result.score >= 25


def test_detection_within_fails_when_late() -> None:
    mission = get_mission("mission.finbank_breach")
    events = [
        _event("e1", "sql_injection_indicator", 200_000, AttackStage.INITIAL_ACCESS),
    ]
    detections = [
        _detection(ThreatClass.SQL_INJECTION, Severity.HIGH, ("e1",)),
    ]
    result = score_mission(mission, events=events, detections=detections, actions=[])
    by_id = {o.objective_id: o for o in result.objectives}
    assert not by_id["detect_injection"].achieved
    assert "200000ms" in by_id["detect_injection"].detail


def test_stage_coverage_requires_evidence_stages() -> None:
    mission = get_mission("mission.finbank_breach")
    events = [
        _event("e1", "sql_injection_indicator", 100, AttackStage.INITIAL_ACCESS),
        _event("e2", "auth_success_after_burst", 200, AttackStage.CRED_ACCESS),
        _event("e3", "data_exfil_indicator", 300, AttackStage.EXFIL),
    ]
    detections = [
        _detection(ThreatClass.DATA_EXFILTRATION, Severity.CRITICAL, ("e1", "e2", "e3")),
    ]
    result = score_mission(mission, events=events, detections=detections, actions=[])
    by_id = {o.objective_id: o for o in result.objectives}
    assert by_id["identify_chain"].achieved, by_id["identify_chain"].detail


def test_contain_before_exfil() -> None:
    mission = get_mission("mission.finbank_breach")
    events = [
        _event("e1", "sql_injection_indicator", 100, AttackStage.INITIAL_ACCESS),
        _event("e2", "data_exfil_indicator", 50_000, AttackStage.EXFIL),
    ]
    actions = [
        {
            "execution_id": "x",
            "detection_id": "d1",
            "action_id": "block_source_ip",
            "params": {},
            "executed_by": "u",
            "result": "applied",
            "sim_time_ms": 5_000,
            "executed_at": "",
        }
    ]
    result = score_mission(mission, events=events, detections=[], actions=actions)
    by_id = {o.objective_id: o for o in result.objectives}
    assert by_id["contain_in_time"].achieved, by_id["contain_in_time"].detail


def test_contain_after_exfil_fails() -> None:
    mission = get_mission("mission.finbank_breach")
    events = [
        _event("e1", "data_exfil_indicator", 5_000, AttackStage.EXFIL),
    ]
    actions = [
        {
            "execution_id": "x",
            "detection_id": "d1",
            "action_id": "block_source_ip",
            "params": {},
            "executed_by": "u",
            "result": "applied",
            "sim_time_ms": 50_000,
            "executed_at": "",
        }
    ]
    result = score_mission(mission, events=events, detections=[], actions=actions)
    by_id = {o.objective_id: o for o in result.objectives}
    assert not by_id["contain_in_time"].achieved


def test_mission_score_caps_at_max() -> None:
    mission = get_mission("mission.finbank_breach")
    # All objectives achieved → capped at max_score.
    events = [
        _event("e1", "sql_injection_indicator", 100, AttackStage.INITIAL_ACCESS),
        _event("e2", "auth_success_after_burst", 200, AttackStage.CRED_ACCESS),
        _event("e3", "data_exfil_indicator", 300, AttackStage.EXFIL),
    ]
    detections = [
        _detection(ThreatClass.SQL_INJECTION, Severity.HIGH, ("e1",)),
        _detection(ThreatClass.DATA_EXFILTRATION, Severity.CRITICAL, ("e1", "e2", "e3")),
    ]
    actions = [
        {
            "execution_id": "x",
            "detection_id": "d1",
            "action_id": "block_source_ip",
            "params": {},
            "executed_by": "u",
            "result": "applied",
            "sim_time_ms": 50,
            "executed_at": "",
        }
    ]
    result = score_mission(mission, events=events, detections=detections, actions=actions)
    assert result.score <= result.max_score
    assert result.score == result.max_score


# ---------- API flow tests ----------


def _client() -> TestClient:
    return TestClient(create_app())


def test_mission_list_and_detail() -> None:
    from cybersim.api.main import create_app as _ca

    client = TestClient(_ca())
    tokens = client.post(
        "/v1/auth/register",
        json={
            "email": "m9@example.com",
            "password": "correct-horse-battery-staple",
        },
    ).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    missions = client.get("/v1/missions", headers=headers)
    assert missions.status_code == 200
    ids = [m["id"] for m in missions.json()]
    assert "mission.finbank_breach" in ids

    detail = client.get("/v1/missions/mission.finbank_breach", headers=headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["scenario_id"] == "web.app.sqli_login"
    assert len(body["objectives"]) == 5


def test_mission_start_and_score_flow() -> None:
    client = _client()
    tokens = client.post(
        "/v1/auth/register",
        json={
            "email": "m9b@example.com",
            "password": "correct-horse-battery-staple",
        },
    ).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    start = client.post(
        "/v1/missions/mission.finbank_breach/start",
        headers={**headers, "Idempotency-Key": "m-start-1"},
    )
    assert start.status_code == 202, start.text
    body = start.json()
    sim_id = body["simulation_id"]
    assert body["mission_id"] == "mission.finbank_breach"
    assert body["share_url"] is not None

    store = client.app.state.sim_store
    deadline = time.time() + 30
    while time.time() < deadline:
        rec = store.get(tokens["org_id"], sim_id)
        if rec is not None and rec.status in ("completed", "failed"):
            break
        time.sleep(0.1)
    assert rec is not None
    assert rec.status == "completed", f"mission sim failed: {rec.error}"
    assert rec.is_mission is True
    assert rec.mission_id == "mission.finbank_breach"

    score = client.get(f"/v1/simulations/{sim_id}/score", headers=headers)
    assert score.status_code == 200, score.text
    s = score.json()
    assert s["mission_id"] == "mission.finbank_breach"
    assert s["max_score"] == 100
    assert 0 <= s["score"] <= 100
    assert s["final"] is True
    assert len(s["objectives"]) == 5
    # With no user actions, contain_in_time etc. are unachieved — but the
    # analyst should have detected the injection chain.
    by_id = {o["objective_id"]: o for o in s["objectives"]}
    assert by_id["detect_injection"]["achieved"], s["objectives"]


# ---------- public share (judge) flow tests (docs/14 §5) ----------


def _mission_record(client: TestClient, token: str) -> Any:
    store = client.app.state.sim_store
    return store.create(
        "org-public",
        "web.app.sqli_login",
        7,
        {},
        label="mission:finbank_breach",
        mission_id="mission.finbank_breach",
        is_mission=True,
        public_share_token=token,
    )


def test_public_mission_view_and_read_routes() -> None:
    from cybersim.api.main import create_app as _ca

    client = TestClient(_ca())
    rec = _mission_record(client, "pub-tok-1")

    view = client.get("/v1/public/missions/pub-tok-1")
    assert view.status_code == 200, view.text
    body = view.json()
    assert body["simulation_id"] == rec.id
    assert body["sim_status"] == "queued"
    assert body["scenario_id"] == "web.app.sqli_login"
    assert len(body["objectives"]) == 5
    assert body["max_score"] == 100

    assert client.get("/v1/public/missions/unknown-token").status_code == 404

    events = client.get("/v1/public/simulations/pub-tok-1/events")
    assert events.status_code == 200
    assert events.json()["total"] == 0

    detections = client.get("/v1/public/simulations/pub-tok-1/detections")
    assert detections.status_code == 200
    assert detections.json() == []

    score = client.get("/v1/public/simulations/pub-tok-1/score")
    assert score.status_code == 200, score.text
    assert score.json()["mission_id"] == "mission.finbank_breach"
    assert len(score.json()["objectives"]) == 5


def test_public_execute_requires_runnable_mission() -> None:
    from cybersim.api.main import create_app as _ca

    client = TestClient(_ca())
    rec = _mission_record(client, "pub-tok-2")

    # No simulation behind the token → 404.
    r = client.post(
        "/v1/public/simulations/unknown-token/detections/det-x/execute",
        json={"action_id": "block_source_ip", "params": {}, "confirm": True},
    )
    assert r.status_code == 404

    # Seed a matching detection (execute must be backed by one), then the
    # simulation has no live simulator/context → 409.
    store = client.app.state.sim_store
    proposal = _detection(ThreatClass.SQL_INJECTION, Severity.HIGH, ("e1",))
    store.add_detection("org-public", rec.id, proposal)
    det_id = f"det-{abs(hash(proposal.simulation_id + proposal.title))}"
    r = client.post(
        f"/v1/public/simulations/pub-tok-2/detections/{det_id}/execute",
        json={"action_id": "block_source_ip", "params": {}, "confirm": True},
    )
    assert r.status_code == 409
    assert r.json()["code"] == "SIMULATION.STATUS_INVALID"


def test_public_share_token_not_required_for_other_routes() -> None:
    """Public endpoints must work without any Authorization header."""
    from cybersim.api.main import create_app as _ca

    client = TestClient(_ca())
    _mission_record(client, "pub-tok-3")
    assert (
        client.get("/v1/public/simulations/pub-tok-3/score").status_code == 200
    )
