# 09 — Database Schema (PostgreSQL 16)

The relational store for CyberSim AI. Covers table design for **platform** (orgs, users, billing, scenarios), **simulation** (sims, events, detections, evidence, actions), **graph** (assets, environment edges, graph snapshots/deltas), **knowledge** (RAG entries + vectors), and **ops** (jobs, audit). Multi-tenant isolation via **Row-Level Security** + app-layer scoping. Vector storage via **pgvector** on the same cluster.

> **Conventions (normative from `00`):** tables plural `snake_case`; PKs `UUIDv7` text; timestamps `timestamptz` (UTC `Z` serialized); `org_id` required on every tenant-scoped table; `JSONB` for flexible payloads with GIN indexes; enum types via Postgres enums *or* text + CHECK (text+CHECK chosen for portability of dumps). Migrations in Alembic; this doc is the design baseline.

---

## 1. Topology

```
cybersim_db (cluster)
├── schema public        # tenant-scoped application tables (RLS-enforced)
├── schema knowledge     # RAG tables (global + per-org partitions)
├── schema ops           # jobs, audit_logs, telemetry rollups (system-only)
└── extensions: pgcrypto, pgvector, pg_trgm, btree_gin
```
One cluster, separate schemas for blast-radius control. Logical partitions per `org_id` **not** used at MVP (RLS suffices; we revisit Sharding in v2 when large tenants arrive — see `09` §10 self-q).

### 1.1 Index conventions
- Every tenant-scoped table: composite `(org_id, <natural key>)` unique indexes.
- Every time-series table: BRIN on time columns or B-tree on `sequence`.
- Event-detail fast paths: `GIN(payload jsonb_path_ops)`.
- Text search fallback: `GIN(name gin_trgm_ops)`.

## 2. Platform tables

### 2.1 orgs
| Column | Type | Notes |
|--------|------|-------|
| `id` | text PK | UUIDv7 |
| `name` | text not null | |
| `slug` | text not null unique | URL-safe |
| `default_density` | text not null default `'comfortable'` | check ∈ {comfortable, compact, ultracompact} |
| `created_at`, `updated_at` | timestamptz | |
| `deleted_at` | timestamptz null | soft delete |

Indexes: `unique(slug)`.

### 2.2 users
| Column | Type | Notes |
|--------|------|-------|
| `id` | text PK | |
| `email` | citext not null unique | (use citext extension) |
| `password_hash` | text null | argon2id; null if sso/passkey-only |
| `mfa_secret_enc` | bytea null | TOTP secret, envelope-encrypted (`15`) |
| `webauthn_credentials` | jsonb default '[]' | list of registered passkeys |
| `status` | text default `'active'` | active|disabled|invited |
| `created_at`, `last_login_at` | timestamptz | |

> **Self-question:** store `webauthn_credentials` as JSONB or normalized? **Answer:** JSONB — passkeys are small, low-cardinality per user, and rarely queried across users; normalized table adds cost without benefit.

### 2.3 org_members
| Column | Type | Notes |
|--------|------|-------|
| `org_id` | text | FK orgs |
| `user_id` | text | FK users |
| `role` | text | admin|member (v0.1) |
| `created_at` | timestamptz |
| PK `(org_id, user_id)` |

### 2.4 sessions & refresh_tokens
| Column | Type | Notes |
|--------|------|-------|
| `id` | text PK | session id (= sid claim) |
| `user_id`, `org_id` | text | |
| `refresh_token_hash` | text unique | hash of opaque refresh token |
| `ua`, `ip` | text | for reuse detection |
| `issued_at`, `expires_at`, `rotated_at` | timestamptz | |
| `revoked_at` | timestamptz null |
| `last_refreshed_at` | timestamptz |

### 2.5 invites
| Column | Type | Notes |
|--------|------|-------|
| `id` | text PK | |
| `org_id`, `email`, `role`, `invited_by`, `status`, `expires_at` | | |

### 2.6 entitlements & usage (mirror of billing; see `16`)
| Column | Type | Notes |
|--------|------|-------|
| `org_id` | text PK | |
| `plan` | text | free|pro|enterprise |
| `entitlements` | jsonb | max_concurrent_sims, ai_tier, retention_days, rps_caps, mission_share |
| `stripe_customer_id` | text null |
| `stripe_subscription_id` | text null |
| `current_period_end` | timestamptz null |
| `usage_period_start` | timestamptz |
| `updated_at` | timestamptz |

### 2.7 usage_events (metering)
| Column | Type | Notes |
|--------|------|-------|
| `id` | text PK | |
| `org_id` | text | |
| `metric` | text | sim_minutes|llm_tokens_in|llm_tokens_out|llm_calls|exports|missions_started |
| `quantity` | bigint | integer counters |
| `at` | timestamptz | |
| Index | `(org_id, metric, at)` BRIN | rollup by day/hour later |

## 3. Scenarios / catalog (cache of file catalog with overrides)
### 3.1 scenarios
| Column | Type | Notes |
|--------|------|-------|
| `id` | text PK | slug |
| `simulator` | text | web|api|network|supply |
| `category` | text | one of 7 |
| `status` | text | active|roadmap |
| `display` | jsonb | title/blurb/difficulty/duration_sec |
| `spec_yaml` | text | raw catalog YAML (for inspector) |
| `env_template_hash` | text | content hash of resolved env |
| `updated_at` | timestamptz |
| Index | `(simulator, category)` |

### 3.2 scenarios_org_overrides (v0.2 — schema present, gated by entitlements)
| Column | Type |
|--------|------|
| `org_id` | text |
| `scenario_id` | text |
| `spec_yaml_override` | text |
| PK `(org_id, scenario_id)` |

## 4. Simulations

### 4.1 simulations
| Column | Type | Notes |
|--------|------|-------|
| `id` | text PK | UUIDv7 |
| `org_id` | text | |
| `scenario_id` | text FK | |
| `label` | text null |
| `seed` | bigint | RNG seed |
| `params` | jsonb | tuned params |
| `status` | text | queued|running|paused|completed|failed|stopped |
| `phase` | text | e.g., "recon"|"exploit"|"post_exploit"|"containment" (advisory) |
| `started_at`, `ended_at` | timestamptz null | |
| `duration_sec` | int | sim duration (wallclock elapsed mirrored) |
| `mission_id` | text null FK missions |
| `is_mission` | bool default false |
| `public_share_token` | text null | for Mission Mode public links (`14`) |
| `created_by` | text FK users |
| `created_at` | timestamptz |
| Index `(org_id, created_at desc)`, `(status)`, `(mission_id)` |

### 4.2 events (the hot path — partitioned)
- **Partition strategy:** `RANGE` partition by `received_at` monthly (per the simulation lifecycle: most queries recent). Cross-year partition maintenance via `pg_partman` (or hand-rolled).
| Column | Type | Notes |
|--------|------|-------|
| `event_id` | text PK | UUIDv7 |
| `simulation_id` | text | FK simulations |
| `org_id` | text | (denormalized for RLS speed) |
| `sequence` | int | strictly increasing per sim |
| `received_at` | timestamptz | partition key |
| `sim_time_ms` | bigint | sim clock |
| `origin`, `raw_type`, `category`, `subtype` | text | |
| `severity_hint` | text | |
| `attack_stage` | text null | |
| `benign` | bool default false | |
| `target_node_ids` | text[] | GIN |
| `source_node_id` | text null | |
| `via_edge_ids` | text[] | GIN |
| `mitre_tactics`, `mitre_techniques`, `owasp_refs` | text[] | |
| `correlation_key` | text null | |
| `payload` | jsonb | GIN jsonb_path_ops |
| `raw_ref` | text null | object-store key |

Indexes (per partition):
- PK `event_id`
- unique `(simulation_id, sequence)` — enforces determinism claim
- `(simulation_id, received_at)` BRIN
- `GIN(target_node_ids)`, `GIN(mitre_techniques)`, `GIN(payload jsonb_path_ops)`

> **Self-question:** array columns (`text[]`) vs join tables for node refs? **Answer:** arrays. Events reference graph nodes but rarely need reverse join; we maintain a *separate* index `(target_node_ids)` GIN for "fetch events by node" UI. A join table would 5× row count on the hot path. We pay the GIN cost (small relative to inserts).

> Self-question: **denormalize `org_id` onto events?** Yes — RLS evaluation needs `org_id` per row without joins; cheaper than a FK at query time.

## 5. Detections & evidence

### 5.1 detections
| Column | Type | Notes |
|--------|------|-------|
| `id` | text PK | |
| `simulation_id` | text | FK |
| `org_id` | text | denormalized |
| `threat_class` | text | enum (`05`) |
| `title` | text | |
| `severity` | text | |
| `confidence` | numeric(4,3) | 0.000–1.000 |
| `confidence_band` | text | low|medium|high|verified |
| `mitre_tactics`, `mitre_techniques` | text[] | |
| `owasp_refs` | text[] | |
| `attack_path` | jsonb | array of {node,label} |
| `rationale` | text | bounded ≤2000 chars (`11`) |
| `source` | text | ai|rules|hybrid |
| `validated` | bool | false until validator passes |
| `status` | text | open|responded|mitigated|false_positive |
| `created_at` | timestamptz | |
| `rejected_at`, `rejected_reason` | timestamptz null, text null | |
| Index `(simulation_id, created_at)`, `(org_id, severity, created_at)` |

### 5.2 detection_evidence
| Column | Type | Notes |
|--------|------|-------|
| `detection_id` | text FK | |
| `label` | text | "repeated_failed_logins" |
| `kind` | text | event_burst|graph_traversal|credential_state|knowledge_citation|behavioral_signature |
| `weight` | numeric(4,3) | |
| `event_ids` | text[] | GIN |
| `graph_node_ids` | text[] | |
| `citation_refs` | text[] | knowledge entry ids |
| `extra` | jsonb | |

PK `(detection_id, label)`.

### 5.3 response_actions (catalog of available actions per simulator + custom)
| Column | Type | Notes |
|--------|------|-------|
| `id` | text PK | slug `block_source_ip` |
| `simulator` | text | |
| `title`, `description` | text | |
| `risk` | text | none|low|medium|high |
| `reversible` | bool | |
| `requires_confirmation` | bool | high-risk ⇒ true |
| `schema_params` | jsonb | action-specific params |

### 5.4 recommended_actions (per detection)
| `detection_id` | text FK | |
| `action_id` | text FK | |
| `order` | int | rank within recommendation |
| `params` | jsonb | |
| `rationale` | text | why this action |
| PK `(detection_id, action_id)` |

### 5.5 executed_actions
| Column | Type | Notes |
|--------|------|-------|
| `id` | text PK | execution_id |
| `org_id`, `simulation_id`, `detection_id` | text | |
| `action_id` | text | FK |
| `params` | jsonb | applied params |
| `executed_by` | text | user_id |
| `executed_at` | timestamptz | |
| `result` | text | applied|failed|rolled_back |
| `audit_blob` | jsonb | graph mutation summary |
| Index `(simulation_id, executed_at)` |

## 6. Graph

### 6.1 assets  & environment_edges (current env view)
For *historical* snapshots we use `graph_snapshots` + `graph_deltas` (§6.2). For *current* fast reads we maintain per-sim environment tables.

**graph_nodes** (per simulation)
| Column | Type |
|--------|------|
| `simulation_id` | text FK |
| `node_id` | text |
| `kind` | text | ASSET|SERVICE|CREDENTIAL|DATA|NETWORK_ZONE |
| `type` | text null | asset subtype (`05`) |
| `label` | text |
| `attrs` | jsonb |
| `foothold_state` | text | enum (`05` §3.3) |
| `attrs_updated_at` | timestamptz |
| PK `(simulation_id, node_id)` |

**graph_edges**
| Column | Type |
|--------|------|
| `simulation_id` | text |
| `edge_id` | text |
| `from_node` | text |
| `to_node` | text |
| `type` | text | EdgeType enum |
| `attrs` | jsonb |
| `active` | bool | removal by responses = false (no delete) |
| PK `(simulation_id, edge_id)` |
| Index `(simulation_id, from_node)`, `(simulation_id, to_node)` |

**graph_overlay**  (attacker-side — append-only state)
| Column | Type | Notes |
|--------|------|-------|
| `simulation_id` | text |
| `node_id` | text | overlay node id (==OverlayGraph local id) |
| `parent_node_id` | text null | graph node id it annotates |
| `state` | text | foothold_state enum |
| `flags` | jsonb | e.g., traversal method |
| `first_seen_seq`, `updated_at_seq` | int |


### 6.2 graph_snapshots & graph_deltas
- **graph_snapshots:** `(simulation_id, seq, snapshot jsonb, kind: full|delta_root)` — full snapshot every `Δt`.
- **graph_deltas:** `(simulation_id, from_seq, to_seq, added_nodes jsonb, added_edges jsonb, updated_footholds jsonb)` — delta between sequences; client replays.
- Index `(simulation_id, from_seq)`.
- Retention: kept for retention_days per tier (older collapsed into snapshots).

## 7. Knowledge (RAG) — schema `knowledge`

### 7.1 knowledge_entries (global pool + per-org partitions via RLS)
| Column | Type | Notes |
|--------|------|-------|
| `id` | text PK | |
| `org_id` | text | 'global' is sentinel; otherwise tenant-scoped |
| `source` | text | mitre|owasp|cve|custom|org_upload |
| `source_id` | text | original id e.g., T1110, A03:2021, CVE-2021-44228 |
| `kind` | text | technique|weakness|vuln|article |
| `title` | text |
| `summary` | text |
| `content` | text | chunk text |
| `payload` | jsonb | tags, references |
| `language` | text | 'en' |
| `created_at` | timestamptz |
| Index GIN(content gin_trgm_ops); `(org_id, source, source_id)` unique |

### 7.2 knowledge_embeddings
| Column | Type | Notes |
|--------|------|-------|
| `id` | text PK | |
| `entry_id` | text FK | |
| `model` | text | 'text-embedding-3-small' (or chosen) |
| `dim` | int | 1536 |
| `embedding` | vector(1536) | pgvector |
| Index HNSW `embedding vector_cosine_ops` |

> **Self-question:** embeddings in row vs single `embeddings` table? **Answer:** separate table — let us re-embed (model swap) without rewriting the big `content` column or invalidating the entries; allows multi-model embedding for experiments.

### 7.3 knowledge_citations (link detections → knowledge)
| `detection_id`, `entry_id` | FK | |
| `weight` | numeric | |
| PK `(detection_id, entry_id)` | | |

## 8. Missions
### 8.1 missions
| Column | Type | Notes |
|--------|------|-------|
| `id` | text PK | |
| `org_id` | text default 'global' | default missions are global, shareable |
| `title`, `description` | text | |
| `simulator` | text | |
| `scenario_id` | text | base scenario |
| `objectives` | jsonb | list of objective defs (`14`) |
| `scoring_config` | jsonb | weights, thresholds |
| `is_public_default` | bool | shareable |
| `created_at` | timestamptz |

### 8.2 mission_scores (live + final)
| `simulation_id` | text PK | |
| `mission_id` | text | |
| `org_id` | text | |
| `score` | jsonb | components |
| `final` | bool | live vs final |
| `updated_at` | timestamptz | |

## 9. Ops (schema `ops`)

### ops_jobs (mirroring Celery task state for queries/audit)
| Column | Type |
|--------|------|
| `id` | text PK (celery task id) |
| `org_id`, `simulation_id` | text |
| `task` | text | `simulation.run` |
| `state` | text | queued|running|succeeded|failed |
| `started_at`, `finished_at`, `attempts` | |
| `error_summary` | text null |

### ops_audit_logs
| Column | Type |
|--------|------|
| `id` | text PK |
| `org_id`, `user_id` | text null (nullable for system) |
| `action` | text | `simulation.start`, `response.execute`, `billing.subscribe` |
| `subject_type`, `subject_id` | text |
| `before`, `after` | jsonb null |
| `at` | timestamptz |
| `ip`, `ua` | text null |
| Index `(org_id, at desc)`, `(subject_type, subject_id)` |

### ops_llm_invocations (mirrors Langfuse + own audit; `11`/`18`)
| Column | Type |
|--------|------|
| `id` | text PK |
| `org_id`, `simulation_id`, `node` | text |
| `prompt_hash` | text | template hash |
| `tokens_in`, `tokens_out`, `cost_micros` | bigint / bigint / bigint (USD micros) |
| `provider`, `model` | text |
| `langfuse_trace_id` | text |
| `validated_outcome` | text | ok|retried|fallback |
| `at` | timestamptz |

## 10. Row-Level Security (multi-tenant isolation)

Every row in `public` schema and the user-facing `knowledge` views has `org_id`. RLS:

```sql
ALTER TABLE events ENABLE ROW LEVEL SECURITY;
ALTER TABLE events FORCE ROW LEVEL SECURITY;

CREATE POLICY events_org_isolation ON events
  USING (org_id = current_setting('app.current_org_id', true));
```

- The API gateway sets `SET app.current_org_id = '<org>'` on the connection per request (or per session), in addition to app-level check.
- Service roles for migrations/ops bypass RLS (uses `BYPASSRLS`).
- The `graph_*`, `detection*`, `executed_actions`, `mission_scores` tables all RLS-by-`org_id` (denormalized).
- **Knowledge** is a special case: global rows have `org_id = 'global'`; policy: `org_id = current_setting('app.current_org_id') OR org_id = 'global'`.
- **Fail-closed:** if `app.current_org_id` is unset, all RLS policies return zero rows. We assert this with an integration test that an unset setting returns nothing (`20`).

> **Self-question:** RLS alone vs RLS + per-tenant connection pools? **Answer:** both. RLS prevents leaks; per-tenant connection pooling (PgBouncer pool-per-tenant *or* SET-app-value-per-request) limits one noisy tenant's effect on the cluster. For MVP, per-request `SET app.current_org_id` via a global FastAPI dependency suffices; v0.2 adds pool-per-tenant for the top-tier accounts (audit, retention scrub errors).

## 11. Migration strategy (Alembic)

- `infra/db/migrations/` — numbered, reviewed; **manual for RLS policies & tenant boundary**; `autogenerate` used only for table schemas.
- Baseline migration 0001 creates extensions + schemas + base tables + RLS skeleton.
- Each migration includes a **downgrade** that's tested in CI on a scratch DB.
- Tenant boundary changes (RLS policy edits) require a code review tag `tenant-change` and an extra PR review gate (`19`).
- Seed data: scenarios catalog YAML → loaded by `cybersim.tools.seed_catalog` (so catalog code stays the source of truth; the DB row is a denormalized cache).

## 12. Seed & fixtures

- `infra/db/seeds/`: minimal seed — one admin user, one free org, RLS sanity rows, MITRE knowledge slice (~50 techniques), OWASP top-10 entries, ~30 sampled CVEs from public sources (refs only).
- Fixtures for tests load scenarios in memory; they do **not** depend on DB state (deterministic replay from raw).

## 13. Retention & pruning

| Tier | Event retention | Snapshot retention | Audit retention |
|------|-----------------|--------------------|-----------------|
| Free | 7 days | 7 days | 90 days |
| Pro | 90 days | 90 days | 365 days |
| Enterprise | per contract (default 365 days) | 365 days | 7 years (compliance) |

Pruning job `cybersim.tools.prune` runs nightly; respects tier; never pruning audit rows below their floor.

## 14. Self-questioning & decisions (DB)

| Decision | Chosen | Rejected | Why |
|----------|--------|----------|-----|
| Single Postgres cluster | Yes | Separate per-tenant DBs | RLS + denormalized org_id suffices at MVP; per-tenant DB is ops overkill until very large tenants (`04` §2.5). |
| Events partitioned monthly by `received_at` | Yes | Partition by org or sim | Org/sim partitioning needs system-level mgmt; time partitioning suits both retention and the recent-read hot path. |
| Denormalize `org_id` on hot tables | Yes | Join via simulation_id | RLS evaluation cost + query speed. |
| Arrays (text[]) for node/edge refs | Yes | Join tables | Hot-path write/read trade favors arrays + GIN. |
| pgvector in same Postgres | Yes | Pinecone/Qdrant | `04` §2.7 — MVP cardinality; one backup. |
| Snapshot+delta for graph history | Yes | Only deltas + replay from seq 0 | Replay-from-zero is O(N); a full snapshot each Δt bounds replay cost. |
| RLS + per-request SET | Yes | Per-tenant DBs at MVP | Ops cost; revisit for top tenants (see §10 self-q). |
| Text + CHECK for enums | Yes | Postgres enum types | Dump portability; version migration lighter. |
| Alembic manual for RLS | Yes | autogen all | Tenant boundary changes are high-stakes. |

---

End of `09-database-schema.md`. Next: `10-graph-schema.md`.
