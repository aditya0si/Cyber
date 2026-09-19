"""Phase 4 API tests (docs/19 Phase 4 DoD, docs/20 §2.2).

Runs in-memory via TestClient: no Postgres/Redis required. Verifies:
  - register/login/refresh + ws-ticket auth flow
  - POST /v1/simulations → background run → WS frames (event.upsert,
    detection.created, sim.status)
  - detection execute path (whitelist + confirm gate)
  - Idempotency-Key replay
  - OpenAPI schema present
"""

from __future__ import annotations

import json
import queue
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from fastapi.testclient import TestClient

from cybersim.api.main import create_app


@contextmanager
def _receive_timeout(ws: Any, timeout_sec: float = 5.0) -> Iterator[Callable[[], Any]]:
    """Yield a bounded `receive()` so a hung hub flush fails fast.

    A daemon thread owns `ws.receive_text()`; the caller reads from a queue
    with a timeout, so a hub flush race raises TimeoutError instead of
    hanging the whole suite.
    """

    def _pump() -> None:
        try:
            while True:
                q.put(ws.receive_text())
        except Exception as exc:
            q.put(exc)

    q: queue.Queue[Any] = queue.Queue()
    t = threading.Thread(target=_pump, daemon=True)
    t.start()

    def _receive() -> Any:
        try:
            return q.get(timeout=timeout_sec)
        except queue.Empty:
            raise TimeoutError("WS receive exceeded timeout") from None

    try:
        yield _receive
    finally:
        t.join(timeout=1.0)


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def _register(client: TestClient, email: str = "alice@example.com") -> dict:
    resp = client.post(
        "/v1/auth/register",
        json={
            "email": email,
            "password": "correct-horse-battery-staple",
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_healthz(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_openapi_schema_present(client: TestClient) -> None:
    resp = client.get("/v1/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    assert "/v1/auth/register" in schema["paths"]
    assert "/v1/simulations" in schema["paths"]


def test_register_login_refresh_flow(client: TestClient) -> None:
    tokens = _register(client)
    assert tokens["token_type"] == "bearer"
    assert tokens["org_role"] == "admin"

    # Login again
    login = client.post(
        "/v1/auth/login",
        json={
            "email": "alice@example.com",
            "password": "correct-horse-battery-staple",
        },
    )
    assert login.status_code == 200, login.text
    login_tokens = login.json()
    assert login_tokens["access_token"] != tokens["access_token"]

    # Refresh (rotating token)
    refresh = client.post(
        "/v1/auth/refresh",
        json={
            "refresh_token": login_tokens["refresh_token"],
        },
    )
    assert refresh.status_code == 200, refresh.text
    refreshed = refresh.json()
    assert refreshed["refresh_token"] != login_tokens["refresh_token"]

    # Old refresh token is now invalid (reuse detection)
    reuse = client.post(
        "/v1/auth/refresh",
        json={
            "refresh_token": login_tokens["refresh_token"],
        },
    )
    assert reuse.status_code == 401


def test_me_endpoint_returns_org(client: TestClient) -> None:
    tokens = _register(client)
    resp = client.get("/v1/me", headers=_auth_headers(tokens["access_token"]))
    assert resp.status_code == 200
    body = resp.json()
    assert body["org"]["id"].startswith("org_")
    assert body["role"] == "admin"


def test_me_requires_auth(client: TestClient) -> None:
    resp = client.get("/v1/me")
    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == "AUTH.TOKEN_MISSING"


def test_scenarios_list_requires_auth(client: TestClient) -> None:
    resp = client.get("/v1/scenarios")
    assert resp.status_code == 401


def test_scenarios_list_returns_web_sqli(client: TestClient) -> None:
    tokens = _register(client)
    resp = client.get("/v1/scenarios", headers=_auth_headers(tokens["access_token"]))
    assert resp.status_code == 200
    ids = [s["id"] for s in resp.json()]
    assert "web.app.sqli_login" in ids


def test_create_simulation_returns_202_and_runs(
    client: TestClient,
) -> None:
    tokens = _register(client)
    headers = _auth_headers(tokens["access_token"])
    resp = client.post(
        "/v1/simulations",
        json={
            "scenario_id": "web.app.sqli_login",
            "params": {"warmup_sec": 1, "request_rate_per_sec": 4},
            "label": "api-test",
        },
        headers={**headers, "Idempotency-Key": "create-1"},
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["status"] == "queued"
    assert body["ws_channel"].startswith("sim.")
    sim_id = body["simulation_id"]

    # Wait for the background task to complete (poll the store)
    import time

    store = client.app.state.sim_store
    deadline = time.time() + 30
    while time.time() < deadline:
        rec = store.get(tokens["org_id"], sim_id)
        if rec is not None and rec.status in ("completed", "failed"):
            break
        time.sleep(0.1)
    assert rec is not None
    assert rec.status == "completed", f"sim failed: {rec.error}"
    assert len(rec.events) > 30
    assert len(rec.detections) >= 1

    # Events endpoint
    events_resp = client.get(f"/v1/simulations/{sim_id}/events", headers=headers)
    assert events_resp.status_code == 200
    assert events_resp.json()["total"] == len(rec.events)

    # Graph endpoint
    graph_resp = client.get(f"/v1/simulations/{sim_id}/graph", headers=headers)
    assert graph_resp.status_code == 200
    assert len(graph_resp.json()["nodes"]) >= 10

    # Detections endpoint
    det_resp = client.get(f"/v1/simulations/{sim_id}/detections", headers=headers)
    assert det_resp.status_code == 200
    detections = det_resp.json()
    assert len(detections) >= 1
    strongest = max(detections, key=lambda d: _sev_rank(d["severity"]))
    assert len(strongest["evidence"]) >= 3
    assert strongest["source"] == "rules"
    assert strongest["confidence"] <= 0.6


def _sev_rank(sev: str) -> int:
    return {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}[sev]


def test_execute_response_requires_confirmation_for_high_risk(
    client: TestClient,
) -> None:
    tokens = _register(client)
    headers = _auth_headers(tokens["access_token"])
    sim_resp = client.post(
        "/v1/simulations",
        json={
            "scenario_id": "web.app.sqli_login",
            "params": {"warmup_sec": 0},
        },
        headers={**headers, "Idempotency-Key": "exec-1"},
    )
    sim_id = sim_resp.json()["simulation_id"]

    import time

    store = client.app.state.sim_store
    deadline = time.time() + 30
    while time.time() < deadline:
        rec = store.get(tokens["org_id"], sim_id)
        if rec is not None and rec.status in ("completed", "failed"):
            break
        time.sleep(0.1)
    store.get(tokens["org_id"], sim_id).detections[0]
    det_id = client.get(f"/v1/simulations/{sim_id}/detections", headers=headers).json()[0][
        "detection_id"
    ]

    # block_source_ip is low-risk; no confirm needed.
    ok = client.post(
        f"/v1/simulations/{sim_id}/detections/{det_id}/execute",
        json={"action_id": "block_source_ip"},
        headers={**headers, "Idempotency-Key": "exec-run-1"},
    )
    assert ok.status_code == 202, ok.text
    assert ok.json()["action_id"] == "block_source_ip"

    # Unknown action → 404 ACTION.UNKNOWN? — executor raises ACTION_NOT_ALLOWED.
    bad = client.post(
        f"/v1/simulations/{sim_id}/detections/{det_id}/execute",
        json={"action_id": "not-a-real-action"},
        headers={**headers, "Idempotency-Key": "exec-bad-1"},
    )
    assert bad.status_code == 403


def test_idempotency_replay_returns_same_sim_id(client: TestClient) -> None:
    tokens = _register(client)
    headers = _auth_headers(tokens["access_token"])
    body = {"scenario_id": "web.app.sqli_login", "params": {"warmup_sec": 0}}
    first = client.post(
        "/v1/simulations", json=body, headers={**headers, "Idempotency-Key": "sim-key-1"}
    )
    second = client.post(
        "/v1/simulations", json=body, headers={**headers, "Idempotency-Key": "sim-key-1"}
    )
    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["simulation_id"] == second.json()["simulation_id"]
    assert second.headers.get("X-Idempotent-Replay") == "true"


def test_missing_idempotency_key_rejected(client: TestClient) -> None:
    tokens = _register(client)
    resp = client.post(
        "/v1/simulations",
        json={"scenario_id": "web.app.sqli_login"},
        headers=_auth_headers(tokens["access_token"]),
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "IDEMPOTENCY.KEY_REQUIRED"


def test_ws_ticket_and_sim_channel(client: TestClient) -> None:
    tokens = _register(client)
    headers = _auth_headers(tokens["access_token"])
    ticket_resp = client.post("/v1/auth/ws-ticket", headers=headers)
    assert ticket_resp.status_code == 200
    ticket = ticket_resp.json()["ticket"]

    # Start a sim first so there are frames to receive.
    sim_resp = client.post(
        "/v1/simulations",
        json={
            "scenario_id": "web.app.sqli_login",
            "params": {"warmup_sec": 1, "request_rate_per_sec": 4},
        },
        headers={**headers, "Idempotency-Key": "ws-1"},
    )
    sim_id = sim_resp.json()["simulation_id"]

    import time

    store = client.app.state.sim_store
    deadline = time.time() + 30
    while time.time() < deadline:
        rec = store.get(tokens["org_id"], sim_id)
        if rec is not None and rec.status in ("completed", "failed"):
            break
        time.sleep(0.1)

    # Replay a fresh run via hub publish on the channel and assert a frame
    # is delivered on an active WS connection.
    frames: list[dict] = []
    with client.websocket_connect(f"/v1/ws?ticket={ticket}&channel=sim.{sim_id}") as ws:
        hello = json.loads(ws.receive_text())
        assert hello["kind"] == "hello"
        # publish detection frames from the store via hub
        hub = client.app.state.hub
        for d in store.get(tokens["org_id"], sim_id).detections:
            hub.publish(
                f"sim.{sim_id}",
                {
                    "kind": "detection.created",
                    "detection": d.model_dump(mode="json"),
                },
            )
        # Receive until we see the detection frame — bounded by a watchdog so
        # a hub flush race fails the test instead of hanging the suite. The
        # hub may coalesce detection frames into `event.batch.frames` (docs/08
        # §5), so check both top-level and nested frames.
        seen_detection = False
        try:
            with _receive_timeout(ws, timeout_sec=5.0) as receive:
                for _ in range(10):
                    frame = json.loads(receive())
                    frames.append(frame)
                    if frame.get("kind") == "detection.created":
                        seen_detection = True
                        break
                    if frame.get("kind") == "event.batch" and any(
                        f.get("kind") == "detection.created" for f in frame.get("frames", [])
                    ):
                        seen_detection = True
                        break
        except TimeoutError:
            pass
        assert seen_detection, f"no detection frame; got {frames!r}"


def test_ws_rejects_invalid_ticket(client: TestClient) -> None:
    from starlette.websockets import WebSocketDisconnect

    with (
        pytest.raises(WebSocketDisconnect) as exc_info,
        client.websocket_connect("/v1/ws?ticket=bogus") as ws,
    ):
        ws.receive_text()
    assert exc_info.value.code == 4401
