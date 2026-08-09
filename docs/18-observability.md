# 18 — Observability, SLOs, and Operations

CyberSim AI operational surfaces: structured logs, metrics, distributed traces, **LLM-specific tracing (Langfuse)**, alerting, runbooks, and SLOs. The aim is "every AI decision is reconstructable from end to end": a detection can be traced to events → graph deltas → LLM prompt hash → trace → RAG citations.

> **Normative:** OpenTelemetry as the contract everywhere; one pipeline → Tempo (traces), Loki (logs), Prometheus (metrics). LLM traces go to **Langfuse** (self-hosted) for prompt/token/cost drilldown. Grafana ties them with shared labels.

---

## 1. SLOs (v0.1)

| Service | SLI | SLO (rolling 28d) | Error budget |
|---------|-----|-------------------|--------------|
| API REST | availability (2xx/3xx) | 99.5% | 0.5% |
| API WS | session disconnect rate (non-user) | ≤1% | — |
| API REST `sim:read` latency | p95 ≤ 600 ms | 99% of requests | 1% |
| API REST `sim:respond` latency | p95 ≤ 4 s | 99% of requests | 1% |
| Analyst detection latency | event→detection p95 ≤ 8 s (`01` §7) | 95% of detections | 5% |
| Detection recall (seeded scout) | ≥ 95% (`20`) | — | — |
| Evidence coverage | 100% (`01` §7) | — | — |
| Knowledge refresh success | approximately daily | 99.5% of days | — |

If detection latency SLO breaches for a tenant (egress model), the runbook routes that tenant's traffic to the rule_fallback more aggressively (`11` §3.11).

## 2. Telemetry attributes (labels shared across logs/metrics/traces)

Always present: `env`, `version`, `org_id`, `service`. Per-category: `simulation_id`, `scenario_id`, `node`, `window_seq`. We treat `org_id`/`user_id` as confidential — scrubbed from remote exporters when env is prod and org_id matches a confidential-tier flag (privacy-by-config LLM trace export).

## 3. Metrics (Prometheus)

### 3.1 RED metrics per route
- `cybersim_http_requests_total{route,method,status,org_tier}`
- `cybersim_http_request_duration_seconds{route,method}` histogram (buckets: 5ms-30s)
- `cybersim_http_inflight{route}`

### 3.2 Use-case metrics
- `cybersim_ws_connections{org_id}`; `cybersim_ws_frames_sent_total{kind,channel}`
- `cybersim_events_ingested_total{simulator,subtype}`; `cybersim_events_normalized_lag_ms{}`; gauge `cybersim_bus_stream_lag{stream}`
- `cybersim_detections_total{threat_class,severity,source}`; `cybersim_detection_evidence_count` histogram
- `cybersim_detection_latency_seconds{stage}` — events-to-detection latency
- `cybersim_llm_calls_total{node,provider,model,outcome}`; `cybersim_llm_tokens_total{kind=in|out,model}`; `cybersim_llm_cost_micros_total{node}`
- `cybersim_validation_outcomes_total{kind,kind_class}` (raised by validator clamps)
- `cybersim_sim_running{org_id}` gauge; `cybersim_sim_started_total{scenario_id}`; `cybersim_sim_minutes_total{org_id}`
- `cybersim_graph_size_nodes` / `cybersim_graph_size_edges` per sim
- `cybersim_knowledge_query_seconds` histogram; `cybersim_knowledge_recall_k5_ratio`
- `cybersim_billing_entitlement_plans{plan}`

### 3.3 Alerting
- `n/a ≥0` on `detection_latency_seconds p95 > 8s for 5m` page analyst team
- `assert_no_validation_bypass > 0` raises (asserted in tests; if in prod, an emergency)
- `bus_lag_ms p95 > 2000ms for 5m` → oncall + worker scale
- `llm_provider_errors_rate 5m > 5%` → oncall; auto-fallback engaged telemetry visible
- `db_connections_active > 80%` max for 10m → scale/inspect
- Knowledge refresh failed 3 consecutive runs → oncall, degraded retrieval messages

## 4. Distributed tracing (OpenTelemetry → Tempo)
- Auto-instrument FastAPI (`opentelemetry-instrumentation-fastapi`), SQLAlchemy, Redis, `httpx` (LLM calls), Celery tasks.
- Manual spans for analyst nodes (`AnalystNode.span`), graph queries (`graph.attack_paths`), RAG retrieval (`knowledge.retrieve`).
- Tail-based sampling: keep 100% of traces with `error=true` OR `event...simulation_id ∈ annotated-mission` (high value) OR `latency > p95`, otherwise 10%. Keep recent missions' traces for replay/debugging.

## 5. Logging (structlog → JSON → Loki)
- Format: `{"ts","level","msg","attrs...}`. Always logs `env,version,service,org_id,simulation_id` when available.
- Log levels semantics:
  - `INFO` lifecycle & ops (sim start/stop, billing transition)
  - `WARNING` recoverable glitch or interection (LLM retry, validation re-route)
  - `ERROR` something failed; emitted to Sentry-tier (see below)
  - `DEBUG` dev-only mostly; gated by `LOG_LEVEL`
- We emit NO secrets: scrubbing filter (`infra/logging/scrub.py`) redacts known regex patterns (`(?i)(secret|password|token|api[_-]?key)`); we replace value with `***scrub***`.
- Sentry (or OTel → Sentry-compatible sink) for ERRORs of code origin issues (not user-facing); the same source-mapped both server+web (`@sentry/nextjs`, `sentry-sdk`).

## 6. LLM traces — Langfuse

- Langfuse receives traces per LLM call with tags `org_id, simulation_id, node, window_seq, prompt_hash, model, validated_outcome`.
- Each trace has spans: Prompt construction, Provider call, Parse, Validator reason, Retry (if any). Score `passed_validation`, `was_pruned`, `evidence_count`.
- Per detection, `detection.langfuse_trace_sets` (list). `08` GET detection includes a deep link to Langfuse for admins (off for member role; v0.2 audit-cohort role).
- Cost tracking per period aggregated by `org_id`; surfaced in billing metering (`16`).

## 7. Replay and reconstruction (because we promised it)
- Every run can be rebuilt: raw events (Postgres `events.raw?` + retention), canonical events (`events`), graph snapshots/deltas, executed_actions, LLM traces (Langfuse), knowledge refresh state.
- `cybersim.tools.replay <sim_id>` CLI reconstructs to a JSON bundle; admin UI exports the bundle (`08` §4.10).
- A `verify-replay <sim_id> baseline.json` test asserts that replay equals the recorded post-run artifacts (modulo received_at_ms, RnG bits) — encoded in the test suite (`20`).

## 8. Dashboards (Grafana) shipped as code
- **Operational Overview** (RED, WS, queue depth, latency)
- **Analyst health** (LLM calls/costs/latency/errors, validation outcome breakdown, detection latency, evidence histogram, fallback ratio)
- **Simulations** (active per org, scenario mix, sim_minutes, errors by simulator)
- **Knowledge** (entry count, last refresh, query latency, recall@5)
- **Billing** (active plans, metered usage deltas, failed webhook retries)
- **Real-time bus** (stream lengths, consumer lag, dropped frames)

## 9. On-call runbook summary (full in `infra/runbooks/`)
- **`AI_TIER_DEGRADED`**: check LLM provider status; ensure fallback indicator visible; thinned routing; trace sample of failures; transit sit to the user via WS `sim.status`.
- **`DETECTION_LATENCY_HIGH`**: graph repo cache hit rate; LLM concurrency saturation; replay-per-tenant; cap analytical LLM concurrency.
- **`STREAM_LAG`**: scale normalizer; inspect PG write throughput; check upsert batching.
- **`VALIDATOR_REJECTION_SPIKE`**: likely prompt regression; check `prompt_hash` distribution; hotfix strict-prompt; if persists, switch to rule_fallback only.
- **`TENANT_BURST`**: an org clamoring heavy sims; entitlement caps should self-limit; if bypassed, manual throttle via feature flag.

## 10. Self-questioning & decisions (observability)

| Decision | Chosen | Rejected | Why |
|----------|--------|----------|-----|
| OTel + Tempo/Loki/Prom as one pipeline | Yes | multiple vendor SDKs | Single exporter set; swappable |
| Langfuse separate from generic traces | Yes | bake LLM into Tempo | multi-tenant prompt explorer + cost; richer context |
| Tail-based sampling | Yes | head-based % | Preserves rare-but-important traces (errors, missions) |
| Replay test asserts end-to-end reconstruction | Yes | no replay test | Promised reproducibility; cheap to assert |
| Structured logs only; no print() | Yes | ad-hoc | Parseable + scraper; onboarding velocity |
| Secret scrubbing at log boundary (not after format) | Yes | regex-on-output only | Defense-in-depth: avoid leak in unhandled paths |
| Auto-instrumentation + manual node spans | Yes | all manual | Development velocity |
| Detection latency SLO + rollback to fallback | Yes | no SLO | Aligns product story ("≤ 8s p95 detection") |

---

End of `18-observability.md`. Next: `19-development-roadmap.md`.
