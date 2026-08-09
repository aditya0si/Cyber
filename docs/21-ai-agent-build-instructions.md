# 21 — AI-Agent Build Instructions

This is the executable counterpart to the rest of this suite: task-by-task instructions an AI coding agent follows to build CyberSim AI. It assumes the agent has read `00-README.md`, `03-system-architecture.md`, and the doc relevant to the current phase (`19`). It uses the same path conventions as `13`, `09`, `08`, `11`.

> **Operating mode for the agent:** always read the named doc before the named task; implement verbatim names + interfaces; do not rename; if a doc says "decide later," use a documented stub; run the verification command at the end of each task; commit only when the user explicitly requests; **never** add comments unless asked in spec; **never** invent library APIs not already documented in `04`.

---

## A. Naming & path conventions (normative — re-cap)

- Python root `cybersim/`, JS root `apps/web/`. Configuration under `infra/`.
- Modules under `cybersim/<area>/` map 1:1 to docs:
  | Doc | Areas created |
  |-----|---------------|
  | `05` | `cybersim/graph/`, `cybersim/graph/mitre.py` |
  | `06` | `cybersim/simulation/`, `cybersim/simulation/{web,api,network,supply}/`, `cybersim/simulation/catalog/` |
  | `07` | `cybersim/events/`, `cybersim/events/{schema,payloads,bus,normalizer,mapping}` |
  | `08` | `cybersim/api/`, `cybersim/realtime/` |
  | `09` | `cybersim/infra/db/`, Alembic migrations |
  | `10` | `cybersim/graph/repo*.py`, `cybersim/graph/cache.py` |
  | `11` | `cybersim/analyst/`, `cybersim/analyst/{nodes,prompts,llm}` |
  | `12` | `cybersim/knowledge/` |
  | `14` | `cybersim/missions/` |
  | `15` | `cybersim/platform/auth`, `platform/tenants` |
  | `16` | `cybersim/platform/billing` |
  | `17` | `infra/terraform/`, `infra/docker/` |

- **File checklist:** at the end of each task, list what was created/modified so subsequent tasks know the surface.

---

## B. Pre-flight (do once)

1. Read: `00`, `01`, `02`, `03`, `04` end-to-end.
2. Ensure `uv`, `pnpm`, `docker`, `docker compose`, `terraform` are installed.
3. Create `cybersim/` and `apps/web/` directories; initialize `pyproject` per Phase 0 (`19`).
4. Set environment default: `.env.example` documents every name listed in `17` §6.

---

## C. Tasks (ordered same as `19` phases)

### Task 0.1 — Repo skeleton & tooling
**Inputs:** `19` Phase 0, `04` §3.
**Do:**
- Create `pyproject.toml` with: `python_requires=">=3.11"`, deps (`fastapi`, `pydantic>=2.7`, `sqlalchemy>=2`, `asyncpg`, `alembic`, `celery`, `redis>=5`, `networkx`, `langgraph`, `openai`, `pgvector`, `httpx`, `structlog`, `opentelemetry-*`, `argon2-cffi`, `pyjwt`, `cryptography`, `webauthn`, `stripe`, `jinja2`); dev deps (`pytest`, `pytest-asyncio`, `pytest-xdist`, `ruff`, `mypy`, `pre-commit`, `httpx`, `pytest-playwright`, `faker`).
- `apps/web/package.json` with: `next@14.2`, `react`, `typescript@5.4`, `tailwindcss@4`, `@radix-ui/*`, `lucide-react`, `@tanstack/react-query`, `zustand`, `openapi-typescript`, `zod`, `react-hook-form`, `shiki`, `axe-core/playwright`, `lighthouse`.
- `ruff.toml` (line-length 100, `I` + `UP` + `B` + `SIM`); `mypy.ini` (`strict=true`, no implicit re-export).
- `.pre-commit-config.yaml` (ruff + ruff-format + mypy + gitleaks + eslint/prettier + a custom hook that forbids `random.*`/`time.time()`/`uuid.uuid4()` outside `cybersim/simulation/core/` and `cybersim/infra/uuidv7`.
- `docker-compose.yml` per `17` §1.
- `.github/workflows/ci.yml` per `17` §5.
- `Makefile` targets: `verify`, `verify-fast`, `verify-nightly`, `replay`, `seed`, `db-up`, `db-upgrade`.
**Verify:** `make verify-fast`.

### Task 1.1 — Event & graph type system
**Inputs:** `07`, `05`, `04` §2.5.
**Do:**
- `cybersim/events/schema.py` (Pydantic models verbatim per `07` §1).
- `cybersim/events/payloads/{http,db,auth,api,net,host,package,process,system}.py`.
- `cybersim/events/mapping.py` (the dispatch table `07` §3).
- `cybersim/graph/types.py` (`GraphNode`, `GraphEdge`, `OverlayNode`, `AttackPath`, enums `NodeKind`, `EdgeType`, `FootholdState`). Use `06` taxonomy.
- `cybersim/graph/mitre.py` (the Mapping table `05` §4.2; expose `threat_class_to_techniques(ThreatClass)`).
**Verify:** `pytest cybersim/events cybersim/graph -v`.

### Task 1.2 — Simulator framework & RNG + EventBus interface
**Inputs:** `06` §1, `07` §4, `04` §2.9.
**Do:**
- `cybersim/simulation/core/rng.py` — `SeededRNG` (`random.Random` based) producing int/choice/sample; deterministic.
- `cybersim/simulation/core/clock.py` — `SimClock` with `now_ms()`, `sleep_ms()` (cooperative only — sim driver yields).
- `cybersim/simulation/core/context.py` — `SimContext` dataclass.
- `cybersim/simulation/base.py` — `Simulator` Protocol per `06` §1.
- `cybersim/events/bus.py` — `EventBus` Protocol with `publish_raw`, `subscribe_raw`, `publish_canonical`, `subscribe_canonical`; impl stubs for in-process.
- `cybersim/events/bus_redis.py` — Redis Streams impl with consumer groups + XACK + XADD; idempotency docs.
- `cybersim/infra/uuidv7.py` — deterministic v7 minting from `clock.now_ms() + rng.random_bytes(74bit)`; verify ordering.
**Verify:** `pytest cybersim/events/bus cybersim/simulation/core -v` — round-trip + ordered delivery.

### Task 2.1 — Catalog loader + env YAML schema
**Inputs:** `06` §2.
**Do:**
- `cybersim/simulation/catalog/loader.py` — load `*.yaml`, validate with Pydantic `ScenarioSpec`, `EnvironmentTemplate`; index by id; reject unknown simulators.
- Catalog files: at minimum `web.app.sqli_login.yaml`, `web.finbank.env.yaml`.
- `cybersim/simulation/catalog/index.py` — `list_scenarios(simulator=None, category=None, difficulty=None)`, `get(scenario_id)`, `env_template(scenario_id)`.
**Verify:** `pytest cybersim/simulation/catalog -v` — loader rejects malformed; index returns expected.

### Task 2.2 — Web simulator implementation
**Inputs:** `06` §3.
**Do:**
- `cybersim/simulation/web/simulator.py` — `class WebSimulator` implementing `Simulator`. `init(env_template)` builds `EnvironmentGraph` (per-cat typing nodes/edges); `beats(ctx)` yields grouped beats per `06` §3.4 phases, using `ctx.rng` exclusively for all randomness.
- `cybersim/simulation/web/beats.py` — schedule + payload builders.
- `cybersim/simulation/web/commands.py` — `apply_command` per `06` §3.6.
- `cybersim/simulation/tasks.py` — Celery task `run_simulation(simulation_id)` orchestrating context, simulator, EventBus.
**Verify:** `pytest tests/sim_determinism/test_web_sqli.py` — runs twice; compares canonical events modulo timeout-fields; equality asserted.

### Task 3.1 — Postgres schema, migrations, RLS
**Inputs:** `09`.
**Do:**
- Alembic env at `cybersim/infra/db/`.
- Migration 0001: extensions (`pgcrypto, pgvector, pg_trgm, btree_gin`); schema `public`, `knowledge`, `ops`; tables per `09` §2–§8 with all indexes; enums as text+CHECK.
- Migration 0002 (manual review): RLS enable + policies per `09` §10; fail-closed.
- `cybersim/infra/db/dal.py` — async SQLAlchemy session factory + dep that issues `SET app.current_org_id = '<org>'`.
- `cybersim/platform/auth/models.py` — `users/orgs/org_members/sessions/refresh_tokens` active.
- `cybersim/tools/seed.py` — `cybersim seed --demo` (admin user + free org + RLS sanity rows).
**Verify:** `pytest tests/integration/security/test_rls.py` — fails closed; `pytest tests/integration/db/test_migrations.py` — upgrade + downgrade work on scratch DB.

### Task 3.2 — Normalizer + Postgres graph persistence
**Inputs:** `07` §2, `10`.
**Do:**
- `cybersim/events/normalizer.py` — `Normalizer.normalize(raw, env) -> CanonicalEvent` per `07` §2.
- `cybersim/events/normalizer_tasks.py` — async consumer pulling from `events.raw.<org>.<sim>` with consumer group `normalizer`, dedup by `event_id`.
- `cybersim/graph/repo.py` — `GraphRepository` Protocol per `10` §2.
- `cybersim/graph/repo_nx.py` — `NetworkXGraphRepository` impl with `cache.py` (LRU) + `dal.py` (Postgres `graph_nodes`, `graph_edges`, `graph_overlay`, `graph_snapshots`/`graph_deltas` writes).
**Verify:** `pytest cybersim/events/normalizer cybersim/graph -v` over a fixture raw stream.

### Task 4.1 — FastAPI gateway + auth
**Inputs:** `08` §1–§3, `15` §2.
**Do:**
- `cybersim/api/main.py` — FastAPI app; problem-detail exception handler (`infra/errors/`); idempotency middleware (`infra/middleware/idempotency.py`); rate-limit middleware (`infra/middleware/rate_limit.py` with Redis Lua token bucket); `current_user` dep.
- Routers: `cybersim/api/routers/auth.py` (register, login, refresh, logout, ws-ticket, webauthn option minimally), `orgs.py`, `scenarios.py`.
- `cybersim/platform/auth/jwt.py` (RS256), `tokens.py` (refresh rotation + reuse detection), `webauthn.py` (start stub).
**Verify:** `pytest cybersim/api/routers -v`; OpenAPI diff green vs `schema.lock.json`.

### Task 4.2 — REST routes + WebSocket hub
**Inputs:** `08` §4–§5.
**Do:**
- Routers: `simulations.py`, `detections.py`, `graph.py`, `missions.py` stubs, `knowledge.py`, `billing.py` stubs.
- `cybersim/realtime/hub.py` — WS hub; `realtime/ticket.py` — ticket issue; `realtime/pubsub_redis.py` — channel publish/subscribe (`sim.<sim_id>`).
- Per-subscription coalescing cap, lag frame, backpressure per `08` §5.
**Verify:** `pytest cybersim/api/routers cybersim/realtime -v`; Solo integrand test asserts 2-instance WS fan-out via Redis.

### Task 5.1 — Rule-based fallback + validator
**Inputs:** `11` §3.10–§3.11, §5.
**Do:**
- `cybersim/analyst/state.py`, `dto.py` (Pydantic per `11` §5).
- `cybersim/analyst/rules_fallback.py` — `analyze_window(events, graph_repo) -> DetectionProposal | None` using `severity_hint` + graph path scoring.
- `cybersim/analyst/validator.py` — `ValidationResult` + clamps per `11` §3.9.
- `cybersim/analyst/runtime.py` — `AnalystRuntime.ingest(window)` that calls rules path when feature flag `analyst.mode=rules`.
- `cybersim/api/routers/detections.py` — persist + WS-publish via the runtime.
**Verify:** `pytest cybersim/analyst -v`; mission `finbank_breach` end-to-end with `analyst.mode=rules` produces validated Detection with ≥3 evidence + nodes path. Document this as M1.

### Task 6.1 — LangGraph analyst nodes
**Inputs:** `11` §2–§4, `06` §6.2 skeleton prompts.
**Do:**
- `cybersim/analyst/nodes/{event_ingestion,candidate_group,threat_detection,graph_retrieval,evidence_analysis,rag_lookup,risk_scoring,response_planning,validation_gate,emit_detection,rule_fallback}.py` — node functions + LangGraph `StateGraph` wiring per `11` §1 mermaid diagram.
- `cybersim/analyst/prompts/*.j2` (templates per `11` §6.2–§6.3 with exact field schemas).
- `cybersim/analyst/llm/llm_client.py` (interface) + `openai_client.py`; `router.py` (model routing per `11` §7).
- `cybersim/analyst/tools.py` (`get_attack_paths`, `get_neighbors`, `get_foothold_state`, `retrieve_knowledge`).
- Checkpointer impl: `analyst_checkpoints` Postgres table (mirror).
**Verify:** `pytest tests/analyst_ai/` (skip if no `OPENAI_API_KEY`); `tests/prompt_stability/` runs 3× and asserts stable threat_class/severity/techniques.

### Task 6.2 — Knowledge base & RAG
**Inputs:** `12`.
**Do:**
- `cybersim/knowledge/entries.py` (Pydantic `KnowledgeEntry`), `repo.py` (`KnowledgeRepository` Protocol).
- `cybersim/knowledge/ingest/{mitre,owasp,cve,cwe,notes}.py` adapters.
- `cybersim/knowledge/embeddings.py` (via `LLMClient.embed()` — OpenAI embeddings).
- `cybersim/knowledge/retrieval.py` (hybrid + rerank).
- `cybersim/tools/seed_knowledge.py` CLI.
- Vendored fixtures under `tests/fixtures/knowledge/`.
**Verify:** `pytest cybersim/knowledge -v`; recall@5 ≥ 0.9 on golden queries.

### Task 7.1 — Other 3 simulators
**Inputs:** `06` §4–§6, `07`.
**Do:** `cybersim/simulation/api/`, `network/`, `supply/` mirroring `web/`; tests matching determinism + per-sim scenario-golden.
**Verify:** `pytest tests/sim_determinism tests/scenario_golden -v`.

### Task 8.1 — Frontend foundation & SOC dashboard
**Inputs:** `13`, `02`.
**Do:** Build `apps/web/` per `13` paths: tokens, primitives, shell, lib/api, lib/ws, lib/auth, dashboard component tree (`08` + `02` §4). Generate typed client from `/v1/openapi.json`. WS provider + coalescing.
**Verify:** `pnpm test`, `pnpm tsc --noEmit`, `pnpm build`, Lighthouse ≥85 on dashboard; axe no critical.

### Task 9.1 — Mission Mode
**Inputs:** `14`.
**Do:** `apps/web/src/components/mission/*`, `cybersim/missions/{dsl,scoring,share}.py`, public pseudo-tenant routes.
**Verify:** mission e2e Playwright; share-link rate-limit tests.

### Task 10.1 — Billing
**Inputs:** `16`.
**Do:** Stripe Checkout + Portal + webhooks; metering flush job; entitlements API.
**Verify:** Idempotent webhook test; entitlement propagation test.

### Task 11.1 — Observability + IaC
**Inputs:** `18`, `17` §4–§5.
**Do:** OTel exporters; Langfuse self-host compose profile; Grafana dashboards as code; Terraform staging env; CI deploy-to-staging job on main.
**Verify:** trace end-to-end on staging; SLO dashboard readable.

### Task 12.1 — Marketing + final polish + a11y
**Inputs:** `02` §5.2, `20` §2.8–§2.9.
**Do:** `(marketing)` route group, hero, code-hero with the JSON decision package as a live artifact; final Lighthouse ≥90 on marketing; final a11y audit.
**Verify:** marketing Lighthouse CI green; `make verify` fully green; e2e passing on all primary pages.

---

## D. Acceptance criteria — "Done when"

Phase = complete when ALL hold:
1. The phase's `Verify` command(s) green locally.
2. CI workflow for the phase green on a feature branch.
3. Any "Decision rationale & alternatives" doc reference changed asks for a written override recorded (`00` §0).
4. The phase's milestone narrativa (if listed in `19` milestones) demoable per its scenario golden.

## E. Stop-and-ask criteria (escalate)

Agent must pause and ask the user before proceeding if:
- A doc says "decide later" and the agent will choose by itself.
- A doc's interface is ambiguous and the agent can pick >1 reasonable interpretation.
- The agent believes the doc is wrong (do not silently override; record the issue + ask).
- A third-party library not in `04` is needed.
- The current task would require committing data/secrets.

## F. Output contract per task

At end of each task, the agent reports:
```
Task: <id>
Files created: ...
Files modified: ...
Deviations: ... (or none)
Verification output: ... (last lines)
Open questions: ... (or none)
Next task: <id>
```

This exact format makes multi-agent orchestration tractable (`21`).

---

## G. Inventory pointer

When this doc finishes a phase, the implementing agent is operating in lockstep with `19-development-roadmap.md` (phases + DoD), `20-testing-strategy.md` (verify commands), and the spec docs the task names. **If anywhere there is conflict, the spec doc wins over this file.**

End of documentation suite. Read `00-README.md` to start any new task.
