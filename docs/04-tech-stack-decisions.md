# 04 — Tech-Stack Decisions

Every technology choice for CyberSim AI, with the **chosen** option, the **rejected alternatives**, the **why**, and the **swap-out seam** (the abstraction layer we maintain so replacing this dependency later is bounded to one package). The directive from the brief: this is a *learning platform* — we want richness, but never gratuitous complexity (e.g., "don't use LangGraph just because the name contains 'Graph'").

Each row has: 📌 **Chosen** · ⚖️ **Rejected** · 🧭 **Why** · 🔌 **Swap seam**.

---

## 1. Stack at a glance

| Layer | Choice | Version pin (min) | Track (build order) |
|-------|--------|-------------------|---------------------|
| Backend language | Python | 3.11 | A |
| Backend framework | FastAPI | 0.110+ | A |
| Agent orchestration | LangGraph | 0.2+ | E |
| LLM access | OpenAI SDK + provider adapter | latest | E |
| Validation/parsing | Pydantic v2 | 2.7+ | A |
| Relational DB | PostgreSQL | 16 | B |
| Migrations | Alembic (autogen + manual) | 1.13+ | B |
| Vector store | **pgvector** (Postgres extension) | 0.7+ | D |
| Graph engine | NetworkX (in-process) | 3.3+ | C |
| Graph DB (future) | Neo4j (5.x) | — | (v0.2 seam) |
| Cache / queue / pub-sub | Redis | 7.2 | B |
| Job queue | Celery + Redis broker | 5.4+ | C |
| Object storage | S3-compatible (MinIO dev) | — | G |
| Frontend framework | Next.js (App Router) | 14.2+ | F |
| Frontend language | TypeScript | 5.4+ | F |
| Styling | Tailwind CSS v4 | 4.0+ | F |
| UI primitives | Radix UI + custom | latest | F |
| Icons | Lucide | latest | F |
| State/data | TanStack Query + Zustand | latest | F |
| AuthN | JWT (internal) + oauth2-password + WebAuthn optional | — | A |
| Billing | Stripe (Checkout + Customer Portal + Webhooks) | — | H |
| IaC | Terraform | 1.7+ | (infra) |
| Containers | Docker + Docker Compose (dev) | — | A |
| CI runner | GitHub Actions | — | A |
| LLM observability | Langfuse (self-host) | 2.x+ | G |
| Observability | OpenTelemetry → Tempo/Loki/Prometheus | — | G |
| Logs | structured JSON (structlog) | — | A |

---

## 2. Deep dive per decision

### 2.1 Backend: Python 3.11 · FastAPI · Pydantic v2 📌
- ⚖️ **Rejected:** Django (heavier, less async-native for real-time), Flask (no async-first), Go (fast but the ecosystem around LangGraph/RAG/ML is Python-first; switching costs the learning goals — see below). Node/TS backend (would unify language with frontend) rejected *for the AI/data plane* because the strongest agent + graph + retrieval libraries are Python; a Node backend would force us off LangGraph.
- 🧭 **Why:** (1) Brief explicitly specifies Python + FastAPI and LangGraph — we honor it. (2) Async-first FastAPI fits our WebSocket-heavy API. (3) Pydantic v2 (Rust core) gives us the *normative* contract surface for events and the LLM's structured outputs — central to our "validate before act" rule. (4) Type hints + `mypy --strict` give a real type contract for a multi-contributor codebase.
- 🔌 **Swap seam:** FastAPI routers stay thin; business logic lives in `cybersim.*` packages callable from any framework (CLI, worker, tests). Migrating to Starlette/Litestar would touch only `cybersim/api/`.

### 2.2 Async strategy
- 📌 **Hybrid:** FastAPI async request handlers for I/O-bound paths (DB, WS, LLM calls). CPU-bound deterministic simulation beats run in a **Celery worker** (not the event loop). The normalizer consumer runs as an `asyncio` task per stream since it's mostly I/O.
- ⚖️ **Rejected:** pure-async (would block event loop on seeded RNG beats + serialization in tight loops—bad). **Rejected:** pure-sync FastAPI (def(...) endpoints) — loses WS throughput.
- 🔌 **Seam:** simulation deterministic core is plain synchronous Python callable; the worker wraps it. No `async` leaks into domain code.

### 2.3 Agent orchestration: LangGraph 📌 (with a hard, justified "why")
- ⚖️ **Rejected:** plain LangChain (no fine-grained state machine; "called an LLM and gave it a dashboard" pattern the vision explicitly forbids), direct LLM calls (no orchestration), AutoGen (multi-agent concurrency overshoots MVP — we need one analyst with tools), CrewAI (role-based multi-agent overhead, harder to make deterministic), custom state machine in `asyncio` (we'd reinvent LangGraph's checkpointing).
- 🧭 **Why:** The analyst is literally a **state machine with shared state, tools, conditional edges, and checkpointing/replay** — LangGraph's exact model. The vision's flow node graph maps 1:1 onto LangGraph nodes. Checkpointing gives us free run replay (matches "reproducibility is a feature"). Conditional edges express `is_suspicious? yes/no`. Tools express graph queries + retrieval. This is *not* LangGraph-because-the-name-contains-Graph; it's LangGraph-because-the-shape-is-a-graph. (See `11`.)
- 🔌 **Swap seam:** All graph logic behind `analyst.runtime.AnalystRuntime` exposing `ingest(event) -> Optional[DetectionProposal]`. Internals use LangGraph; a port to a hand-rolled FSM would touch only `analyst/runtime/`.

### 2.4 LLM provider: provider-agnostic adapter (default OpenAI-compatible) 📌
- 📌 Use a thin `LLMClient` interface (chat, structured-output via JSON schema) backed by `openai` SDK pointed at the chosen provider. Default provider: **OpenAI** (gpt-4o-class for analysis, gpt-4o-mini for triage/light nodes). A second adapter for **Anthropic** Claude is optional.
- ⚖️ **Rejected:** LangChain LLM wrappers (extra abstraction; we already have OpenAI SDK + LiteLLM-style adapter), Ollama-only local (latency/quality below demo-grade; fine for dev offline mode as an *opt-in dev adapter*).
- 🧭 **Why:** The brief says "Whatever API you have access to." We standardize on the OpenAI Chat Completions surface (most broadly compatible) and validate structured outputs with our **own** Pydantic parse on the way in — we do **not** trust the SDK's `response_format` alone; we parse defensively and retry on failure (`11` guardrails).
- 🔌 **Swap seam:** `cybersim.analyst.llm.LLMClient` interface; concrete adapters `OpenAIClient`, `AnthropicClient`, `LocalOllamaClient(dev-only)`. Prompt templates do not reference provider-specific features.

### 2.5 Relational store: PostgreSQL 16 📌
- ⚖️ **Rejected:** MySQL (weaker JSONB, weaker RLS, weaker pgvector), Mongo (we need transactions + RLS; document model hurts analytical joins), SQLite (no multi-tenant concurrency).
- 🧭 **Why:** Mature, JSONB + GIN for event payloads, **Row-Level Security for tenant isolation** (`15`), **pgvector** for RAG in the same DB (avoids a second store), native `gen_random_uuid()`, mature prod story. Single source of ops pain.
- 🔌 **Seam:** All SQL via SQLAlchemy 2.0 (async) with an explicit `Repository` layer. No business code raw-SQL-leaks; migrations stay portable-ish.

### 2.6 Migrations: Alembic 📌
- ⚖️ **Rejected:** `sqlalchemy-migrate`, raw `migrations/*.sql` folder (loses ordering/autogen), Prisma migrate (different language/stack).
- 🧭 **Why:** Battle-tested, autogen from models, supports multi-tenant baseline. We **never use `autogenerate` for tenant boundary changes** (manual review for RLS policies).
- 🔌 **Seam:** `infra/db/migrations/`; baseline/seed scripts in `infra/db/seeds/`.

### 2.7 Vector store: pgvector 0.7+ 📌
- ⚖️ **Rejected:** Pinecone (SaaS dependency, separate ops, cost, egress; we'd replicate knowledge anyway), Qdrant (extra component, no win over pgvector at our vector cardinality), Weaviate (heavy).
- 🧭 **Why:** We already run Postgres; vector cardinality is small-to-medium (knowledge base: thousands–tens-of-thousands of chunks; per-org uplift: small). pgvector HNSW index handles this well < 1M vectors (we'll be far below). Saves a store, a deploy, a backup, a budget line. Migration to a dedicated store is bounded behind `knowledge.repo.KnowledgeRepository` if scale demands (`12`).
- 🔌 **Seam:** `KnowledgeRepository` interface; can re-target Pinecone/Qdrant later without touching retrieval logic.

### 2.8 Graph engine: NetworkX today, Neo4j tomorrow 📌
- ⚖️ **Rejected:** Neo4j on day 1 (extra DB + Cypher learning curve + lifecycle/backup cost for graphs that are ≤100 nodes and ephemeral), ArangoDB (multi-model, more than we need), memgraph (smaller community), pure SQL recursive CTEs (cumbersome for path queries).
- 🧭 **Why:** Per-simulation attack graphs are small and ephemeral; NetworkX is dependency-light, trivially serialized/snapshotted to Postgres (JSON), and has every path algorithm we need (shortest path, all-simple-paths with depth limit, centrality). Neo4j earns its keep for **persistent, cross-simulation, large** graphs — that's a v0.2 concern (e.g., an org-wide asset graph reused across missions).
- 🔌 **Seam (normative):** `graph.repo.GraphRepository` abstract interface with `NetworkXGraphRepository` (v0.1) and `Neo4jGraphRepository` (v0.2). All business code calls the repository, never NetworkX directly. **CI test suite runs the same tests against an in-memory NetworkX repo and a stub that fakes a remote repo, to prove the abstraction.**

### 2.9 Cache / queue / pub-sub / streams: Redis 7.2 📌
- ⚖️ **Rejected:** RabbitMQ (strong but more moving parts + less natural WS fan-out), NATS JetStream (excellent but extra learning curve; not worth it for the 3 Redis use-cases we have), cloud SQS/Pub-Sub (vendor lock-in; dev friction).
- 🧭 **Why:** One component covers (a) cache, (b) Celery broker + result backend, (c) Redis Streams event bus, (d) pub/sub WS fan-out, (e) rate-limit tokens. Redis Streams + consumer groups + persistence tick the guarantees we need (order per stream, at-least-once, consumer-group ack). One ops box to run/backup.
- 🔌 **Seam:** `cybersim.events.bus.EventBus` (publish/subscribe), `cybersim.realtime.hub.PubSub`. Both can be reimplemented against Kafka/NATS without touching call sites.

### 2.10 Job queue: Celery 5.x (+ Redis broker) 📌
- ⚖️ **Rejected:** RQ (simpler but weaker orchestration; we need beat-style scheduling for time-bounded simulation clocks + per-task concurrency limits + priority), Dramatiq (fine; Celery has bigger ecosystem + the same Redis), Arq (single-broker; nice but smaller).
- 🧭 **Why:** Worker pool for simulation runs; per-tenant concurrency caps (entitlements); `celery beat` for reminder/cleanup tasks. Celery's reputation for rough edges is offset by `cybersim.platform.queues` wrappers that constrain it (typed tasks, status enums, idempotency keys).
- 🧭 Why not "background tasks in FastAPI's threadpool"? Because we need **horizontal worker scaling + cross-process state**; an in-process pool dies with the API process. The vision brief implies long-running "mission clocks" — needs a real queue.
- 🔌 **Seam:** Tasks defined behind `cybersim.simulation.tasks`; the queue library is a single package, swappable to Dramatiq.

### 2.11 Object storage: S3-compatible (MinIO in dev; S3/R2 in prod) 📌
- 📌 Used for: evidence artifacts (the structured payloads beyond a DB row's size), run exports (JSON replay bundles), optional knowledge-base source files.
- ⚖️ **Rejected:** filesystem-only (no multi-instance), DB BLOB (bloats WAL/backups).
- 🧭 **Why:** Standard S3 API abstracts MinIO(dev) ↔ S3/R2(prod). Cheap backup story.
- 🔌 **Seam:** `cybersim.infra.storage.ObjectStore` interface.

### 2.12 Frontend: Next.js 14 App Router · TypeScript · Tailwind v4 📌
- ⚖️ **Rejected:** Remix (would also be fine; we lose RSC/ISG maturity + ecosystem the brief doesn't justify a switch), Vite SPA (no SSR; weaker SEO; the marketing site is part of the product), SvelteKit (excellent DX but ecosystem; would split hiring/contrib friction), Astro (great for marketing, weak for app).
- 🧭 **Why:** SSR + streaming for marketing + dashboard initial paint; RSC for the dashboard keeps the heavy lifting server-side (auth, initial feed slice) and pushes small client islands for WS/streaming. The dashboard itself is a client-rendered SPA-like page fed by WS (SSR is the initial tail). OpenAI's platform ships Next.js-style tech — parity with reference UI is easier.
- 🔌 **Seam:** API consumed via typed client generated from FastAPI OpenAPI schema (`openapi-typescript`); the web app talks only to the typed client — no raw `fetch`.

### 2.13 Styling: Tailwind v4 + CSS variables 📌
- ⚖️ **Rejected:** CSS-in-JS (runtime cost on dense UI; doesn't integrate RSC well), vanilla-extract (good but build-step; Tailwind is faster for a design system with utility-first density), styled-components (RSC friction).
- 🧭 **Why:** v4's `@theme` + first-class CSS vars let us hold one source of truth (see `02` §3) and switch theme/density at runtime by changing `data-theme`/`data-density` attributes — no rebuild. Utilities match the dense SOC UI; component classes (`cui-row`, `cui-card`) encode the design system.
- 🔌 **Seam:** Design tokens are CSS vars; Tailwind is generator only. Removing Tailwind later is bounded to the design-system components, not application code.

### 2.14 UI primitives: Radix UI (headless) + custom 📌
- ⚖️ **Rejected:** shadcn/ui (great; we adopt its *patterns* but build our own slot-in implementations using our tokens — we don't import its snapshots wholesale because we want full control of the design system and to keep a11y decisions ours), MUI (heavy, opinionated visual style collides with OpenAI-inspired neutrality), Chakra (style props + TS, but heavier than needed), AntD (visual style far from target).
- 🧭 **Why:** Radix gives us a11y-hardened primitives (Dialog, Menu, Popover, Tooltip, Toggle, Toast, Slot) without styling; we apply our design system on top. Components are *ours*, tokens-only.
- 🔌 **Seam:** Icon set (Lucide) and PRimitive (Radix) are drop-in if either ever changes; the design system is independent.

### 2.15 State & data fetching on web: TanStack Query + Zustand 📌
- ⚖️ **Rejected:** Redux Toolkit (overkill for our state shape; no real benefit), SWR (also fine; TanStack's mutation/optimistic APIs edge it out for our response-execution UI), raw `useEffect` fetching (anti-pattern).
- 🧭 **Why:** TanStack Query for server state (REST), `useSyncExternalStore` for WS messages, **Zustand for ephemeral UI state** (selected detection, drawer state, density). Clear boundary: server-cache vs. session-ephemeral.
- 🔌 **Seam:** All data through a `lib/api/*` typed client + WS adapter; both swappable, components don't import transport.

### 2.16 AuthN/Z: internal JWT + refresh + WebAuthn optional 📌
- ⚖️ **Rejected:** Clerk (great, fast; vendor lock-in + SaaS billing dependency + data residency concerns), Auth0 (similar; cost), Supabase Auth (couples us to Supabase infra), magic-link-only (no security-tool users want magic-link only).
- 🧭 **Why:** A security tool should ship its own auth so we fully control tokens, scopes, RLS coupling, and audit. Cost: ~1 phase of work; benefits: tight tenant boundaries + no auth-vendor billing coupling. **WebAuthn (passkey) optional** — practitioners value phishing-resistant auth; we add it as a *secondary* login method, not a replacement, to keep friction low.
- 🔌 **Seam:** Auth behind `cybersim.platform.auth`; tokens opaque to the rest of the system (we expose `current_user`). External IdP (SSO) is a v0.2 adapter behind this interface.

### 2.17 Billing: Stripe 📌
- ⚖️ **Rejected:** ChargeBee (enterprise sales friction), Lemon Squeezy (merchant-of-record is nice but limits flexibility + EU/US tax story differs from Stripe's depth), no-billing (no).
- 🧭 **Why:** Practical default: Checkout + Customer Portal + Webhooks + metered billing (analyst invocations, simulation-minutes) — covers our entitlements (`16`). Stripe is the boring-correct choice.
- 🔌 **Seam:** `cybersim.platform.billing.BillingProvider` interface; concrete `StripeProvider`. The rest of the app doesn't import Stripe.

### 2.18 IaC: Terraform 📌
- ⚖️ **Rejected:** Pulumi (great; team familiarity default to TF), Cloud Formation (AWS-only), CDK (AWS-only).
- 🧭 **Why:** Cloud-agnostic; matches "don't over-commit to a single cloud at MVP." Modularized so prod can be AWS/GCP/Fly interchangeably with bounded edits (`17`).
- 🔌 **Seam:** Backend choice (Postgres-as-managed-service vs self-hosted) is parameterized.

### 2.19 LLM observability: Langfuse (self-host) 📌
- ⚖️ **Rejected:** Arize Phoenix (good, heavier), LangSmith (LangChain-vendor; we want ours), no tracing (non-starter: we *need* to debug prompts and replay run decisions — "reproducibility").
- 🧭 **Why:** OSS, self-hostable, OpenTelemetry-aligned; records prompts/responses/usage/costs with our org/run tags. Pairs with general OTel. We tag every trace with `org_id`, `simulation_id`, `node` so an AI decision is auditable end-to-end.
- 🔌 **Seam:** Tracing behind an `LLMTracer` interface; can target stdout for local dev and Langfuse for prod.

### 2.20 General observability: OpenTelemetry → Tempo/Loki/Prometheus + Grafana 📌
- ⚖️ **Rejected:** Datadog (vendor cost + lock-in), Sentry (good for *errors*, complementary not a replacement — we add Sentry-lite via OTel too), honeycomb (good but cost).
- 🧭 **Why:** One OSS pipeline across logs/metrics/traces; mirrors Redis/Postgres/etc. in a single Grafana. LLM traces go to Langfuse; *generic* traces go to Tempo. Application logs structured JSON to Loki.
- 🔌 **Seam:** Exporters configurable; we can ship to a managed OTel backend later by changing exporter endpoints.

---

## 3. Cross-cutting "non-choice" rules

1. **No business code imports an SDK *implementation*; always behind an interface.** (This is the universal seam policy — and the single biggest determinant of swap-ability.)
2. **The LLM is never in any response path of a security-affecting action without Pydantic validation + executor whitelist.** (Restated from `01` §3 + `03` §8.1 — duplicated because it's load-bearing.)
3. **One toolchain.** `uv` for Python (lockfile + reproducible envs); `pnpm` for JS (workspaces-friendly, fast); `pre-commit` (ruff, black-compatible `ruff format`, mypy, eslint, prettier, tsc). *No black + isort; ruff replaces both.*
4. **Strict typing.** `mypy --strict` for packages, `tsc --strict` for the app. Pydantic models are the boundary contract.
5. **Determinism convention:** any `random` use goes through `cybersim.simulation.core.rng` seeded per simulation. No `random.random()` elsewhere; documented inspection lint (`20`).

---

## 4. Decision rationale table — alternatives summary

| Layer | Chosen | #1 rejected alt | Why not the rejected |
|------|--------|-----------------|----------------------|
| Agent framework | LangGraph | LangChain LCEL | state/control-plane conflation; no checkpoint |
| LLM access | openai SDK + adapter | LangChain LLM wrappers | unnecessary abstraction; trust our Pydantic instead |
| Vector store | pgvector | Pinecone | extra store/ops/$; sub-scale here |
| Graph | NetworkX→Neo4j seam | Neo4j day 1 | cardinality doesn't justify an extra DB and Cypher learning for ephemeral ≤100-node graphs |
| Queue | Celery + Redis | Dramatiq | Celery's broader ecosystem; same broker |
| Frontend | Next.js | Vite SPA | losing SSR + RSC cost us the marketing-dashboard dual nature |
| Styling | Tailwind v4 + CSS vars | CSS-in-JS | runtime cost + RSC friction |
| UI primitives | Radix + custom | shadcn/ui snapshots | want full design-system ownership |
| Auth | internal JWT | Clerk | tenant isolation + cost control + audit |
| Billing | Stripe | ChargeBee | Stripe is the boring-correct default with metered billing |
| Observability | OTel + Langfuse | Datadog | OSS + self-host, no lock-in |
| IaC | Terraform | Pulumi | broader familiarity + cloud-neutral |

---

## 5. License/dependencies compliance note
- All chosen libs are MIT/Apache-2.0/BSD-compatible. **No GPL/AGPL** dependencies in the build (a SaaS + future on-prem offering requires this). `pre-commit` licenses check (`pip-licenses`, `license-checker`) is a CI gate (`20`). OpenAI SDK is MIT; LangGraph is MIT; Radix is MIT; Tailwind is MIT; Lucide is ISC; Langfuse is MIT (self-host).

---

## 6. What we explicitly did *not* choose and why (brief)

- **Not a real Elasticsearch/SIEM** — out of scope; the cyber range doesn't need a petabyte-scale indexer. Feed backpressure is handled by WS coalescing + Postgres indexes.
- **Not Kafka now** — added ops load below MVP threshold; Redis Streams first, Kafka behind the same `EventBus` seam later if/when warranted (`03` §6.2).
- **Not a microservices topology now** — modular monolith + queue seams. Service split points identified (`03` §6.1) but not executed until the profile demands it.
- **Not a real sandbox/VM for "attacks"** — simulations *generate structured events*; they do not spin VMs and execute payloads. This is the safety promise (`01` §8) and keeps the demo cheap and reproducible. v0.2 could integrate with a real range via the same `Simulator` interface.

---

End of `04-tech-stack-decisions.md`. Next: `05-domain-model-attack-graph.md`.
