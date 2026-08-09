# 06 — Simulators Specification

The four MVP simulators that drive CyberSim AI: **Web Application**, **API**, **Network**, and **Supply Chain**. Each is a *synthetic event producer* that instantiates a scenario, runs a deterministic clock with a seeded RNG, emits canonical-ready raw events, and reacts to `Execute Response` commands. **No simulator touches real networks** — they only produce events that *describe* attacks (`01` §8).

---

## 1. Shared simulator model

Every simulator conforms to the `Simulator` interface:

```python
# cybersim/simulation/base.py
class Simulator(Protocol):
    id: str                         # "web" | "api" | "network" | "supply"

    def init(self, ctx: SimContext) -> EnvironmentGraph:
        """Build the environment graph from the scenario env template + params."""

    def beats(self, ctx: SimContext) -> Iterator[SimBeat]:
        """Yield timed beats (event groups) until simulation ends or halted.

        Beat ordering is deterministic given ctx.seed. Beats are *groups* so we
        can seed correlation without leaking intra-beat timing choices."""

    def apply_command(self, cmd: ResponseCommand, ctx: SimContext) -> list[RawEvent]:
        """Apply an Execute-Response command; return response-effected events."""
```

### 1.1 `SimContext`
```python
@dataclass(frozen=True)
class SimContext:
    org_id: str
    simulation_id: str
    scenario_id: str                # e.g., web.app.sqli_login
    seed: int                       # RNG seed; determinant of reproducibility
    params: dict                    # user-tunable parameters (see per simulator)
    clock: SimClock                 # monotonic sim-time in seconds; wall-clock independent
    graph: EnvironmentGraph         # current environment graph reference
    rng: SeededRNG                  # cybersim.simulation.core.rng
```

### 1.2 Determinism rules (normative)
1. All randomness via `ctx.rng` (a `numpy.random.Generator` or `random.Random` beneath) — seeded per simulation. **No `random.*`, `time.*` jitter, or `uuid4`** anywhere in sim code; `pre-commit` lint forbids them (`20`).
2. Beat timings are *ordered by sim-time*; "real wall-clock" is decoupled: a sim can run 1×, 0.1×, 10× sim-speed. The sim *time* delta is deterministic; wall sleep is a presentation concern.
3. `SimClock` advances in monotonic integer millis; beats scheduled at *absolute* times so a paused/resumed sim is still identical.
4. IDs are **UUIDv7** (time-ordered but seedable; we do NOT use `time`-derived entropy — we derive the v7 timestamp from `clock.now_ms()`, then layer the RNG to fill the random bits — gives deterministic, ordered IDs).

### 1.3 Raw → canonical pipeline (per simulator)
Simulators emit `RawEvent`s (sim-specific payload) into the Redis `events.<org>.<sim>` stream. The normalizer canonicalizes them (`07`). Simulators **never** call the canonical constructor themselves.

## 2. Scenario DSL (YAML)

Scenarios are declarative; we ship a catalog. The DSL is the contract between "scenario author" and "simulator."

```yaml
# simulation/catalog/web.app.sqli_login.yaml
id: web.app.sqli_login
simulator: web
display:
  title: "Web App: SQL injection against /api/login"
  blurb: "Credential brute force + SQLi payload slips into a parameter; DB errors leak schema."
  category: web_application_attack        # one of 7 categories (01 §5.1)
  difficulty: intermediate
  duration_sec: 240                      # default sim duration
environment: !include web.finbank.env.yaml   # reusable env template
adversary:
  origin: { zone: internet, ip: 203.0.113.42 }
  skill: intermediate                    # beginner|intermediate|expert
  kill_chain: web_chain_sqli             # chain template name (05 §5.1)
  intent: data_exfiltration              # intent; influences IMPACTS edge kind
params_default:
  request_rate_per_sec: 4
  payload_mutation_seed: 7               # changes which SQLi payloads appear
  noise_ratio: 0.2                       # benign-traffic ratio for FP-discipline
  benign_users: ["alice","bob","carol"]
dependencies:
  simulators: []
expected_detections:
  - threat_class: sql_injection
    min_severity: high
    within_sec: 60
  - threat_class: data_exfiltration
    min_severity: critical
    within_sec: 120
scoring:                                  # 14 (Mission scoring)
  speed_weight: 0.3
  correctness_weight: 0.5
  containment_weight: 0.2
```

> 7 scenario categories (`01` §5.1) map to a `display.category`; three categories (`phishing_social_engineering`, `cloud_misconfiguration`, and dedicated `credential_attack`) are shown dimmed with `status: roadmap` in the picker; their YAML may exist as scaffolding but no simulator is wired.

### 2.1 Environment templates
A reusable YAML describing the asset topology:
```yaml
# simulation/catalog/web.finbank.env.yaml
assets:
  - id: lb1
    type: load_balancer
    attrs: { vip: 198.51.100.10, tls: true }
  - id: web1
    type: web_server
    attrs: { os: ubuntu2204, framework: flask, sqli_vulnerable: true }
  - ...
services:
  - id: login_ep
    asset: web1
    kind: http
    endpoint: /api/login
    attrs: { auth_required: false, rate_limit_per_min: 60 }
  - id: orders_api
    asset: api1
    kind: http
    endpoint: /api/orders/{id}
    attrs: { auth_required: true }
edges:
  - { from: lb1,    type: EXPOSES,        to: login_ep }
  - { from: web1,   type: READS,          to: users_db, attrs: { priv: r } }
  - ...
credentials:
  - id: admin_creds
    owner: auth_svc
    attrs: { strength: weak, mfa: false, scope: ["admin"] }
data:
  - id: user_data
    store: users_db
    attrs: { kind: pii, sensitivity: high }
```
The simulator's `init()` builds `EnvironmentGraph` from this (entity definitions live in `05`).

---

## 3. Simulator 1 — Web Application (`web`)

### 3.1 Scenario archetypes covered (MVP)
- SQL injection (`web.app.sqli_login`)
- Cross-site scripting stored (`web.app.stored_xss_product`)
- Path traversal (`web.app.path_traversal_static`)
- Authentication bypass (`web.app.auth_bypass_admin`)

### 3.2 Parameters
| Param | Range | Effect |
|-------|-------|--------|
| `request_rate_per_sec` | 0.5–20 | event cadence |
| `payload_mutation_seed` | int | selects SQLi/XSS payload variants |
| `noise_ratio` | 0.0–0.5 | share of benign-looking traffic |
| `attacker_skill` | beginner/intermediate/expert | stealth (lowers error rate, slower), exhibits more sophisticated payloads |
| `stealth_error_rate` | 0.0–1.0 | probability attacker's request triggers a visible SQL error |
| `benign_users` | list[str] | names that produce legitimate logins used as decoys |

### 3.3 Event families emitted (`RawEvent.origin = "web"`)

| RawEvent.type | When | Key payload |
|---------------|------|-------------|
| `http.request` | every request | `method`, `path`, `headers`(subset), `query`, `body`, `src_ip`, `status`, `ms` |
| `http.error` | server errors | `path`, `status>=500`, `detail`, `stack`(partial, scrubbed) |
| `db.query`   | service executes SQL | `statement`(redacted unless `sqli_vulnerable=true`), `rows_returned`, `error?`, `db` ref |
| `db.error`   | DB error | `code`, `message`, `query_ref` |
| `auth.attempt` | login attempt | `username`, `success`, `ip`, `user_agent`, `mfa_used` |
| `auth.success` | successful login | `account_id`, `ip`, `factor` |
| `session.created` | session issued | `account_id`, `session_id`(simulated), `scope`, `ip` |
| `payload.detected` | WAF/proxy heuristic (when enabled) | `signal`, `field` |

### 3.4 Attack behavior for `web.app.sqli_login`
1. Adler prelude: legitimate-looking traffic from benign users (`noise_ratio`) over `T0..T0+30s`.
2. Recon: attacker issues `/api/login` with malformed parameters (`payload_mutation_seed` selects variants: `' OR 1=1--`, `UNION SELECT`, `; DROP`, time-based `SLEEP`).
3. Repeated malformed attempts, increasing frequency (rate doubles between phases), inducing `db.error` ↔ `db.query` correlation.
4. Successful SQLi: a request returns the accounts table or a known-large row count → `auth.success` from a "new geo" → session created.
5. Post-exploit: query widening (`SELECT * FROM users; --`), with large `rows_returned` flagged as exfil pattern; eventually a `data.exfil.candidate` overlay signal.
6. Stepping: optional lateral move to `auth_svc` (reusing extracted hashes) → `auth.success` on admin account → another `db.query` on a privileged table.
7. Termination: scenario ends after `duration_sec` or after a containment/fast-fail signal.

### 3.5 Severity-influencing facts
- `sqli_vulnerable` Service node attribute (env)
- Graph distance `login_ep → users_db → user_data` (≤2 hops) ⇒ severity input high→critical chain (`05` §6.1)
- `attacker_skill=expert` ⇒ fewer visible `db.error` events ⇒ lower *recallable* evidence ⇒ confidence gets clamped if evidence sparse

### 3.6 `apply_command` for Web
| ResponseAction | Effect on env graph | Emitted events |
|----------------|---------------------|---------------|
| `block_source_ip` | REMOVE `CONNECTS_TO` between attacker zone & `web1` | `http.request` with `status=403/blocked` for subsequent attacker attempts |
| `rate_limit_endpoint` | mark `login_ep.attrs.rate_limit_per_min` reduced | `http.request` 429 responses for bursts |
| `disable_endpoint` | REMOVE web `Service` node | `http.request` 503 for that path |
| `patch_sqli` | set `sqli_vulnerable=false` | subsequent SQLi payloads cleanly parameterized (`db.query.parameterized=true`), no `db.error` |
| `rotate_credentials` | replace `admin_creds` node (overlay outbound creds now stale) | `auth.attempt` failures for re-using the stale cred |
| `quarantine_host` | isolate `web1`: remove all active CONNECTS_TO | `service.down` events |

### 3.7 Sample raw→canonical pair (excerpt)
```json
// Raw (simulator output)
{
  "id": "01J9...v7",
  "sim_time_ms": 562230,
  "origin": "web",
  "type": "http.request",
  "node_ref": "login_ep",
  "src_ip": "203.0.113.42",
  "payload": {"method":"POST","path":"/api/login","status":500,
              "body":{"username":"' OR 1=1--"},"ms":41}
}
```
Normalizer canonicalizes per `07` (yielding `category=auth` / `subtype=sql_injection_indicator`, `matre=[T1190]`, severity hint).

---

## 4. Simulator 2 — API (`api`)

### 4.1 Scenario archetypes (MVP)
- Broken auth / excessive data exposure (`api.broken_auth`)
- IDOR (`api.idor_orders`)
- Brute force + rate abuse (`api.brute_force`)
- *(Excessive requests collapse into rate_abuse, included here)*

### 4.2 Parameters (additions)
| Param | Range | Effect |
|-------|-------|--------|
| `id_resource_pool` | int | object IDs the IDOR can enumerate |
| `auth_failure_rate` | 0.0–1.0 | real-failure rate for legitimate creds |
| `permit_broken_authz` | bool | a route with missing authz checks |
| `rate_limit_per_min` | int | real rate cap set on the service |

### 4.3 Event families
| type | When | Payload |
|------|------|---------|
| `api.request` | each call | `method`,`route`,`route_params`,`status`,`ms`,`user_id`,`token_present` |
| `api.authz` | authz decision | `route`,`decision`(allow|deny),`reason` |
| `api.rate.window` | when bucket tick | window metrics: hits, denied |
| `api.data_response` | body stats | `route`,`fields_returned`(count; *some* may be excessive),`rows` |

### 4.4 Attack behavior for `api.idor_orders`
1. Attacker holds/de-rives a valid token (from a benign initial session as low-priv user).
2. Sequentially increments `{id}` on `/api/orders/{id}` from 1000..2000; ~10% error rate at boundary.
3. Each successful response returns the full order (excessive-data-exposure when fields include `cvv`, `address`).
4. No `db.error` correlation here; the *nodal* pattern is the rate of sequential IDs + the absence of `authz.deny` (broken authz).
5. Side-channel: brief bursts of `api.request` to `/api/auth` (brute force variant) intermixed → cross-signal event correlation the analyst must disentangle.

### 4.5 `apply_command` for API
| Action | Effect | Events |
|--------|--------|--------|
| `block_source_ip` | as web | 403s |
| `rate_limit_route` | lower per-route cap | 429s for bursts |
| `fix_idor_authz` | set `permit_broken_authz=false`, re-evaluate responses | subsequent denies (`api.authz.decision=deny`) |
| `restrict_returned_fields` | trim `api.data_response.fields_returned` | responses show redacted field count |
| `revoke_token` | invalidate `token_id` | 401 responses for that token |

### 4.6 Detection nuance
IDOR is *subtle*: failed `db.error` correlation absent; instead evidence = burst of consecutive successful 200s across monotonically-increasing IDs + order fields exceeding scope. RAG retrieves OWASP A01:2021.

---

## 5. Simulator 3 — Network (`network`)

### 5.1 Scenario archetypes (MVP)
- Port scan → service discovery → brute → lateral (`net.recon_lateral`)
- Service-specific credential attack (`net.ssh_credential_attack`) — *also surfaces in the 7-category picker as Credential Attack lite*

### 5.2 Parameters
| Param | Range | Effect |
|-------|-------|--------|
| `open_port_ratio` | 0.0–1.0 | discoveries per host |
| `ssh_brute_prob` | 0–1 | probability each scanned target becomes a brute target |
| `weak_host_ratio` | 0–1 | shares of hosts with weak creds (shaped) |
| `lateral_branching_factor` | 1–4 | average targets attacked from each foothold |
| `firewall_evasion` | bool | SYN-stealth vs full-connect scan signature |

### 5.3 Event families
| type | When | Payload |
|------|------|---------|
| `net.connection` | TCP/UDP open | `src`,`dst`,`port`,`proto`,`flags`(SYN/ACK),`state` |
| `net.scan_probe` | recon probe | `script` (SYN scan / banner), `target_host`, `ports[]` |
| `net.service_discovered` | bannered/identified | `port`,`service`,`banner_fingerprint` |
| `host.login_attempt` | brute attempt | `host`,`account`,`success`,`method`,`ms` |
| `host.session` | foothold on host | `host`,`role`,`creds`,`access_scope` |
| `host.process_spawn` | post-exploitation | `host`,`caller`,`cmdline`,`target` |
| `net.lateral_hop` | attacker uses new host to attack another | `from`,`to`,`method` |
| `evidence.data_exfil` (over net) | outbound bulk transfer | `bytes`,`dst_ext`,`host_src` |

### 5.4 Attack behavior for `net.recon_lateral`
```
(t0) port_scan :: SYN scan across 10.0.0.0/24 ──► net.scan_probe ×N, net.service_discovered on (22,3389,5432)
(t1) brute_force against discovered ssh ──► host.login_attempt bursts
     -- when weak host: host.session (foothold) sets overlay foothold=compromised
(t2) lateral: from new foothold → branch into new targets via LATERAL_TO edges
     -- net.lateral_hop events
(t3) discovery of DB host (port 5432) → targeted brute → credential reuse cracks
     -- host.session on DB host
(t4) evidence.data_exfil :: net.connection bulk to footprint [zone=internet,egress node]
```

### 5.5 `apply_command` for Network
| Action | Effect | Events |
|--------|--------|--------|
| `isolate_host` | remove `CONNECTS_TO` to others (kept perimeter-only admin) | `net.connection` refused from other hosts |
| `block_egress` | remove edge from host to internet | `evidence.data_exfil` :: `blocked` annotation |
| `rotate_credentials_host` | replace `cred` node on host | subsequent `host.login_attempt` failures |
| `sinkhole_scan_domain` | (placeholder defensive) — annotated info | none (stretch) |

---

## 6. Simulator 4 — Supply Chain (`supply`)

### 6.1 Scenario archetypes (MVP)
- Malicious transitive dependency (`supply.malicious_package`)
- Build-system integrity compromise (`supply.build_integrity`)

### 6.2 Parameters
| Param | Range | Effect |
|-------|-------|--------|
| `dependency_depth` | 1–5 | transitive depth where malice occurs |
| `malicious_leak_payload` | str | pre-/post-install script content (synthetic token-eXfil pattern only) |
| `delay_before_activation_ms` | int | dormancy before payload does something visible |
| `package_head_count` | int | # of plausible benign deps around the malicious one |

### 6.3 Event families
| type | When | Payload |
|------|------|---------|
| `build.dependency_resolve` | package install step | `name`,`version`,`resolved_tree`(ids) |
| `package.installed` | installed | `name`,`version`,`integrity_hash`,`registry` |
| `package.lifecycle.hook` | pre/post-install script | `hook`,`cmdline`,`env_subset` |
| `process.exec` | exec spawned | `caller_package`,`cmdline`,`cwd`,`parent_pid` |
| `process.env_exfil` | env-var scan (token-pattern detection) | `var_patterns_seen`(not values!) |
| `net.connection` from build container | (reuse) | `src`,`dst`(simulated registry/attacker C2) |

### 6.4 Attack behavior for `supply.malicious_package`
```
(t0) build.dependency_resolve: app → depA → depB → lib-jwt@1.2.3 (the malicious one)
(t1) package.installed: lib-jwt@1.2.3 with an integrity hash recorded
(t2) package.lifecycle.hook: post-install script execution
     ─ env scan (process.env_exfil — reports *patterns*, not values) +
       spawns process.exec that scrapes ~/.config/credentials.json path (simulated)
(t3) net.connection to fp-bad-registry.example (simulated C2) :: evidence of exfil
(t4) propagation: app variability writes a shim into build output (integrity violation)
```
Critical design: sim emits *patterns* and *paths*, **never values** of credentials — never deviating from "synthetic event producers, no secrets leaving the sandbox" (`01`).

### 6.5 Detection nuance
Strong signals: `dependency_depth` transitive chains ending in a dep with `lifecycle.hook` activity + a network egress. MITRE T1195 + OWASP A08:2021. Analyst cites the supply chain path (graph) as evidence.

### 6.6 `apply_command` for Supply Chain
| Action | Effect | Events |
|--------|--------|--------|
| `pin_dependency_version` | replace `.edge DEPENDS_ON` with a known-safe pin | subsequent `build.dependency_resolve` returns safe version |
| `remove_malicious_package` | remove node | `package.installed` rolled back; build stops using it |
| `block_registry_source` | remove `FETCHES_FROM` to the malicious registry | `build.dependency_resolve` fetch fails |
| `block_post_install_hook` | disable `lifecycle.hook` for that package | no `process.exec`; resolves symlinks-only |
| `force_reproducible_build` | re-run with locked material | integrity check passes |

---

## 7. Scenario catalog inventory (MVP)

| ID | Simulator | Category (7) | Difficulty | Used in mission |
|----|-----------|-------------|-----------|-----------------|
| `web.app.sqli_login` | web | Web application attack | intermediate | Mission "FinBank breach" |
| `web.app.stored_xss_product` | web | Web application attack | intermediate | demo alt |
| `web.app.path_traversal_static` | web | Web application attack | beginner | training |
| `web.app.auth_bypass_admin` | web | Credentials / Web | advanced | stretch |
| `api.idor_orders` | api | API abuse | intermediate | mission alt |
| `api.brute_force` | api | API abuse / Credential | beginner | training |
| `api.broken_auth` | api | API abuse | advanced | stretch |
| `net.recon_lateral` | network | Network intrusion | intermediate | mission "Lateral Hunt" |
| `net.ssh_credential_attack` | network | Credential attack | intermediate | training |
| `supply.malicious_package` | supply | Supply-chain compromise | intermediate | mission "Poisoned Lib" |
| `supply.build_integrity` | supply | Supply-chain compromise | advanced | stretch |
| `phishing.social_engineering` | (placeholder) roadmap | Phishing | — | future |
| `cloud.identity_misconfig` | (placeholder) roadmap | Cloud misconfiguration | — | future |

Shipped at simulation startup by `cybersim/simulation/catalog/loader.py` (loads `*.yaml` in the catalog dir; supports org overrides scoped to tenant partition — enterprise tier v0.2).

---

## 8. Self-questioning & decisions (simulators)

| Decision | Chosen | Rejected | Why |
|----------|--------|----------|-----|
| Simulators do *synthetic event generation* only | Yes | Real exploits / VMs | Safety + reproducibility + cost; vision brief explicit (`01` §8). Real VMs are a v0.2 integration via `Simulator` interface. |
| Beat abstraction = group + deterministic ordering | Yes | One event per call | Batches correlation seed (e.g., SQLi+DB error occur together) without real-time coupling. |
| Attack clock decoupled from wall-clock | Yes | Real-time | Replay/CI deterministic; supports 0.1–10× speed for demos. |
| All nonces via context RNG | Yes | `uuid4`/`random`/`time` | Determinism (`04` §3 rule #5). Pre-commit lint enforces. |
| Severity inputs come from the env graph | Yes | simulator declares severity | Cross-sim consistency; severity parser uses graph distance (`05` §6.1). |
| 4 simulators fully built, 3 categories dimmed | Yes | Build all 7 | Pillared scope; showing 7 communicates trajectory without overpromising (`01` §5.1). |
| Catalog in YAML files | Yes | DB-only scenarios | Versionable + reviewable + CI-runnable; DB store reserved for tenant-private scenarios (v0.2). |
| Cross-simulator event-type reuse | Yes (http.request reused web+api) | Per-sim taxonomies | Simpler normalization; aligned canonical classes. |
| `data.exfil` never includes real values | Yes | include simulated secret tokens | Safety rule (`01` §8). Emit only patterns + paths for supply chain sim. |

---

End of `06-simulators-spec.md`. Next: `07-event-schema-normalization.md`.
