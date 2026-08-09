# 20 — Testing Strategy

CyberSim AI's quality approach across levels: unit, contract, integration, end-to-end (e2e), **simulation replay determinism**, **scenario-replay golden detection**, **prompt stability**, **accessibility**, **performance**, and **security** tests. CI gating + a single command to run them all. Tests are first-class deliverables — every phase's DoD in `19` references a test command here.

> **Normative:** pytest (with `pytest-asyncio`, `pytest-xdist`), Docker Compose for integration, **Playwright** for e2e + a11y, `axe-core` via Playwright, **Lighthouse CI** for web perf, **walk (meantime) tests + contract diff** via OpenAPI. Determinism is critical: any test asserting an ordered event stream must run twice with same seed and compare.

---

## 1. Test pyramid

```
   e2e (Playwright)               5%                      [mission flow, dashboard flow, login+upgrade]
  integration (compose)            15%                     [event pipeline, graph repo persistence, multi-instance WS]
 contract (API contract diff)       5%                     [OpenAPI drift, types]
 replay/golden (sim-specific)       15%                     [determinism + scenario-replay detection asserts]
           unit                    60%                     [graphs nodes/entities/payloads/validators/scoring/...]
```

Coverage targets (lines + branches): packages `cybersim/analytics` and `cybersim/events` ≥ 85%; `cybersim/graph/`, `sybersim/analyst/`, `cybersim/knowledge/` ≥ 80%; `cybersim/simulation/*` ≥ 75%. Macro tend education covers fully forgiving low (UI-tediousness crawl).

## 2. Levels

### 2.1 Unit (pytest; no I/O)
- Domain functions (severity rubric, MITRE mapping, evidence bundle validity, scoring math, payload parsers).
- Should be pure; mock interfaces; never spin DB/Redis/LLM.
- Naming: `tests/unit/test_<module>.py::test_<scenario>`.
- Mode: wraps `pytest.mark.<component>` for fast targeted runs.

### 2.2 Integration (docker compose spin-up)
- `/tests/integration/conftest.py` brings up `postgres`, `redis`, `minio` service containers.
- Tests assert cross-component behavior: raw → canonical event persistence + graph delta + WS frame round-trip; auth refresh rotation; idempotency keys; RLS fail-closed.
- WS multi-instance test (`realtime_ha.test`) brings up TWO api containers sharing Redis; assert WS messages fan out across instances.

### 2.3 Contract (OpenAPI + typed client)
- After API starts, `GET /v1/openapi.json` must equal `apps/web/src/lib/api/schema.lock.json` (committed). Diff occurs in CI: any breaking change requires lockfile bump + ICU check-in note.
- Also: `openapi-typescript` regenerates schema.ts; `tsc --noEmit` on the web app must pass with new types — proves no client-server type drift.

### 2.4 Replay determinism (`tests/sim_determinism/`)
For each simulator + scenario combo, run twice with same `seed`, same `params`, same `scenario_id`. Compare:
- Canonical events: number, ordered `sequence`, `subtype`, `severity_hint`, `attack_stage`, `target_node_ids`, MITRE tags — equal (excluding `received_at_ms` and the random half of `event_id`).
- Graph snapshots at the same `seq` — equal.
- Detection outputs (rule-based mode for stability): equal.

Test failure ⇒ follow-up: find nondeterministic RNG/time/uuid misuse in code (the `pre-commit` regex lint plus this test catch most).

### 2.5 Scenario-replay golden detection (`tests/scenario_golden/`)
The **judgment** test: assert the **expected detection** from each scenario is produced within time and severity (`06` scenario `expected_detections`). Runs against **rule-fallback mode** (deterministic, no LLM flakiness) and optionally **AI mode** (asserted *proposal* matches expected threat_class with confidence ≥ 0.75; 3-run mean).

- Free run under rule-fallback for stability: 100% pass required (CI).
- AI-mode runs gated by daily/`nightly` job (not PR-blocking, but tracked).

### 2.6 Prompt stability (`tests/prompt_stability/`)
Run AI analyst 3× per scenario with same window; assert: same `threat_class`, `severity`, set-of-MTTE techniques identical, confidence band same; rationale wording may vary but evidence count and weight within 5%. Records `prompt_hash` so drift (template change) is visible.

### 2.7 e2e (Playwright)
Critical paths only, run nightly + smoke on PR (short):
- `auth.spec.ts` — register → login → home page.
- `scenario_run.spec.ts` — pick scenario → start → see event stream → see detection → execute response → graph reflects containment.
- `mission.spec.ts` — open mission share link (no signup) → execute response → see score.
- `billing.spec.ts` (staging only) — checkout + portal.

### 2.8 Accessibility (`axe-core` per Page)
- Marked via Playwright `@axe-core/playwright`.
- Asserts no `critical` violations on **every primary page** (login, scenario picker, dashboard, mission).
- Color contrast computed separately (walks the rendered Token CSS) — ensure contrast on `--cs-text-primary` against each card/panel background; fail build on regression.
- Keyboard-only reach for each route (tab-stop audit, dynamic focus paths).

### 2.9 Performance (Lighthouse CI)
- LHCI custom config (`apps/web/lighthouserc.json`): two test URLs (marketing `/` and dashboard `/sim demo` sim id) — using seeded local sim to keep runtime short.
- Gates: Marketing perf ≥ 90; dashboard ≥ 85; failure stops PR.
- Trends recorded; not blocking for fixes (warnings).

### 2.10 Security/CI scans
- `gitleaks` on PR (commits + diff).
- `pip-audit`, `npm audit`, `pip-licenses`/`license-checker` ("no GPL/AGPL" gate).
- Image scans: `trivy image` for built containers; fail on `CRITICAL`.
- RLS tests (`tests/integration/security/test_rls.py`): simulation_id rows from other orgs are returned only if `app.current_org_id` matches — otherwise empty; fail-closed if unset.
- SAST baseline via `bandit` (Python) + ` tslint-security` minimal flags (we keep TS ESLint core for now).

## 3. Fixtures & data

- **No network** in unit/integration tests. Knowledge ingest tests use vendored fixtures (`tests/fixtures/knowledge/mitre_sample.json`, `owasp_sample.md`, `cve_sample.json`) — not live fetches.
- LLM `fake` provider for unit (`cybersim.analyst.llm.FakeLLMClient`) — deterministic; can be programmed per test (`next_response(payload)`);
- Real LLM calls only run in nightly `AI matrix` job vs `OPENAI_API_KEY` provided (skipped otherwise with explicit `pytest.skip`).
- Simulation scena seed files in `tests fixtures/scenarios/` (subset of the catalog) for fast tests; full catalog run in integration.
- Graph fixtures: tiny `EnvironmentGraph`maker (`tests.fixtures.graphs.attacker_at_lb_toward_db` etc.).

## 4. Determinism & reproducibility hatchets
- `pytest --randomly-seed=...` for fuzzing internal order; nightly determinism mode: `pytest --replay-verify` re-runs every determinism + golden golden under two RNG seeds.
- A **trial run** of an analyst hallucination guard: feed invalid `expected_detections` scenario; expect validator to drop spurious MITRE and reduce confidence — proves anti-hallucination rule.

## 5. Single-command verification

`Makefile`/`tasks.py` target the same name:
```
make verify         # unit + contract + integration (compose-up) + replay-determinism + lints + types
make verify-fast    # unit + lint + types (no compose)
make verify-nightly # adds replay golden AI mode + prompt-stability + Lighthouse a11y + dependency audit
make replay <sim>   # reconstruct run from Postgres + compare to stored baseline
```

## 6. Per-phase test gates (`19` DoDs)
| Phase | Test surface invoked |
|-------|------------------------|
| 0 | tooling smoke + pre-commit |
| 1 | unit/events + parallel |
| 2 | `tests/sim_determinism/web_sqli` |
| 3 | integration graph + RLS + replay |
| 4 | contract diff +
 api smoke + WS multi-instance |
| 5 | `mission.mode_rules` e2e stub + scenario-golden (rules mode) |
| 6 | prompt-stability + scenario-golden (AI mode, nightly) + knowledge recall@5 |
| 7 | sim_determinism for each of api/network/supplychain + scenario-golden |
| 8 | Lighthouse gate + a11y axe + keyboard e2e + dash flow |
| 9 | mission e2e + share link rate limit test |
| 10 | billing webhooks idempotency + entitlement propagation |
| 11 | OTel trace export + SLO detectors |
| 12 | final marketing perf + e2e smoke |

## 7. Self-questioning & decisions (testing)

| Decision | Chosen | Rejected | Why |
|----------|--------|----------|-----|
| Dual-mode tests: rules-mode block-on-PR + AI-mode nightly-only | Yes | both required | Anti-flaky CI — rulesy deterministic; AI used nightly since nondeterministic (`20` §2.5/§2.6) |
| Determinism assert: byte-identical minus known-excluded fields | Yes | approximate | Strict catches RNG/time leakage (`04` §3 rule #5) |
| Replay test from Postgres-only records | Yes | requires raw stream side-by-side | We have both `events` table + snapshots; the test re-runs graph reconstruction so we know replay works without streams |
| Lighthouse as hard gate (≥90/85) | Yes | informational only | Performance is a product-quality bar (`01` §7) |
| axe on every primary page (not 1) | Yes | spot-check only | A11y is a product requirement (`02` §7) |
| Contract test = lockfile diff | Yes | none | Frontend configures typed client from OpenAPI; drift = bug |
| Multi-instance WS test asserts Redis fan-out | Yes | single instance only | Validates the decision that fan-out is decoupled from instance identity (`03` §8.2) |
| nightly runs on real LLM (gated by secret presence) | Yes | only fake | Catches real provider drift; doesn't block main |
| no-network unit/integration tests | Yes | allowed calls | reproduction + speed (`12` §3.1) |

---

End of `20-testing-strategy.md`. Next: `21-ai-agent-build-instructions.md`.
