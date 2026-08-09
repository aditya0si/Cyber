# 01 — Product Vision

## 1. What we are building

**CyberSim AI** is an **Autonomous Cybersecurity Simulation & Response Platform** delivered as a multi-tenant SaaS. It spins up **sandboxed, reproducible cyberattack scenarios**, streams normalized security events, models the evolving environment as an **attack graph**, and runs an **evidence-grounded AI analyst** (orchestrated with LangGraph) that **detects, explains, and recommends responses** to evolving threats.

The platform is, intentionally, *not* a scanner of other people's production systems. It is a **controlled cyber range**: a safe, reproducible laboratory where attacks, detection, analysis, and remediation are demonstrated end-to-end with full evidence.

## 2. The metaphors we are building toward

### 2.1 It is a *range*, not a *scanner*
A gun range doesn't patrol a city. It gives you controlled targets, known distances, and lets you train safely. CyberSim AI is a cyber range: scenarios are bounded, seeded, and replayable. There is no risk of collateral damage, and demos never "accidentally" hit a real system.

### 2.2 It is an *analyst*, not an *oracle*
The AI does not emit unsupported assertions ("there is an SQL injection"). It emits a *decision package*: threat, severity, confidence, evidence (event IDs + graph context), and a *recommended* (not performed) response. The system validates the package before anything changes.

### 2.3 It is *graph reasoning*, not *alert noise*
Alerts become **chains**. Events are placed on an attack graph; the agent reasons about *progression* ("these five events are probably part of the same attack chain") rather than isolated blips. This is the core differentiator vs. a dashboard bolted onto an LLM.

## 3. Who it is for

| Persona | Goal in platform | Why CyberSim |
|---------|------------------|--------------|
| **Security engineer / blue-team lead** | Train detection & response on realistic, reproducible scenarios | Replace over-consuming prod SOC tooling with a safe simulator for drills and onboarding. |
| **DevSecOps / platform engineer** | Validate that the pipeline catches the OWASP- and supply-chain-style attacks | Run scenarios as *-tests* in CI; assert the analyst detects them. |
| **GRC / training lead** | Demonstrate control efficacy to auditors with evidence trails | Every detection ships evidence; runs are replayable. |
| **Hiring manager / educator** | Assess and develop analyst skill | **Mission Mode** gamifies scenarios with scoring. |
| **Investor / judge / prospect** | See a defensible live demo | Mission Mode produces a dramatic, interactive demonstration with evidence. |

Primary buyer persona for MVP: **security engineering teams at 50–500-person tech companies** for training and validation. Secondary: educators running cyber ranges. (See `16` for how this maps to pricing.)

## 4. The core user journeys

### Journey A — "Run a scenario and watch the AI analyze it" (core E2E)
1. User picks a **scenario** (e.g., Web App: SQLi against `/api/login`).
2. User (optionally) tunes(parameters: attacker skill, noise, seed) and clicks **Start Simulation**.
3. The SOC Dashboard opens; events stream live over WebSocket.
4. The AI Analyst ingests events, builds/updates the attack graph, and emits **detections** with severity, confidence, evidence, attack path, and recommended response.
5. The user inspects the evidence, the attack graph, and the explanation, then clicks **Execute Response**.
6. The simulation reacts (e.g., source IP blocked); the dashboard shows containment.

### Journey B — "Mission Mode" (the demo killer)
1. Judge/visitor is handed a **Mission**: "Protect FinBank" (environment: 5 servers, 3 APIs, 1 DB, 200 users).
2. They press **Start Simulation**; events begin appearing (`⚠ Suspicious login activity`, `⚠ API anomaly`, `⚠ Privilege escalation`, `🔴 Database access`).
3. The AI pieces it together and surfaces: `ATTACK DETECTED — Likely attack: credential compromise → privilege escalation → data access — Confidence 91% — Recommended action: contain authentication service`.
4. Judge clicks **Execute Response**; the simulation changes based on their action.
5. At end-of-mission, CyberSim scores the operator on detection speed, response appropriateness, and avoided impact. (See `14`.)

### Journey C — "Scenario as code" (dev/CI use)
A scenario is a YAML/JSON file; a CLI/CI runner executes it headless, asserts the analyst produced a detection for the seeded attack, and fails the build if not. This turns the cyber range into **programmable security testing infrastructure**. (Stretch for MVP; see `19`.)

## 5. Functional scope

### 5.1 In scope — MVP (v0.1)
- **4 simulators:** Web App, API, Network, Supply Chain (see `06`).
- **7 scenario archetypes surfaced in the scenario picker** (the UI lists 7 categories; 4 are fully implemented, 3 are "coming soon" placeholders): Web application attack, API abuse, Credential attack, Network intrusion, Supply-chain compromise, Phishing/social-engineering *(placeholder)*, Cloud misconfiguration *(placeholder)*. *(Self-question: should we hide the placeholders? Decision: show them dimmed as "Roadmap" to communicate product trajectory without over-promising.)*
- **Event normalization + event bus** (`07`).
- **Attack graph engine** with NetworkX backend and a documented Neo4j migration seam (`05`, `10`).
- **AI Analyst** via LangGraph with: event ingestion → normalization → threat detection → graph retrieval → evidence analysis → risk scoring → response planning, with a deterministic **rule-based fallback detector** for degradation (`11`).
- **RAG knowledge base:** MITRE ATT&CK + OWASP + a curated CVE slice, with citations in analyst output (`12`).
- **SOC Dashboard** (web): live event stream, detections panel, evidence viewer, attack-graph visualization, response console (`13`).
- **Mission Mode** with ≥3 missions and scoring (`14`).
- **Multi-tenant SaaS essentials:** org/teams auth, entitlements, Stripe billing, usage metering (`15`, `16`).
- **Replay & export:** every run downloadable as JSON; deterministic replay from seed.
- **Observability:** structured logs, metrics, Langfuse LLM tracing, SLOs (`18`).

### 5.2 In scope — v0.2+ (documented but not built first)
- Additional simulators: Phishing/social-engineering, Cloud misconfiguration, Credential attack as a first-class simulator (currently folded into Identity within API/Network).
- Neo4j backend promotion behind the graph abstraction.
- Team collaboration, RBAC roles beyond admin/member, and SSO.
- Scenario authoring studio (no-code editor).
- Organizations can upload private knowledge into their tenant-scoped RAG partition.

### 5.3 Explicitly out of scope (for v0.1 — and we *say so* in the UI)
- Operating against real/external production systems. Ever.
- Autonomous, unsupervised response execution in a customer environment.
- Any claim of "AI discovers unknown vulnerabilities on the internet."
- Real malware execution. Simulations are *synthetic event generators*, not malware.

> **Scope honesty rule:** anywhere marketing copy might overstate capabilities, ship the honest version. The product story is "reproducible, evidence-grounded, sandboxed" — not "magic scanner."

## 6. The defensible architecture story (for judges/investors)

```
                  CYBERSIM AI
                       │
       ┌───────────────┴────────────────┐
       │                                │
   SIMULATION                        KNOWLEDGE
       │                                │
 ┌─────┼─────┐                    ┌─────┼─────┐
 Web  API Network               MITRE OWASP CVE
 │     │     │                       │
 └─────┼─────┘                       │
       ↓                              ↓
             EVENT ENGINE
                   │
                   ↓
              ATTACK GRAPH
                   │
                   ↓
              LANGGRAPH AI
                   │
        ┌──────────┼──────────┐
        ↓          ↓          ↓
      Detect     Explain    Respond
        │          │          │
        └──────────┼──────────┘
                   ↓
             SOC DASHBOARD
```

Narration: *"Controlled scenarios → normalized events → attack graph → evidence-grounded AI analyst that detects, explains, and recommends responses → operator dashboard. The AI never acts unvalidated; every decision ships evidence."*

## 7. Success metrics (v0.1)

| Metric | Target | How measured |
|--------|--------|--------------|
| Detection Recall on seeded attacks | ≥ 95% across MVP scenarios | Scenario-replay test suite asserts the seeded attack raises a matching detection within 30s (`20`). |
| Evidence coverage | 100% of detections include ≥3 evidence items | Validator rejects evidence-less detections (`11`). |
| False-positive discipline | Rule-based noise correctly *not* escalated | Scenarios include benign noise; tests assert it doesn't raise high/critical. |
| Agent p95 detection latency (event → detection) | ≤ 8s | Traced in Langfuse; SLO in `18`. |
| Demo determinism | Same seed → same event stream (byte-identical ordering where ordering is non-time-based) | Replay tests. |
| UI Lighthouse perf | ≥ 90 (perf) on SOC Dashboard | CI gate. |
| Onboarding-to-first-detection time | ≤ 5 minutes for a new judge/judgeable user | Dogfooded run-through. |

## 8. Non-goals & guardrails (recap, normative)

- **No real network egress to attacker targets.**Simulators are synthetic event producers; they do not perform reconnaissance against third parties. (Vision brief: "Everything happens inside your controlled simulation environment.")
- **No autonomous mutation by the LLM.** All response execution is validated by a deterministic executor and gated by an explicit user action (except in optional auto-pilot mode, which itself requires tenant opt-in and is off by default).
- **No stored secrets in events.** Simulated credentials are fictional tokens, never real values.

---

## 9. Decision rationale & alternatives (product-level)

| Decision | Chosen | Rejected alternative | Why |
|----------|--------|----------------------|-----|
| Product shape | Sandbox cyber range + AI analyst | "AI website scanner" | Scanner over-promises and is indefensible; the range is honest, safe, and demoable. |
| Scope of simulators (MVP) | 4 fully built, 7 shown | Build all 7 | Hackathon-style deadline; pillared scope keeps quality high. Showing 7 communicates trajectory without over-promising. |
| LLM role | Proposer (validated by executor) | Autonomous actor | Defensible + safe; surprises are minimized; the vision explicitly forbids "we called an LLM API and gave it a suspicious dashboard." |
| Evidence mandates | Required on every detection | Optional | This is the differentiator; making it optional erases the product story. |
| Graph as first-class | Attack Graph is core, not incidental | Plain event list + LLM | "Graph reasoning vs. alert noise" is the pitch. |
| Mission Mode for demo | Yes | Plain dashboard demo | Interactive game converts judges; produces a memorable 60-second story. |

---

## 10. Open product questions (decide before v0.1 ship, *not* before v0.1 start)

1. **Should missions be shareable via a public link (no signup)?** Lean: yes for demo virality, gated to read-only + ephemeral. Decide by roadmap Phase 6.
2. **Auto-pilot mode (AI executes responses automatically)?** Off by default; gated opt-in per simulation. Document flag scope in `14`/`15`.
3. **Should scenario configs be importable from MITRE CALDERA / Atomic Red Team?** Valuable but out of MVP; logged for v0.2.

---

End of `01-product-vision.md`. Next: `02-design-system-openai-inspiration.md`.
