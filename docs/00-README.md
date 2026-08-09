# CyberSim AI — Build Documentation Suite

> **One-line pitch:** CyberSim AI creates controlled cyberattack scenarios, models their progression as an attack graph, and uses an evidence-grounded AI agent to detect, explain, and recommend responses to evolving threats.

This directory is the **single source of truth** used to build the CyberSim AI SaaS platform. It is written to be consumed by an AI coding agent (and by humans). Every module is specified to the level of interfaces, schemas, prompts, and task breakdowns so that implementation can proceed with minimal ambiguity.

---

## 0. How to use these docs

- **Read `01` and `02` first** — they define the product and the visual language. Everything else is implementation detail.
- **Before writing code for a module, read its doc end-to-end.** Each doc has a `Decision rationale & alternatives` section; do not deviate from a recorded decision without committing a written override.
- **Doc = contract.** Component names, file paths, API routes, env var names, table names, and function signatures in these docs are normative. The agent should implement them verbatim unless a doc explicitly says "TBD" or "decide later."
- **Trade-off-first.** The user's directive: *"for everything you write, question yourself if it is the best approach."* Every significant choice in this suite is accompanied by a rationale and the alternatives that were rejected, so the agent can defend the implementation.
- **Numbering is load-bearing.** Files are prefixed `NN-` so import order is stable. Cross-references use the form `[§09 §3.2]` = file `09`, section `3.2`.

### Conventions
- **Language/runtime:** Python 3.11 backend, TypeScript 5+ frontend, Node 20.
- **Package manager:** `uv` (backend), `pnpm` (frontend).
- **Naming:** backend modules `snake_case`; frontend components `PascalCase`; DB tables `snake_case`, plural; env vars `UPPER_SNAKE`.
- **All timestamps** are ISO-8601 UTC strings (`Z` suffix); store as `timestamptz` in Postgres.
- **IDs** are `UUIDv7` string-formatted (time-ordered) unless otherwise noted. Multi-tenant entities embed `tenant_id`.
- **Money** is integer cents. **Confidence** is a float `0.0–1.0`. **Severity** ∈ `{info, low, medium, high, critical}`.
- **Mermaid diagrams** are used throughout; render with the GitHub markdown preview or any Mermaid CLI.
- Code blocks tagged `ts`, `py`, `sql`, `json`, `yaml`, `bash` are normative copy-paste targets.

---

## 1. Document index

| # | File | Purpose |
|---|------|---------|
| 00 | `00-README.md` | This file: index, conventions, glossary, cross-cutting rules. |
| 01 | `01-product-vision.md` | What we are building, who it's for, the story, scope, MVP cut, success metrics. |
| 02 | `02-design-system-openai-inspiration.md` | Reverse-engineered OpenAI design language → design tokens, components, layouts, motion. |
| 03 | `03-system-architecture.md` | High-level architecture, containers, data flow, deployment topology, sequence diagrams. |
| 04 | `04-tech-stack-decisions.md` | Every technology choice with rationale + rejected alternatives + swap-out seams. |
| 05 | `05-domain-model-attack-graph.md` | Core domain model, the attack graph, attack chains, taxonomy, MITRE ATT&CK mapping. |
| 06 | `06-simulators-spec.md` | The 4 simulators: Web App, API, Network, Supply Chain — events, params,🍫automation. |
| 07 | `07-event-schema-normalization.md` | Canonical event schema, normalization rules, event bus, delivery guarantees. |
| 08 | `08-backend-api-spec.md` | FastAPI REST + WebSocket routes, auth, request/response contracts, rate limits, errors. |
| 09 | `09-database-schema.md` | Postgres schema, multi-tenancy, indexes, migrations, seed data. |
| 10 | `10-graph-schema.md` | Attack graph node/edge schema, NetworkX→Neo4j abstraction, queries. |
| 11 | `11-ai-analyst-langgraph.md` | LangGraph analyst: state, nodes, tools, prompts, structured outputs, guardrails. |
| 12 | `12-rag-knowledge-base.md` | Knowledge ingestion (MITRE/OWASP/CVE), embeddings, retrieval, citations. |
| 13 | `13-frontend-architecture.md` | Next.js App Router structure, state, data fetching, component inventory, mapping to design system. |
| 14 | `14-mission-mode.md` | Interactive simulation game: missions, scenarios, response execution loop, scoring. |
| 15 | `15-security-multi-tenancy.md` | AuthZ/AuthN, tenant isolation, data security, secrets, compliance, abuse prevention. |
| 16 | `16-billing-saas.md` | Pricing tiers, Stripe integration, entitlements, usage metering, limits. |
| 17 | `17-deployment-infra.md` | Container layout, IaC, environments, CI/CD, scaling. |
| 18 | `18-observability.md` | Logs, metrics, traces, LLM tracing (Langfuse), alerting, SLOs. |
| 19 | `19-development-roadmap.md` | Phase plan, milestones, ordering, dependencies, definition of done per phase. |
| 20 | `20-testing-strategy.md` | Unit/integration/e2e/contract/simulation-replay tests; fixtures; coverage gates. |
| 21 | `21-ai-agent-build-instructions.md` | Task-by-task build instructions for the implementing agent, file checklist, verification steps. |

---

## 2. Glossary (normative terms)

| Term | Definition |
|------|-----------|
| **Simulation** | A single run of a scenario in a sandbox. Identified by `simulation_id`. Emits a stream of **events**. |
| **Scenario** | A declarative description of an attack environment + adversary behavior (e.g., "Web App: SQLi against login endpoint"). Identified by `scenario_id`. |
| **Simulator** | A module that instantiates a scenario and produces events. Four MVP simulators: Web App, API, Network, Supply Chain. |
| **Event** | A canonical, structured record of something happening in the simulated environment (see `07`). |
| **Attack Graph** | A directed graph where nodes are assets/services/credentials/data and edges are trust/access/dependency relations plus attacker footholds (see `05`, `10`). |
| **Attack Chain** | A path through the attack graph representing a plausible progression of an intrusion (Initial Access → … → Impact). |
| **Detection** | The AI Analyst classifying a group of events as a threat with severity + confidence. |
| **Evidence** | Structured facts (events + graph context) that justify a detection. **No detection is emitted without evidence.** |
| **Response Plan** | A validated set of recommended actions the user may execute against the running simulation. |
| **Mission** | A gamified scenario with objectives, a judgeable outcome, and a score (see `14`). |
| **Tenant / Organization** | A customer workspace. All user data is scoped to an `org_id`. |
| **SOC Dashboard** | The operator UI showing live events, detections, attack graph, evidence, and response console. |
| **AI Analyst** | The LangGraph agent. Sometimes referred to as "the agent." It **proposes** decisions; the system **validates** before acting. |

---

## 3. Cross-cutting rules (apply to every module)

1. **Evidence is mandatory.** No AI output may surface to the user as a decision without accompanying structured evidence (event IDs + graph node refs). See `11` guardrails.
2. **Structured outputs only.** The LLM emits JSON conforming to a Pydantic model; the app validates before any side-effect. Free-form prose is allowed only inside `explanation` fields, and even those are length-bounded.
3. **The LLM never mutates state directly.** It returns proposals. A deterministic validator + executor applies them. This is the "spiritual GPU-for-Minesweeper" guardrail from the vision brief.
4. **Simulations are sandboxed and reproducible.** No real network traffic leaves the platform. Simulations are seeded so `simulation_id` + `random_seed` → identical event stream. This makes demos safe and tests deterministic.
5. **Tenant isolation is physical + logical.** Row-level scoping (`org_id`) plus per-tenant graph namespaces. See `15`.
6. **Everything is replayable.** Every event and every AI invocation is stored with inputs + outputs so any run can be reconstructed and debugged. See `18`.
7. **Degradation is explicit.** If the LLM API is down, the platform falls back to a deterministic rule-based detector (lowered confidence) and surfaces that the AI tier is degraded — never silently fakes AI output.
8. **Accessibility is a requirement, not a nice-to-have.** The design system targets WCAG 2.2 AA. See `02`.

---

## 4. The story (repeat verbatim in pitches)

> CyberSim AI creates **controlled cyberattack scenarios**, models their progression as an **attack graph**, and uses an **evidence-grounded AI agent** to **detect, explain, and recommend responses** to evolving threats.
>
> We are *not* claiming magical autonomous discovery of vulnerabilities across the internet. We are building a **reproducible, sandboxed cybersecurity range** where attacks, detection, analysis, and remediation can be demonstrated — with every AI decision backed by evidence and validated before action.

---

## 5. Build intent

This suite is designed so an AI coding agent can build the platform in the order given by `19-development-roadmap.md`, implementing tasks defined in `21-ai-agent-build-instructions.md`. Each phase has a Definition of Done and a verification command in `20-testing-strategy.md`.
