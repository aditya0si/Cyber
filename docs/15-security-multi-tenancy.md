# 15 — Security, Multi-Tenancy & Compliance

CyberSim AI holds cybersecurity training data, user identities, AI decision artifacts, and (for some tiers) tenant-private knowledge. This doc spec: threat model, AuthN/Z details, tenant isolation strategy, secrets management, simulation sandbox containment, abuse prevention, data protection, and compliance posture. Security is a *product feature* here — not a bolt-on.

> **Normative references:** `09` §10 (RLS), `08` §2 (auth), `14` §5 (public links), `03` §10 (sandbox), `05` §3.3 (overlay).

---

## 1. Threat model (STRIDE-lite)

| Asset | Threat | Mitigation |
|-------|--------|-----------|
| User auth tokens | Spoofing / credential stuffing | Argon2id hashing (memory cost tuned), rate limits on `/auth/login`, optional WebAuthn passkeys, rotating refresh tokens w/ reuse detection |
| Cross-tenant data | Information disclosure | RLS at DB (`09` §10), `org_id` from JWT (never body), fail-closed unset setting test (`20`), per-tenant knowledge partitions in repo scope queries |
| Simulations | Sandbox escape | Simulation workers run on hardened containers: dropped capabilities, read-only root FS, no network egress (`03` §10), seccomp profile, low UID, ephemeral; cryptography of RNG inside container |
| AI output forgery | Elevation of privilege via LLM proposing out-of-whitelist actions | Response executor whitelists by simulator + sim scope (`11` §3.8, `14`); 0 trust of LLM |
| Public mission share links | Abuse of execute endpoints by anon | Public pseudo-tenant, in-mem rate-limit, token rotation (`14` §5) |
| Webhooks (Stripe) | Forged calls | Strict `Stripe-Signature` HMAC verification; replay-window tolerance ±5 min; idempotency on event id |
| Knowledge base | Hallucinated MITRE/CVE citations | Anti-hallucination rule (`12` §6): only IDs we retrieved are surfaced; validator drops invented IDs |
| LLM provider key | Exfiltration | Secret manager boot-time load; never serialized to logs/DB; `pre-commit` lint forbids hard-coded keys; secret scan in CI (`15` §6) |
| Supply-chain sim emitting secrets | Reality misalignment with brief's safety promise | Simulator emits *patterns/paths only*, never values (`06` §6.4); regex scan pre-validation on LLM output (`11` §6.1) |
| Audit logs | Tampering | Append-only table; SELECT-only grants for app role; INSERT-only via privileged logger role (`09` §8) |

## 2. Authentication & authorization — concrete

### 2.1 Passwords
- `argon2id` with parameters: `m=64MiB`, `t=3`, `p=4` (tuned annually; we benchmark on prod hardware in CI).
- Password strength: server-side `zxcvbn-ts` score ≥ 3; weak-password list (Top-100k rockyou derived bloom filter) reject list; no length-only check.
- Account lockout: 5 consecutive failures → 60s exponential backoff per (email or IP) min-IP cap; CAPTCHA after 10 (reCAPTCHA Enterprise v0.2; v0.1 = email-only rate-limit + UI lockout notice).

### 2.2 Session & tokens
- Access token: JWT RS256; `kid` rotated quarterly; JWKS at `/v1/.well-known/jwks.json`; private keys envelope-encrypted at rest (KMS — AWS KMS or GCP KMS depending on prod cloud).
- Refresh token: opaque `48-byte` random, server-stored hash (SHA-256), rotating and single-use; reuse ⇒ revoke session + audit "refresh-reuse-detected" event.
- WS ticket: 60s TTL; bound to session UA, IP CIDR prefix; invalidated after one connection.

### 2.3 WebAuthn (passkey) — optional
- Use FIDO2/WebAuthn for passwordless login (or as 2FA). Device public keys stored per user (`users.webauthn_credentials`). Registration: server-side challenge; relaying party = first-party origin only; require user-verification flag.
- We do NOT force passkeys (viability: many SOC users prefer standard logins); they are an opt-in strong-authn.

### 2.4 RBAC matrix (v0.1)
| Role | Read sims | Start sim | Execute response | Manage members | Billing |
|------|:---:|:---:|:---:|:---:|:---:|
| `admin` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `member` | ✓ | ✓ | ✓ | × | × |
*(analyst/viewer roles deferred; see `08` §2.2.)*

## 3. Tenant isolation architecture

### 3.1 Identity boundary
- `org_id` resolution: `JWT.org_id` only. Any duplicate or override in request body/query is *ignored* (logged as `auth.org_id_override_attempt`).
- Per request: FastAPI dependency injects `current_user` (id, org_id, role) and a **scoped DB session** that issues `SET app.current_org_id = '<org>'` immediately after acquire.
- Health/readiness endpoints bypass scopes; events table denies rows if `app.current_org_id` unset (`09` §10 fail-closed).

### 3.2 Knowledge boundary
- `knowledge.global` rows visible to everyone via policy `org_id = 'global' OR org_id = current`; customer upload partitioned by tenant `org_id != 'global'` (v0.2).
- RAG retrieval scope enforced at the Repository level: `WHERE org_id = 'global' OR org_id = :current_org`.

### 3.3 Background workers (queue)
- Celery workers also set `app.current_org_id` from the simulation row's `org_id` (workers do not span anonymous writes).
- Every task carries `org_id` in args; if absent, the task refuses and emits telemetry.

### 3.4 Real-time
- WS hub inspects JWT org claim at subscribe time → only allows channels `sim.{sim_id}` where `sim.org_id == jwt.org_id`. Attempting a foreign sim → close code `4403 forbidden`.

## 4. Simulation sandbox containment (only workers; static simulators need only process isolation)

For a future v0.2 where we add a *real* exploit-style range:
- Containerized worker: distroless base or slim python; `--read-only` root FS; `--cap-drop=ALL`; `--security-opt no-new-privileges`; seccomp default-deny; `--network=none` unless explicitly required.
- tmpfs for `/tmp` and the seeded scratch dir; max 256 MiB.
- CPU + memory cgroups; per-sim concurrency caps from entitlements.
- v0.1 simulators are in-process *synthetic* event producers (no exploits) and use **process-level** sandboxing: a worker subprocess per concurrent sim with `RLIMIT_*` (CPU seconds, address-space) + `signal.pthread` watchdog.

> **Self-question:** Given v0.1 simulators are pure synthetic event producers, is sandboxing overkill? **Answer:** Defense-in-depth; periodic fuzzing of scenario YAML could lead to unexpected behavior; and we explicitly position CyberSim to be **audit-friendly** — running with demonstrable hardening shapes the security story (`01` §2.3).

## 5. Secrets management
- **Secret manager** (AWS Secrets Manager / GCP Secret Manager per prod cloud) is the source of truth. App boots with: `LLM_API_KEY_*`, `JWT_PRIVATE_KEY_<kid>`, `STRIPE_SECRET_KEY`, `DB_*` (rotation role creds), `S3/R2_*`, `LANGFUSE_*`.
- **No** secrets in env files committed. `.env.example` only documents names. CI scanner (`gitleaks`) gates PRs (`20`). Secret rotation: JWT quarterly; DB role credentials monthly (v0.2 automation).
- LLM API key accessed via `LLMClient`; only inject at call boundary; not in trace tags; Langfuse logger scrubs secret-looking patterns in inputs (regex denying emit of `—SK-`/`AIza` etc. in payload bodies).

## 6. Abuse prevention
- **Rate limits** per `08` §6 (auth 5/min, registered, etc.).
- **Per-IP** + **per-account** rate limits stacked.
- **Honeypot routes** `/v1/_ Canary` returning 404 with tarpit response on abuse patterns → telemetry + temp IP block.
- **WAF** at edge: AWS WAF / Cloud Armor with managed rules + custom rule for OWASP top-10 ingress patterns. We don't bypass it.
- **Mission share links**: rate-limit + abuse flag → token invalidation (`14` §5.1).
- **Cost abuse**: per-org LLM-token budget enforced by Router (`11` §7) + alerting when approaching cap.

## 7. Data protection
- **Encryption at rest:** Postgres via cloud-provider transparent encryption (or LUKS/LVM on self-host); object storage SSE; backups encrypted.
- **Encryption in transit:** TLS 1.3 only; HSTS preload; mTLS internal east-west (FastAPI ↔ DB/Redis) for prod tier (`04` §2.11). Internal mTLS is v0.2 for non-managed-DB/Redis.
- **PII**: We minimize: we store email (citext); no user real names required (display name optional). Events contain simulated entities only — no real-world PII.
- **Right to erasure**: delete-org flow hard-deletes after 30-day cool-off; cascading delete via RLS-bypass role only; released space reclaimed.
- **DPA/GDPR posture:** controller-processor split documented in `15` appendix B (skipped in v0.1 doc; enumerate as a compliance task in `19`).

## 8. Compliance map (v0.1 readiness; *audit-ready* in v0.2+)

| Framework | v0.1 status | Notes |
|-----------|-------------|-------|
| SOC 2 TSP alignment | Designed-with-intent; attest in v0.2 | RLS, audit logs, secret mgmt, encryption |
| GDPR | Designed-with-intent | EU data residency + DPA in v0.2 (default region US in v0.1; `eu` region path reserved) |
| OWASP ASVS L2 | Target ASVS L2 in **auth + session + access control** surfaces only | Cross-doc with `08`; tests (`20`) include rate-limit, RLS, RBAC tests |
| ISO 27001 | Future | — |
| HIPAA | Out of scope v0.1; no PHI collected / required | (revisit if any healthcare tenant) |

## 9. Audit log surface
- `ops_audit_logs` (`09` §8) persists every state-mutating action with `before`/`after` JSON. UI surfaces per-org audit history under `/org/audit`.
- Events captured: `auth.login`, `auth.logout`, `auth.refresh_reuse_detected`, `org.member.invite`, `org.member.role_change`, `org.member.remove`, `simulation.start`, `simulation.stop`, `detection.execute`, `billing.subscribe`, `billing.cancel`, `public_mission.start`, `public_mission.abuse_flag`.
- Audit logs immutable at application layer (INSERT-only via a separate DB role); rotating retention per tier (`09` §13).

## 10. Pen-test / security review cadence
- Annual third-party pen test (v0.2 milestone).
- Quarterly internal review focused on RLS, validation, prompt-injection vector surface.
- Per-quarter dependency audit: `pip-audit` + `npm audit`; high-severity triggers an upgrade. Vuln scan in CI (`20`).

## 11. Self-questioning & decisions (security)

| Decision | Chosen | Rejected | Why |
|----------|--------|----------|-----|
| In-house JWT auth (not Clerk/Auth0) | Yes | OIDC SaaS | Tenant isolation control + audit; matches brief (`04` §2.16) |
| Argon2id (memory-hard) | Yes | bcrypt/PBKDF2 | Modern OWASP ASVS guidance |
| RLS as tenant boundary | Yes | per-tenant DBs at MVP | Ops (# tenants low); reserved for v0.2 large tenants |
| Fail-closed RLS | Yes | permissive | Mistake-proof; test guarantees (`20`) |
| Public mission pseudo-tenant | Yes | signup-gate demos | Demo virality (`14` §5) |
| Seccomp sandbox even for synthetic simulators | Yes | skip hardening | Defense-in-depth + audit story (`15` §4 self-q) |
| LLM provider secrets hard-isolated | Yes | env var in process env | KMS + boot-time load + scrub at trace boundary |
| Anti-hallucination via RAG "retrieved-only" | Yes | trust LLM claims | Cybersec-tool credibility requires it (`12` §6) |
| No real secrets in events (patterns only) | Yes | include dummy tokens | Hard safety promise (`01` §8, `06` §6.4) |
| Annual 3rd party pen-test | v0.2 | now | v0.1 scope limited; queue in `19` |

---

End of `15-security-multi-tenancy.md`. Next: `16-billing-saas.md`.
