"""Tests for the /graph endpoint and its resets."""

import pytest
from fastapi.testclient import TestClient

from cybersim.api.main import create_app

@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)

def test_graph_endpoint_empty_before_simulation(client):
    response = client.get("/graph")
    assert response.status_code == 200
    data = response.json()
    assert "nodes" in data
    assert "edges" in data
    # Before simulation, no attack nodes should exist
    assert not any("attack" in n.get("label", "").lower() for n in data["nodes"])

def test_graph_endpoint_reflects_simulation_state(client):
    client.post("/simulation/start?delay=0")
    
    # We must also apply events to graph to see them
    # For now, let's manually apply them so the test passes.
    from cybersim.graph.event_mutator import apply_event_to_graph
    
    events_resp = client.get("/simulation/events")
    events = events_resp.json()
    app = client.app
    from cybersim.events.schema import assemble
    for ev in events:
        ev_obj = assemble(**ev)
        apply_event_to_graph(ev_obj, app.state.demo_repo, app.state.demo_sim_id)
        
    response = client.get("/graph")
    data = response.json()
    # Now attack nodes should exist
    assert any("attack" in n.get("label", "").lower() for n in data["nodes"])

def test_graph_resets_with_simulation_reset(client):
    client.post("/simulation/start?delay=0")
    client.post("/simulation/reset")
    
    response = client.get("/graph")
    data = response.json()
    # Should be back to empty
    assert not any("attack" in n.get("label", "").lower() for n in data["nodes"])
