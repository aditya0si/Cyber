"""Tests for the human approval gate (docs/03 Checkpoint B)."""

import pytest
from fastapi.testclient import TestClient

from cybersim.api.main import create_app


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def test_response_does_not_execute_without_approval_call(client):
    client.post("/simulation/start?delay=0")

    # Send to analyze
    resp = client.post("/analyst/analyze")
    assert resp.status_code == 200

    # Check graph
    graph = client.get("/graph").json()
    # Find user node - should still be compromised, not isolated
    user_node = next((n for n in graph["nodes"] if n["id"] == "user_admin_service_account"), None)
    assert user_node is not None, "scenario no longer produces user_admin_service_account"
    assert user_node.get("attrs", {}).get("status") != "isolated"


def test_approve_response_triggers_simulation_action(client):
    client.post("/simulation/start?delay=0")
    client.post("/analyst/analyze")

    resp = client.post("/analyst/approve-response")
    assert resp.status_code == 200

    graph = client.get("/graph").json()
    user_node = next((n for n in graph["nodes"] if n["id"] == "user_admin_service_account"), None)
    assert user_node is not None, "scenario no longer produces user_admin_service_account"
    # After approval, it should be isolated
    assert user_node.get("attrs", {}).get("status") == "isolated"


def test_environment_updated_reflects_containment(client):
    client.post("/simulation/start?delay=0")
    client.post("/analyst/analyze")
    client.post("/analyst/approve-response")

    events = client.get("/simulation/events").json()
    assert any(e["event_type"] == "CONTAINMENT_EXECUTED" for e in events)
