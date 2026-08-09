# 07 — Event Schema & Normalization

The **canonical event** is the universal contract between every simulator and the rest of the platform. This doc defines it as a normative Pydantic model, the normalization rules that transform raw simulator events into canonical ones, the event bus's delivery guarantees, idempotency, severity hints, MITRE tagging, and replay semantics.

> **The rule:** No component outside `cybersim/events/` constructs a `CanonicalEvent`. No component reads `RawEvent` except the normalizer. The normalizer is the contract enforcer.

---

## 1. The canonical event (`cybersim.events.schema`)

```python
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict
from typing import Annotated

class EventCategory(str, Enum):
    NETWORK      = "network"        # net.connection, net.scan_probe, net.service_discovered
    AUTH          = "auth"          # auth.attempt, auth.success, session.created
    HTTP          = "http"          # http.request, http.error
    DATABASE      = "database"      # db.query, db.error
    API           = "api"           # api.request, api.authz, api.rate.window, api.data_response
    HOST          = "host"          # host.login_attempt, host.session, host.process_spawn, net.lateral_hop
    PACKAGE       = "package"       # build.dependency_resolve, package.installed, package.lifecycle.hook
    PROCESS       = "process"       # process.exec, process.env_exfil
    SYSTEM        = "system"        # sim.start, sim.end, response.* (executor-originated)
    ANALYST       = "analyst"       # analyst.detection (publish mirror), analyst.decision

class Severity(str, Enum):
    INFO = "info"; LOW = "low"; MEDIUM = "medium"; HIGH = "high"; CRITICAL = "critical"

class AttackStage(str, Enum):
    RECON          = "reconnaissance"
    INITIAL_ACCESS = "initial_access"
    EXECUTION      = "execution"
    PERSISTENCE     = "persistence"
    CRED_ACCESS    = "credential_access"
    DISCOVERY      = "discovery"
    LATERAL         = "lateral_movement"
    PRIV_ESCAL     = "privilege_escalation"
    EXFIL          = "exfiltration"
    IMPACT         = "impact"
    BENIGN         = "benign"

class CanonicalEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    # ---- Identity -----------------------------------------------------
    event_id:         UUIDv7Str                                # globally unique, time-ordered
    simulation_id:    UUIDv7Str
    org_id:           str
    sequence:         int = Field(ge=0)                        # strictly increasing within sim
    sim_time_ms:      int = Field(ge=0)                        # sim clock millis (deterministic)
    received_at_ms:   int                                       # wall clock ingestion; for lag metrics

    # ---- Classification ----------------------------------------------
    origin:           str                                       # web|api|network|supply|exec|analyst|platform
    raw_type:         str                                       # raw type from simulator (e.g., http.request)
    category:         EventCategory
    subtype:          str                                       # canonical subtype (e.g., sql_injection_indicator)
    severity_hint:    Severity                                  # deterministic hint pre-LLM (see §5)
    attack_stage:     AttackStage | None = None                 # inferred; None for purely benign

    # ---- Graph linkage ------------------------------------------------
    target_node_ids:  list[str] = Field(default_factory=list)   # affected graph nodes (assets/services/creds/data)
    source_node_id:   str | None = None                        # source/origin node id if known (e.g., attacker zone)
    via_edge_ids:     list[str] = Field(default_factory=list)   # overlay edges this event implicates

    # ---- MITRE/OWASP labelling --------------------------------------
    mitre_tactics:    list[str] = Field(default_factory=list)   # TA-IDs, e.g., ["TA0001"]
    mitre_techniques: list[str] = Field(default_factory=list)   # T-IDs, e.g., ["T1190","T1110"]
    owasp_refs:       list[str] = Field(default_factory=list)   # e.g., ["A03:2021"]

    # ---- Payload ------------------------------------------------------
    payload:          dict = Field(description="Type-specific structured payload (JSON).")
    raw_ref:          str | None = None                         # object-store ref to original RawEvent (audit)

    # ---- Provenance ---------------------------------------------------
    correlation_key:  str | None = None                        # joinable identity across events (src_ip/cred_id/...)
    benign:           bool = False                             # explicit benign flag (drives FP discipline)
```

### 1.1 Why these fields, and not others

> **Self-question:** Are 26 fields too many? Should we move `mitre_*`, `owasp_refs`, `severity_hint`, `attack_stage` *out of the event* and into the analyst? **Answer:** Considered seriously. They *are* the deterministic pre-LLM attributes the analyst *and the rule-based fallback* rely on; keeping them on the event means (a) the fallback can reach a sensible near-detection without the LLM, (b) the dashboard can group/MITRE-filter without round-tripping through the analyst, (c) replay is verifiable independent of LLM nondeterminism. Cost: richer event write; benefit: dramatically simpler/read-only dashboard logic and degradation. Accept the cost.

> **Self-question:** Is `severity_hint` (deterministic) redundant with the AI's `severity` (in `Detection`)? **Answer:** No — they are intentionally two layers. `severity_hint` is per-event and *lower* bound; the AI severity is per-detection (chain-level), and the validator clamps against graph distance (`05` §6.1). Having both shows the system has a deterministic floor even when AI is offline.

### 1.2 Payloads are typed-by-category
Payloads are not free `dict`s forever — each `category` ships a payload schema in `cybersim/events/payloads/*.py` (e.g., `HTTPPayload`, `DBQueryPayload`, `AuthAttemptPayload`, `NetConnectionPayload`, `PackageLifecycleHookPayload`). The normalizer parses into the payload model, *then* re-emits the dict for storage. This gives us schema validation on ingestion (catches simulator bugs at the seam) and lets the dashboard/benchmarks read typed shapes without re-parsing.

## 2. Raw → canonical normalization rules

`cybersim.events.normalizer.Normalizer.normalize(raw: RawEvent, env: EnvironmentGraph) -> CanonicalEvent`

### 2.1 Deterministic transformations

| Step | Input | Output | Rule |
|------|-------|--------|------|
| 1. Dedup by raw `id` | `(raw.id)` | skip if seen | Idempotent: an event re-delivered (at-least-once bus) produces zero new rows. |
| 2. Assign sequence | sim-scoped monotonic | `sequence` | Strict-increasing per sim; deterministic ordering by `sim_time_ms`, then by raw emission order tiebreak. |
| 3. Assign category/subtype | `raw_type` → map | `category`, `subtype` | Static dispatch table `cybersim/events/mapping.py`. |
| 4. Resolve graph nodes | `raw.node_ref`, `entity ids` | `target_node_ids`, `source_node_id`, `via_edge_ids` | Looks up env graph; opaque raw refs become canonical node IDs; ambiguous refs emit a `normalize.warning` telemetry event and use best-match + lower confidence. |
| 5. Severity hint | raw attrs + env | `severity_hint` | Rubric in §5; deterministic. |
| 6. Attack stage | subtype map | `attack_stage` | Lookup table; `None` if benign. |
| 7. MITRE/OWASP tags | subtype + attrs | `mitre_*`, `owasp_refs` | Lookup from `cybersim.graph.mitre.Mapping` and owasp cross-ref `05` §4.2/§4.3 (deterministic). |
| 8. Correlation key | dominant identity | `correlation_key` | Composite: e.g., `src_ip=203.0.113.42`, `cred_id=admin_creds`, `token_id=...`. Lets analyst join events cheaply. |
| 9. Benign flag | scenario noise config | `benign` | If the simulator tagged the raw event as `noise=true`, set `benign=True`, `attack_stage=AttackStage.BENIGN`. |
| 10. Persist + republish | — | canonical | Insert into `events` (Postgres) — idempotent on `(event_id)`; publish to `canonical.events.<sim>`. |

### 2.2 Severity rubric applied at the normalizer (per-event hint)
(Refines `05` §6.1 to per-event granularity.)

| Trigger | Hint |
|---------|------|
| `db.error` correlated with suspicious payload | high |
| `auth.attempt.success=false` burst (≥5/min/same IP) | medium |
| `auth.success` from a known attacker `correlation_key` *after* failed burst | critical (potential compromise) |
| `http.request` with `body.username` matching SQLi regex + `sqli_vulnerable=true` | high |
| `net.scan_probe` (SYN scan over N ports) | medium (recon) |
| `net.lateral_hop` | high |
| `package.lifecycle.hook` + outbound net to non-allow-listed registry | critical |
| `process.env_exfil` patterns matched | critical |
| Explicit benign tag | info |
| else (uncategorized) | info |

The hint is **lowerbound** of evidence; the AI can raise severity at detection time but never below the hint + graph-distance clamp.

## 3. Subtype dispatch table (canonical mapping)

```python
# cybersim/events/mapping.py  (excerpt)
RAW_TYPE_TO_SUBTYPE = {
  ("web","http.request"):   ("http","http_request"),
  ("web","http.error"):     ("http","http_error"),
  ("web","db.query"):       ("database","db_query"),
  ("web","db.error"):       ("database","db_error"),
  ("web","auth.attempt"):   ("auth","auth_attempt"),
  ("web","auth.success"):   ("auth","auth_success"),
  ("web","session.created"):("auth","session_created"),
  ("api","api.request"):    ("api","api_request"),
  ("api","api.authz"):      ("api","api_authz"),
  ("api","api.rate.window"):("api","api_rate_window"),
  ("api","api.data_response"):("api","api_data_response"),
  ("network","net.connection"):("network","net_connection"),
  ("network","net.scan_probe"):("network","net_scan_probe"),
  ("network","net.service_discovered"):("network","net_service_discovered"),
  ("network","host.login_attempt"):("host","host_login_attempt"),
  ("network","host.session"):("host","host_session"),
  ("network","host.process_spawn"):("host","host_process_spawn"),
  ("network","net.lateral_hop"):("host","net_lateral_hop"),
  ("supply","build.dependency_resolve"):("package","build_dependency_resolve"),
  ("supply","package.installed"):("package","package_installed"),
  ("supply","package.lifecycle.hook"):("package","package_lifecycle_hook"),
  ("supply","process.exec"):("process","process_exec"),
  ("supply","process.env_exfil"):("process","process_env_exfil"),
  ("exec","response.applied"):("system","response_applied"),
  ("analyst","detection.created"):("analyst","detection_created"),
}
```

A scenario subtype like `sql_injection_indicator` is derived in step 7 when a regex detector matches a payload; subtypes can be *indicator* subtypes (signals derived in normalizer) on top of the *carrier* subtypes above. The latter describes the event nature; the former the *suspected semantic*.

## 4. The event bus (`cybersim.events.bus`)

- **Transport:** Redis Streams. Two physical streams per simulation:
  - `events.raw.<org_id>.<sim_id>` — simulator → normalizer
  - `canonical.events.<org_id>.<sim_id>` — normalizer → (consumers: dashboard WS hub, analyst, graph engine)
- **Consumer groups:**
  - Group `normalizer`: 1+ consumers; at-least-once via XACK on processed; dedup by raw.id in PK.
  - Group `analyst`: 1+ consumers; idempotent ingestion keyed on `event_id`.
  - Group `graph`: 1 consumer per simulation (graph state must serialize per-sim); partitions by `sim_id`.
- **Ordering:** Redis Streams preserve per-stream order; consumer groups process in order; downstream consumers honor `sequence` strictly.
- **Backpressure:** producers publish if `XLEN < HARD_LIMIT` (per-stream); else throttle sim scheduler (`06` beats). BUS emits a `bus.lag` metric to OTel (`18`).
- **Replay:** `events.raw.*` and `events` table together allow full replay from raw → canonical → graph deltas → detection. Replay tool: `cybersim.tools.replay` CLI.

### 4.1 Delivery guarantees (normative)
1. **At-least-once** between sim and normalizer (Redis Streams + XACK). Dedup makes this effectively-exactly-once for state.
2. **At-least-once** between normalizer and consumers; idempotency on `event_id` everywhere.
3. **No parallel reordering** within a sim/stream; inter-sim parallelism is allowed (independent streams).
4. **Persistence:** raw stream retained ≥72h OR until sim end + N mins (configurable; retention ≥ catalog persistence tier). Canonical events live in Postgres indefinitely (subject to retention policy in `15`).

> **Self-question:** Why Redis Streams over Kafka when Kafka gives stronger guarantees? **Answer:** See `04` §6.2 — operational cost. Redis Streams + idempotency + dedup gives us "at-least-once → effectively once" at MVP cardinality; Kafka is a `04`-named seam swap when an env demands it.

## 5. Severity rubric (per-event) — formal

(included above §2.2; referenced as authoritative here)

## 6. Enrichment hooks (optional, deterministic)

Normalizer allows pluggable, **deterministic** enrichers (`Enricher` protocol). Built-in:
- `IPGeoEnricher` (offline MaxMind GeoLite2 shipped modulo licensing; falls back to stubbed synthetic geo consistent per `correlation_key`)
- `UserAgentParserEnricher` (offline UA parser → normalized `device_type`, `ua_family`; never a network call)
- `AppNameResolverEnricher` (resolve service `endpoint` → friendly name from env template)

> No enricher may call a network service at runtime. Pre-commit guard for network imports in the enricher package (`20`). Geo is *simulated* AGB consistent — `corrrelation_key`-keyed synthetic. This preserves the safety/reproducibility promise.

## 7. Replay semantics (`replay` contract)

For any `(simulation_id)`:
```
replay(simulation_id):
  load canonical events ordered by sequence
  rebuild environment graph from scenario env + executed actions (from actions.<sim>)
  re-apply each canonical event to graph (NEUTRAL start) to reproduce deltas
  => identically-updated environment graph (byte-identical nodes/edges snapshot delta sequence)
```
Determinism audit (`20`): for two runs of the same `(scenario, seed)` from catalog, canonical event sequence sets must match modulo `received_at_ms` and `event_id`'s RNG bits—but those are excluded from comparators. The normalized *content* of each event's payload + tags must be equal.

## 8. Self-questioning & decisions (events)

| Decision | Chosen | Rejected | Why |
|----------|--------|----------|-----|
| Monomorphic `CanonicalEvent` | Yes (one model) | Per-category events | One table — easier replay/RAG/dashboard; subtypes still typed via payload model. |
| Deterministic fields on event (`severity_hint`, tags) | Yes | Compute in analyst only | Honest degradation + dashboard independence from LLM (`01` §3). |
| `benign` first-class | Yes | absence only | Active FP discipline (`05` §4.1, `02` §4.4). |
| Raw + canonical both kept | Yes | Canonical only | Replay from raw protects against normalizer-bug-induced data loss; cheap due to Postgres+object storage. |
| Redis Streams bus | Yes | Kafka / PG LISTEN/NOTIFY | MVP ops envelope; idempotency covers at-most/effectively-once (`04` §6.2). |
| Enrichers offline-only | Yes | network enrichment | Safety + reproducibility (`01` §8). |
| Payload typed via sub-models | Yes | `dict[str,Any]` | Schema enforcement at the seam catches simulator bugs early. |
| `event_id = UUIDv7` deterministic-minted | Yes | UUIDv4 | Time-ordered for storage/index + deterministic on replay; normative (`00`). |

---

## 9. Event examples (canonical JSON)

### 9.1 SQLi request, normalized
```json
{
  "event_id":         "01J9Z2X3...v7",
  "simulation_id":     "01J9Y...v7",
  "org_id":            "org_demo",
  "sequence":          142,
  "sim_time_ms":       562230,
  "received_at_ms":    1723...X,
  "origin":            "web",
  "raw_type":          "http.request",
  "category":          "http",
  "subtype":           "sql_injection_indicator",
  "severity_hint":     "high",
  "attack_stage":      "initial_access",
  "target_node_ids":   ["login_ep","users_db"],
  "source_node_id":    "zone_internet_attacker",
  "via_edge_ids":      ["edge_attacker_to_lb"],
  "mitre_tactics":     ["TA0001"],
  "mitre_techniques":  ["T1190"],
  "owasp_refs":        ["A03:2021"],
  "payload": {
    "method":"POST","path":"/api/login","status":500,
    "body":{"username":"' OR 1=1--"},"ms":41,
    "sqli_pattern":"tautology"
  },
  "correlation_key":   "src_ip=203.0.113.42",
  "benign":            false
}
```

### 9.2 Auth success after burst (potential compromise)
```json
{
  "raw_type":"auth.success","subtype":"auth_success_after_burst",
  "severity_hint":"critical","attack_stage":"credential_access",
  "mitre_tactics":["TA0006","TA0001"],"mitre_techniques":["T1078"],
  "payload":{"account_id":"admin@finbank","factor":"password","new_geo":"sim:CN"},
  "target_node_ids":["admin_creds","auth_svc"],"correlation_key":"src_ip=203.0.113.42"
}
```

### 9.3 Benign noise (explicit)
```json
{
  "raw_type":"http.request","subtype":"http_request","benign":true,
  "attack_stage":"benign","severity_hint":"info",
  "mitre_tactics":[],"mitre_techniques":[],
  "payload":{"method":"GET","path":"/index.html","status":200,"ms":12},
  "correlation_key":"src_ip=198.51.100.42"
}
```

### 9.4 Supply chain hook
```json
{
  "raw_type":"package.lifecycle.hook","subtype":"package_lifecycle_hook",
  "severity_hint":"critical","attack_stage":"execution",
  "mitre_tactics":["TA0002","TA0001"],"mitre_techniques":["T1059","T1195"],
  "owasp_refs":["A08:2021"],
  "target_node_ids":["lib_jwt_1_2_3","app_build_container"],
  "payload":{"hook":"postinstall","cmdline":"node scrape.js","env_patterns":["AWS_","_TOKEN"]},
  "correlation_key":"package=lib-jwt@1.2.3"
}
```

---

End of `07-event-schema-normalization.md`. Next: `08-backend-api-spec.md`.
