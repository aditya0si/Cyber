# 08 — Backend API Specification

The CyberSim AI public/first-party API surface served by the FastAPI gateway: REST + WebSocket, auth, multi-tenant conventions, errors, rate limits, idempotency, and OpenAPI generation. The web app (`13`) consumes this via a typed client generated from the OpenAPI schema (`openapi-typescript`). This doc is the contract; code must match these route paths, methods, and shapes exactly.

> **Conventions reminder:** `org_id` is never trusted from request bodies or query strings — it is resolved solely from the verified JWT. All IDs are string-formatted UUIDv7. All timestamps are ISO-8601 UTC strings ending in `Z`.

---

## 1. Base & versioning

- **Base URL:** `https://api.cybersim.ai` (prod). Local/dev: `http://localhost:8000`.
- **Path prefix:** `/v1` for everything except auth bootstrap and webhooks. `v2` is reserved.
- **Versioning policy:** additive changes only within a major version. Breaking change ⇒ `v2`. We include a contract test suite (`20`) that snapshots OpenAPI on each PR; breaking changes fail CI.
- **Content type:** `application/json` for REST bodies; `application/octet-stream` for raw exports. WS frames are JSON text frames.
- **OpenAPI doc at `/v1/openapi.json`**; human docs at `/v1/docs` (dev), disabled in prod by env flag `DOCS_PUBLIC=false`. The frontend client is regenerated in CI from `/v1/openapi.json` into `apps/web/src/lib/api/schema.ts`.

## 2. Authentication & authorization

### 2.1 AuthN
- **OAuth2 password flow + refresh tokens** (default). **Optional WebAuthn (passkey)** login; both yield the same token shape.
- **Access token:** signed JWT (RS256; JWKS endpoint `/v1/.well-known/jwks.json`), 15min TTL. Claims: `sub`(user_id), `org_id`, `org_role`, `scopes[]`, `sid`(session id), `typ:"access"`.
- **Refresh token:** opaque, server-stored, rotating; 30d TTL; one-time use with reuse detection (rotated: invalid prior refresh + audit event + force re-login on reuse on a new UA). Endpoint: `POST /v1/auth/refresh`.
- **WS auth:** one-time WS ticket (`POST /v1/auth/ws-ticket`) — short-lived (≤60s), bound to `session_sid`; WS connects with the ticket in a `subprotocol` header; one subscription per ticket; re-fetch on expiry.
- **SSO (enterprise tier, future):** SAML/OIDC flows produce the same JWT shape; mapping to `org_id`/role is a v0.2 adapter behind `cybersim.platform.auth.IdP`.

### 2.2 AuthZ
- **Roles (org-level):** `admin`, `member`, `analyst`, `viewer` (v0.1 ships `admin` + `member`; `analyst`/`viewer` optional later). RBAC enforced at the route guard layer and **double-checked via RLS** (`09`, `15`).
- **Scopes:** coarse capability tokens (`sim:run`, `sim:read`, `sim:respond`, `mission:manage`, `billing:manage`, `org:admin`). Endpoint requirements documented per route below.
- **Resource scoping:** every object is owned by `org_id`; the JWT claim gates the policy. Cross-org access returns `403 forbidden`.

### 2.3 Header conventions
| Header | Required? | Notes |
|--------|-----------|-------|
| `Authorization: Bearer <jwt>` | all REST except auth bootstrap | |
| `Idempotency-Key: <uuidv7-or-client-uuid>` | all non-GET mutating endpoints | dedupes retries; 24h cache |
| `X-Request-ID: <uuid>` | optional, returned if absent | propagates tracing |
| `Accept-Language` | optional | i18n keys returned; default `en` |

## 3. Standard error format (RFC-9457 Problem Details, extended)

```json
{
  "type":   "https://errors.cybersim.ai/v1/simulation/running",
  "title":  "Simulation already running",
  "status": 409,
  "detail": "A simulation with scenario 'web.app.sqli_login' is already running for this org.",
  "instance": "/v1/simulations",
  "code":   "SIMULATION.RUNNING",
  "trace_id": "01J9...",
  "violations": null
}
```
Validation errors set `violations: [{field, code, message}]`.
We use a global exception handler → error code taxonomy in `infra/errors/codes.py`; the *code* is the stable identifier for clients (paths may evolve).

## 4. Resources (REST)

### 4.1 Auth
| Method | Path | Scope | Description |
|--------|------|-------|-------------|
| `POST` | `/v1/auth/register` | none | create user + first org (becomes admin) |
| `POST` | `/v1/auth/login` | none | password login; returns tokens |
| `POST` | `/v1/auth/webauthn/begin` | none | begin passkey registration (challenge) |
| `POST` | `/v1/auth/webauthn/finish` | none | finish passkey registration |
| `POST` | `/v1/auth/webauthn/login` | none | passkey login |
| `POST` | `/v1/auth/refresh` | refresh | rotate refresh token; return access |
| `POST` | `/v1/auth/logout` | any | invalidate refresh + session |
| `POST` | `/v1/auth/ws-ticket` | any | get short-lived WS ticket |
| `GET`  | `/v1/me` | any | user profile, orgs, entitlements snapshot |

### 4.2 Organizations & users
| Method | Path | Scope | Description |
|--------|------|-------|-------------|
| `GET`    | `/v1/orgs/{org_id}` | `org:admin` | org details, plan, usage |
| `PATCH`  | `/v1/orgs/{org_id}` | `org:admin` | update org (name, default_density) |
| `GET`    | `/v1/orgs/{org_id}/members` | `org:admin` | list members |
| `POST`   | `/v1/orgs/{org_id}/invites` | `org:admin` | invite user |
| `DELETE` | `/v1/orgs/{org_id}/members/{user_id}` | `org:admin` | remove member |
| `PATCH`  | `/v1/orgs/{org_id}/members/{user_id}` | `org:admin` | change role |

### 4.3 Scenarios (catalog)
| Method | Path | Scope | Description |
|--------|------|-------|-------------|
| `GET` | `/v1/scenarios` | `sim:read` | list (filter by `simulator`, `category`, `difficulty`) |
| `GET` | `/v1/scenarios/{scenario_id}` | `sim:read` | full scenario + env template (sanitized: no `expected_detections` exposed) |
| `GET` | `/v1/scenarios/{scenario_id}/preview-graph` | `sim:read` | initial environment graph (for UI) |

### 4.4 Simulations
| Method | Path | Scope | Description |
|--------|------|-------|-------------|
| `POST`   | `/v1/simulations` | `sim:run` | create + start. Body: `{scenario_id, params?, seed?, label?}`. Returns `202` with `simulation_id` and WS subscription URL. **Idempotency-Key honored.** |
| `GET`    | `/v1/simulations` | `sim:read` | list (cursor pagination, filters `status`, `scenario_id`, `from`, `to`) |
| `GET`    | `/v1/simulations/{sim_id}` | `sim:read` | detail + status + counts (events, detections, actions) |
| `POST`   | `/v1/simulations/{sim_id}/pause` | `sim:run` | pause (no events) |
| `POST`   | `/v1/simulations/{sim_id}/resume` | `sim:run` | resume |
| `POST`   | `/v1/simulations/{sim_id}/stop` | `sim:run` | stop end-of-sim |
| `DELETE` | `/v1/simulations/{sim_id}` | `sim:run` | soft delete (retain for 30d per tier retention) |
| `GET`    | `/v1/simulations/{sim_id}/events?cursor&limit&category&severity&since_seq` | `sim:read` | paginate canonical events (cache-greedy 60s) |
| `GET`    | `/v1/simulations/{sim_id}/events/stream-tail?limit=200` | `sim:read` | initial tail to seed the UI before WS |

### 4.5 Detections
| Method | Path | Scope | Description |
|--------|------|-------|-------------|
| `GET`   | `/v1/simulations/{sim_id}/detections` | `sim:read` | list detections |
| `GET`   | `/v1/simulations/{sim_id}/detections/{d_id}` | `sim:read` | full detection + evidence + recommended actions |
| `POST`  | `/v1/simulations/{sim_id}/detections/{d_id}/follow-up` | `sim:read` | ask the analyst a follow-up question; body `{prompt, evidence_refs?: [], graph_ref?: ""}`; returns SSE stream of answer card |
| `POST`  | `/v1/simulations/{sim_id}/detections/{d_id}/execute` | `sim:respond` | Execute a recommended response. Body `{action_id}`. Validates + applies + emits response-effected events. Returns `202` with `execution_id`. |

### 4.6 Attack graph
| Method | Path | Scope | Description |
|--------|------|-------|-------------|
| `GET` | `/v1/simulations/{sim_id}/graph` | `sim:read` | current full graph (nodes + edges + foothold state) snapshot |
| `GET` | `/v1/simulations/{sim_id}/graph/snapshot?at_time_ms` | `sim:read` | historical snapshot at sim time |
| `GET` | `/v1/simulations/{sim_id}/graph/paths?src={node}&dst={node}&k=5` | `sim:read` | simple-paths query (bounded `k`, depth-limited) |
| `GET` | `/v1/simulations/{sim_id}/graph/deltas?from_seq=&to_seq=` | `sim:read` | graph delta sequence for SCRUB replay |

### 4.7 Knowledge (RAG)
| Method | Path | Scope | Description |
|--------|------|-------|-------------|
| `GET` | `/v1/knowledge/search?q=...&kind=...` | `sim:read` | search knowledge; returns ranked cited items |
| `GET` | `/v1/knowledge/entries/{entry_id}` | `sim:read` | entry (single cited doc chunk) |

### 4.8 Missions
| Method | Path | Scope | Description |
|--------|------|-------|-------------|
| `GET` | `/v1/missions` | `sim:read` | list missions |
| `GET` | `/v1/missions/{mission_id}` | `sim:read` | mission detail (objectives, scoring config) |
| `POST` | `/v1/missions/{mission_id}/start` | `sim:run` | start a simulation that's a mission (returns simulation_id + judgeable share URL if public) |
| `GET` | `/v1/missions/{sim_id}/score` | `sim:read` | live + final score; updates as the simulation progresses |

> Mission flow, share links, autoplay: see `14`.

### 4.9 Billing & entitlements (see `16`)
| Method | Path | Scope | Description |
|--------|------|-------|-------------|
| `GET`   | `/v1/billing/plan` | `billing:manage` | current plan, entitlements, current period usage |
| `POST`  | `/v1/billing/checkout` | `billing:manage` | create Stripe Checkout Session |
| `POST`  | `/v1/billing/portal` | `billing:manage` | Stripe Customer Portal URL |
| `POST`  | `/v1/billing/webhook` | (Stripe signed) | Stripe webhook receiver; trusts `Stripe-Signature` only |

### 4.10 Exports / replay
| Method | Path | Scope | Description |
|--------|------|-------|-------------|
| `GET` | `/v1/simulations/{sim_id}/export` | `sim:read` | async export; returns `202` + `export_id` then posts a download URL via WS when done |
| `GET` | `/v1/exports/{export_id}` | `sim:read` | download bundle (URL short-lived; S3/R2 pre-signed) |

---

## 5. WebSocket protocol

`wss://api.cybersim.ai/v1/ws?ticket=<ws-ticket>` (one connection per ticket; multi-tenant isolation enforced server-side).

### 5.1 Client→server frames
```json
{"kind":"subscribe","channel":"sim.{sim_id}","cursors":{"events": 0, "graph": null}}
{"kind":"unsubscribe","channel":"sim.{sim_id}"}
{"kind":"ping"}
```
`cursors.events` = last sequence acknowledged; server resumes from there. Server-side coalescing cap: 4 msg/sec per sub; client may set a lower cap via `coalesce_ms`.

### 5.2 Server→client frames (all carry `channel`, `sim_id`, `seq` when applicable)
| `kind` | When | Body |
|--------|------|------|
| `hello` | on connect | `{ticket_exp_ms, server_time_ms, deps}` |
| `event.upsert` | new canonical event | `CanonicalEvent` (`07`) |
| `event.batch` | coalesced batch (preferred under burst) | `events: CanonicalEvent[]` (≤32) |
| `detection.created` | new detection | `Detection` (`11`) |
| `graph.delta` | graph state changed | `{added_nodes?, added_edges?, updated_footholds?, snapshot_seq, from_seq, to_seq}` |
| `action.executed` | response applied | `ExecutionAcknowledgement` (`14`) |
| `sim.status` | phase changes | `{status, phase, reason?}` |
| `sim.lag` | bus lag indication | `{lag_ms}` (≥ every 5s when lag >0) |
| `score.update` | mission only | `{score}` |
| `done` | channel closed | channel closed cleanly |
| `error` | protocol violation / auth | `{code, detail}` |

### 5.3 Channel vocabulary
- `sim.{sim_id}` → all sub-streams for a simulation (events + detections + graph + actions + status). Default subscribe.
- Granular subs: `sim.{sim_id}.events`, `.detections`, `.graph`, `.actions`, `.score` (these exist as fine-grained channels; `sim.{id}` is the union).

### 5.4 Rate-limiting / coalescing rules (server)
- Per connection: ≤32 frames/sec sustained; bursts ≤64 (then 16ms defer). Triggers of `429:frame-coalesce` are not errors — we coalesce in batches.
- Backpressure: if a client has unread frames >100, server sends `error: FRAME_BUFFER_OVERFLOW` and closes the subscription (not the socket).

## 6. REST rate limits (per org / per user)

| Bucket | Anonymous | Auth (default) | Pro | Enterprise |
|--------|-----------|------------------|-----|------------|
| Auth endpoints | 5/min | — | — | — |
| `sim:run` (sims started) | — | 20/hr | 200/hr | per-contract |
| `sim:read` GET | — | 600/min | 2000/min | per-contract |
| `sim:respond` | — | 60/min | 300/min | per-contract |
| Analyst follow-up (`POST .../follow-up`) | — | 30/min | 120/min | per-contract |
| Knowledge search | — | 60/min | 300/min | per-contract |
| Exports | — | 10/hr | 60/hr | per-contract |

Headers on each response: `RateLimit-Limit`, `RateLimit-Remaining`, `RateLimit-Reset` (or `X-RateLimit-*` legacy parity). `429` returns problem details with `Retry-After`.

## 7. Idempotency semantics

- `Idempotency-Key` on `POST /v1/simulations`, `POST .../execute`, `POST /v1/billing/checkout`, `POST /v1/missions/{id}/start`.
- Server stores keyed `(key, response)` for 24h in Redis (org-scoped). Replay returns the cached response (including same `simulation_id`). Mutations applied once; double-submit returns the memoized result.
- Insufficient headers ⇒ `400` with `code=IDEMPOTENCY_KEY_REQUIRED` on the listed endpoints.

## 8. Pagination

- **Cursor pagination** for `GET .../events`, `GET .../detections`, list endpoints. Cursor is opaque base64 of `(sequence, id)` for ordering stability.
- Query params: `?limit=` (max 500) `?cursor=`; response has `{items, next_cursor, has_more, total_estimate}`.
- `total_estimate` is approximate (Postgresql `SQL_CALC` avoided; we offer count only when `?count=true`, costing an extra query).

## 9. ETag & caching

- `GET` endpoints emit `ETag` (weak) computed from max updated_at + count; `GET .../graph` computes from `graph_seq`.
- `GET .../events` is cache-greedy for backfill: 60s. Live tail uses WS, not polling.

## 10. Health & ops
- `GET /healthz` (no auth): `{status:"ok"}` if API can reach Postgres + Redis; `503` otherwise (+ dependency breakdown).
- `GET /readyz`: includes warm graph cache size, queue depths, LLM provider health (lightweight ping, cached 30s).
- `GET /v1/.well-known/jwks.json`: JWKS for JWT verification (cached, rotated on key roll).

## 11. CORS

- Dev: allow `http://localhost:3000`.
- Prod: allow only our first-party origins (`https://app.cybersim.ai`, `https://cybersim.ai`); webhooks bypass CORS.

## 12. Sample contracts (request/response excerpts)

### 12.1 `POST /v1/simulations`
Request:
```json
{
  "scenario_id": "web.app.sqli_login",
  "params": { "request_rate_per_sec": 4, "noise_ratio": 0.2, "attacker_skill":"intermediate" },
  "seed": 7,
  "label": "Stakeholder demo 2026-08-09"
}
```
Response `202`:
```json
{
  "simulation_id": "01J9Z...",
  "status": "running",
  "ws_channel": "sim.01J9Z...",
  "scenario": { "id":"web.app.sqli_login","display":{...} },
  "graph_seed_seq": 0,
  "entitlements": { "max_concurrent_sims": 5, "ai_tier": "default" }
}
```

### 12.2 Detection (subset of `11` schema returned by GET)
```json
{
  "detection_id":"01J9Zd...",
  "simulation_id":"01J9Z...",
  "created_at":"2026-08-09T14:03:11Z",
  "threat_class":"credential_compromise",
  "title":"Credential compromise followed by privilege escalation",
  "severity":"high",
  "confidence":0.91,
  "confidence_band":"high",
  "mitre":[ "T1110","T1078" ],
  "owasp":[ "A07:2021" ],
  "attack_path":[
    {"node":"zone_internet_attacker","label":"Internet"},
    {"node":"lb1","label":"Load Balancer"},
    {"node":"login_ep","label":"Auth endpoint"},
    {"node":"users_db","label":"Database"}
  ],
  "evidence":[
    {"label":"repeated_failed_logins","event_ids":["01J9a1...","01J9a2..."],"count":17,"weight":0.9},
    {"label":"successful_login_from_new_location","event_ids":["01J9b1..."],"weight":0.85},
    {"label":"privilege_escalation","event_ids":["01J9c1..."],"weight":0.95}
  ],
  "rationale":"17 anomalous requests from 203.0.113.42 within 4s, …",
  "recommended_actions":[
    {"action_id":"block_source_ip","title":"Block source IP","risk":"low","reversible":true},
    {"action_id":"rate_limit_endpoint","title":"Rate-limit /login","risk":"low","reversible":true},
    {"action_id":"rotate_credentials","title":"Rotate exposed credentials","risk":"medium","reversible":false},
    {"action_id":"inspect_db_logs","title":"Inspect database access logs","risk":"none","reversible":true}
  ],
  "source":"ai",                  // "ai" | "rules" (degraded)
  "validated":true
}
```

### 12.3 `POST .../execute` Response `202`
```json
{
  "execution_id":"01J9Xe...",
  "detection_id":"01J9Zd...",
  "action_id":"block_source_ip",
  "applied_at":"2026-08-09T14:04:01Z",
  "ack_channel":"sim.01J9Z.../actions"
}
```

## 13. Self-questioning & decisions (API)

| Decision | Chosen | Rejected | Why |
|----------|--------|----------|-----|
| REST + WS hybrid (vs. all-stream) | Yes | All-stream / tRPC | WS only for what's live; REST is the boring-tested default; OpenAPI→typed client. |
| JWT in-house | Yes | Clerk/Auth0 | Tenant boundary control + audit (`04` §2.16). |
| WS fan-out via Redis pub/sub | Yes | Sticky sessions | Multi-instance scale + clean deploys (`03` §8.2). |
| `Idempotency-Key` mandatory on listed mutations | Yes | Optional | Demoers & jitter retry; sim start must be dedup-safe. |
| RFC 9457 Problem Details | Yes | ad-hoc `{error:...}` | Standard, well-tooled; `code` is stable identifier. |
| Cursor pagination always | Yes | Offset + LIMIT | Stability cost > slight cost; `events` reads are hot. |
| Coalesced `event.batch` WS frame | Yes | Single events only | Burst scenarios (brute force) would thrash UI; coalesce keeps UX fluid + AT-friendly (`02` §7). |
| `/v1/docs` disabled in prod | Yes | Public docs | Reduce attack surface (still emit `/openapi.json` to authenticated internal CI). |
| Detection exposes `source: ai|rules` | Yes | hide | Trust + cost-cut explanation; honest about degradation. |

---

End of `08-backend-api-spec.md`. Next: `09-database-schema.md`.
