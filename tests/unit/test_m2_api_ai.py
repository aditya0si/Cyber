"""M2 milestone: AI-mode detection through the full API pipeline (docs/19 Phase 6).

Proves the API's background simulation task emits an AI-sourced Detection
when the app is created in `analyst_mode="ai"` with a fake LLM + seeded
knowledge base — no OpenAI key required.
"""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from cybersim.analyst.llm.fake_client import FakeLLMClient, sql_injection_script
from cybersim.analyst.response_catalog import allowed_actions
from cybersim.api.main import create_app
from cybersim.knowledge.embeddings import HashEmbedder
from cybersim.knowledge.ingest import ingest_all
from cybersim.knowledge.repo import InMemoryKnowledgeRepository


def _make_app() -> TestClient:
    knowledge = InMemoryKnowledgeRepository(embedder=HashEmbedder(dim=128))
    knowledge.bulk_upsert(ingest_all())
    app = create_app(analyst_mode="ai")
    app.state.knowledge_repo = knowledge
    # Wire the runtime-level AI deps used by the background task.
    app.state.analyst_llm = FakeLLMClient(script=sql_injection_script())
    app.state.analyst_allowed = tuple(allowed_actions("web"))
    return TestClient(app)


def _register(client: TestClient) -> dict:
    resp = client.post(
        "/v1/auth/register",
        json={
            "email": "m2@example.com",
            "password": "correct-horse-battery-staple",
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_m2_ai_detection_via_api() -> None:
    client = _make_app()
    tokens = _register(client)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    resp = client.post(
        "/v1/simulations",
        json={
            "scenario_id": "web.app.sqli_login",
            "params": {"warmup_sec": 1, "request_rate_per_sec": 4},
        },
        headers={**headers, "Idempotency-Key": "m2-sim"},
    )
    assert resp.status_code == 202, resp.text
    sim_id = resp.json()["simulation_id"]

    store = client.app.state.sim_store
    deadline = time.time() + 30
    while time.time() < deadline:
        rec = store.get(tokens["org_id"], sim_id)
        if rec is not None and rec.status in ("completed", "failed"):
            break
        time.sleep(0.1)
    assert rec is not None
    assert rec.status == "completed", f"sim failed: {rec.error}"
    assert len(rec.detections) >= 1

    det = client.get(f"/v1/simulations/{sim_id}/detections", headers=headers).json()
    assert len(det) >= 1
    strongest = max(
        det,
        key=lambda d: {
            "info": 0,
            "low": 1,
            "medium": 2,
            "high": 3,
            "critical": 4,
        }[d["severity"]],
    )
    assert strongest["source"] == "ai", f"expected AI-sourced detection, got {strongest['source']}"
    assert strongest["confidence"] >= 0.85
    assert strongest["attack_path"], "AI detection must carry an attack_path"
    assert strongest["evidence"], "AI detection must carry evidence"

    # Knowledge search endpoint returns seeded entries.
    search = client.get("/v1/knowledge/search?q=brute+force", headers=headers)
    assert search.status_code == 200
    assert len(search.json()["hits"]) >= 1


def test_knowledge_seed_via_cli() -> None:
    """seed_knowledge CLI embeds fixtures without error."""
    from cybersim.knowledge.seed_knowledge import main

    rc = main(["--dry-run"])
    assert rc == 0
