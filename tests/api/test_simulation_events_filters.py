"""Regression tests for the `GET /v1/simulations/{sim_id}/events` filters.

Before the fix these filters read `category` / `severity_hint` / `benign` off
`CanonicalEvent`, which only carries the 8 contract fields (docs/00 §5), so any
filtered request raised AttributeError -> HTTP 500. `category` and `benign` are
carried in `raw_context`; `severity` is a contract field.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from cybersim.api.main import create_app

SCENARIO_ID = "api.brute_force"


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def _register(client: TestClient, email: str = "events-filter@example.com") -> dict:
    resp = client.post(
        "/v1/auth/register",
        json={"email": email, "password": "correct-horse-battery-staple"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _completed_sim(client: TestClient, tokens: dict, idempotency_key: str) -> tuple[str, dict]:
    """Start a simulation and wait for the background run to finish."""
    headers = {
        "Authorization": f"Bearer {tokens['access_token']}",
        "Idempotency-Key": idempotency_key,
    }
    resp = client.post(
        "/v1/simulations",
        json={"scenario_id": SCENARIO_ID, "seed": 7, "params": {}},
        headers=headers,
    )
    assert resp.status_code == 202, resp.text
    sim_id = resp.json()["simulation_id"]

    store = client.app.state.sim_store
    deadline = time.time() + 30
    rec = None
    while time.time() < deadline:
        rec = store.get(tokens["org_id"], sim_id)
        if rec is not None and rec.status in ("completed", "failed"):
            break
        time.sleep(0.1)
    assert rec is not None
    assert rec.status == "completed", f"sim failed: {rec.error}"
    return sim_id, {"Authorization": f"Bearer {tokens['access_token']}"}


def _events(client: TestClient, sim_id: str, headers: dict, **params: object) -> dict:
    resp = client.get(f"/v1/simulations/{sim_id}/events", headers=headers, params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_events_category_filter_returns_only_that_category(client: TestClient) -> None:
    tokens = _register(client)
    sim_id, headers = _completed_sim(client, tokens, "events-filter-1")

    unfiltered = _events(client, sim_id, headers)
    assert unfiltered["total"] > 0
    assert unfiltered["items"], "expected the scenario to emit events"

    categories = {e["raw_context"]["category"] for e in unfiltered["items"]}
    category = sorted(categories)[0]

    filtered = _events(client, sim_id, headers, category=category)
    assert filtered["items"], f"no events returned for category {category!r}"
    assert all(e["raw_context"]["category"] == category for e in filtered["items"])
    # total always reports the unfiltered count of the simulation.
    assert filtered["total"] == unfiltered["total"]


def test_events_severity_filter_returns_only_that_severity(client: TestClient) -> None:
    tokens = _register(client)
    sim_id, headers = _completed_sim(client, tokens, "events-filter-2")

    unfiltered = _events(client, sim_id, headers)
    severities = {e["severity"] for e in unfiltered["items"]}
    severity = sorted(severities)[0]

    filtered = _events(client, sim_id, headers, severity=severity)
    assert filtered["items"], f"no events returned for severity {severity!r}"
    assert all(e["severity"] == severity for e in filtered["items"])


def test_events_benign_filter_matches_raw_context_flag(client: TestClient) -> None:
    tokens = _register(client)
    sim_id, headers = _completed_sim(client, tokens, "events-filter-3")

    unfiltered = _events(client, sim_id, headers)
    benign_true = [e for e in unfiltered["items"] if e["raw_context"].get("benign")]
    benign_false = [e for e in unfiltered["items"] if not e["raw_context"].get("benign")]
    assert benign_true, "scenario should emit benign events"
    assert benign_false, "scenario should emit non-benign events"

    only_true = _events(client, sim_id, headers, benign="true")
    only_false = _events(client, sim_id, headers, benign="false")
    assert len(only_true["items"]) == len(benign_true)
    assert len(only_false["items"]) == len(benign_false)
    assert all(e["raw_context"].get("benign") for e in only_true["items"])
    assert all(not e["raw_context"].get("benign") for e in only_false["items"])


def test_events_unknown_filter_value_returns_empty_page(client: TestClient) -> None:
    tokens = _register(client)
    sim_id, headers = _completed_sim(client, tokens, "events-filter-4")

    filtered = _events(client, sim_id, headers, category="NOT_A_CATEGORY")
    assert filtered["items"] == []
    # The cursor advances over the scanned page even when nothing matches,
    # otherwise a filtered request would loop on the same page forever.
    assert filtered["cursor"] > 0
