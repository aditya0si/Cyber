import pytest
from fastapi.testclient import TestClient
from cybersim.api.main import create_app
from cybersim.events.schema import CanonicalEvent

@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)

def test_start_returns_200(client):
    response = client.post("/simulation/start?delay=0")
    assert response.status_code == 200
    assert response.json()["status"] == "started"

def test_events_empty_before_start(client):
    client.post("/simulation/reset")
    response = client.get("/simulation/events")
    assert response.status_code == 200
    assert response.json() == []

def test_events_populated_after_start(client):
    client.post("/simulation/reset")
    client.post("/simulation/start?delay=0")
    response = client.get("/simulation/events")
    assert response.status_code == 200
    events = response.json()
    assert len(events) > 0
    assert events[-1]["event_type"] == "DB_ACCESS"

def test_reset_then_restart_is_clean(client):
    client.post("/simulation/start?delay=0")
    ev1 = client.get("/simulation/events").json()
    assert len(ev1) > 0

    client.post("/simulation/reset")
    ev_empty = client.get("/simulation/events").json()
    assert ev_empty == []

    client.post("/simulation/start?delay=0")
    ev2 = client.get("/simulation/events").json()
    assert len(ev2) > 0
    assert ev1[0]["event_id"] != ev2[0]["event_id"]

def test_events_are_json_serializable_and_schema_valid(client):
    client.post("/simulation/reset")
    client.post("/simulation/start?delay=0")
    response = client.get("/simulation/events")
    events = response.json()
    for e in events:
        CanonicalEvent(**e)

def test_double_start_without_reset(client):
    client.post("/simulation/reset")
    client.post("/simulation/start?delay=0")
    client.post("/simulation/start?delay=0")
    # the second start will implicitly reset inside the state machine since start() calls reset()
    events = client.get("/simulation/events").json()
    # It should have exactly the stages of one run (3 fails, 1 success, 1 priv esc, 1 db access) = 6 events
    assert len(events) == 6
