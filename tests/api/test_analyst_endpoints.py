"""Tests for analyst API endpoints."""

import pytest
from fastapi.testclient import TestClient

from cybersim.api.main import create_app

@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)

def test_analyze_endpoint_returns_full_threat_card(client):
    client.post("/simulation/start?delay=0")
    
    resp = client.post("/analyst/analyze")
    assert resp.status_code == 200
    data = resp.json()
    
    assert "threat_card" in data
    assert "recommended_actions" in data
    assert len(data["recommended_actions"]) > 0

def test_approve_response_endpoint_full_cycle(client):
    client.post("/simulation/start?delay=0")
    client.post("/analyst/analyze")
    
    resp = client.post("/analyst/approve-response")
    assert resp.status_code == 200
    data = resp.json()
    print("APPROVE RESPONSE:", data)
    
    # Check that events were emitted
    events = client.get("/simulation/events").json()
    print("EVENTS:", events)
    assert any("isolate" in str(e).lower() or "block" in str(e).lower() for e in events)

def test_rag_sources_endpoint(client):
    client.post("/simulation/start?delay=0")
    client.post("/analyst/analyze")
    
    resp = client.get("/analyst/rag-sources")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
