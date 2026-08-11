# CyberSim AI — Round 1 Build Contract

**Event:** International Innovation Challenge 3.0, Manipal University Jaipur
**Deadline:** PPT + prototype submission, 11 Aug 2026, 11:59 PM IST
**Theme:** Cybersecurity & Digital Sovereignty
**Team:** Solo builder directing AI coding agents locally against an existing repo

This file is the **immutable contract**. Every other file (`01`–`06`) must follow
it. If any instruction in another file conflicts with this one, this file wins.
Do not re-scope, "improve," or expand beyond what is written here without the
human explicitly changing this file first.

---

## 1. What we are building

> CyberSim AI is an AI-powered cyber defense simulation platform that models
> controlled cyberattacks as evolving attack graphs. A LangGraph-based security
> analyst continuously combines structured security events, attack-path
> context, and evidence from cybersecurity knowledge sources to detect
> threats, explain their progression, assess risk, and recommend defensive
> actions. A human-approved response can then modify the simulated
> environment, allowing the AI to observe the consequences and reassess the
> threat.

**Round 1 MVP, exactly this and nothing more:**

One controlled web/API environment demonstrating:

```
Brute Force → Account Compromise → Privilege Escalation → Database Access
  → AI Detection → Graph Reasoning → Evidence-Backed Response
  → Human Approval → Simulated Containment → Re-observation
```

**The differentiator judges must walk away remembering:** the meaningful unit
isn't the individual alert, it's the evolving attack path — and the system
closes the loop (observe → reason → decide → human-approves → act → observe
again), not just "LLM prints a paragraph about a log line."

---

## 2. Non-negotiable scope boundaries

### In scope for Round 1
- ONE simulation environment, ONE attack chain (brute force → compromise →
  priv-esc → DB access → optional exfil signal)
- Event Engine: normalizes simulated events into a canonical schema
- Attack Graph: NetworkX, in-memory, live-updating
- LangGraph pipeline with the exact node sequence in `03-analyst-langgraph-rulebased.md`
- **Human Approval gate** before any simulated response executes — this is
  not optional, it is the core design decision that makes this a defensible
  "agentic system" rather than an unsupervised one
- RAG: small, scoped corpus (MITRE ATT&CK + OWASP excerpts relevant to
  credential access / brute force only), `all-MiniLM-L6-v2` local embeddings
  with a TF-IDF/keyword fallback (see `03`)
- Dashboard: React + TypeScript + Tailwind + React Flow, four panels (event
  stream, attack graph, AI analyst card, action controls)
- Rule-based fallback for every LangGraph node — the demo must run with
  **zero API calls** and still be complete and impressive. LLM calls are an
  optional enhancement behind a config flag, never a dependency.

### Explicitly OUT of scope — do not build these
- Real-world penetration testing or scanning of arbitrary/public websites
- Autonomous exploitation or any real destructive action
- Multiple independent simulators (network, cloud, supply-chain) — these are
  **roadmap diagram only**, not implemented
- Neo4j in the running demo (NetworkX only; keep the graph layer's interface
  abstract enough that Neo4j could be swapped in later, but do not stand up
  the database)
- Kubernetes, Terraform deploy, production infra
- Multi-tenant auth, RBAC, billing, login screens
- Massive/live CVE ingestion
- Redis/WebSocket real-time layer — polling is acceptable; only build the
  real-time layer if everything else is done early and stable
- Postgres/MinIO persistence — in-memory state for the demo run is sufficient

If a coding agent thinks one of these "would only take an hour" — it does not
get built anyway. Time saved goes into making the one slice flawless and
demo-able, and into slide/RAG-source quality.

---

## 3. Existing codebase policy

Your teammate has an existing repo (`cybersim/` backend, `apps/web/` frontend,
Docker Compose, Terraform, Phase-0 bootstrap complete). Policy for all agents:

1. **Audit first, always.** Before writing any code in a module, the agent
   must read what already exists at the relevant path and report: does it
   run, is it a stub, does it match the canonical event/graph schema this
   contract defines, what's missing. Do not assume the teammate's summary
   description is ground truth on completeness — verify against actual code.
2. **Reuse and extend by default.** If `simulation/`, `events/`, `graph/`, or
   `analyst/` modules exist and are close to what's needed, extend them
   rather than replacing them. Preserve their existing interfaces where
   reasonable so the rest of the team's future work isn't orphaned.
3. **Rewrite only what's broken, missing, or blocks the demo.** If a module
   depends on something out-of-scope (e.g. `graph/` assumes a live Neo4j
   connection), the agent should adapt it to run against NetworkX instead of
   discarding the module — keep the abstraction, swap the backend.
4. **Never silently drop the human-approval gate or the rule-based fallback**
   even if the existing `analyst/` code doesn't have them. These are new
   requirements from this contract and must be added.
5. Document every "kept as-is / extended / rewrote / stubbed" decision in a
   running `AUDIT.md` at the repo root as you go, one line per module. This
   is also useful evidence of engineering process for judges.

---

## 4. Frozen technology stack

| Layer | Choice |
|---|---|
| Frontend | React + TypeScript + Tailwind + React Flow (attack graph viz) |
| Backend | Python 3.11, FastAPI, `uv` |
| AI orchestration | LangGraph, rule-based nodes as default, LLM optional via flag |
| Graph | NetworkX (in-memory) |
| Knowledge/RAG | Local corpus, `sentence-transformers` (`all-MiniLM-L6-v2`), cosine similarity; TF-IDF/keyword fallback if the model can't load |
| Simulation | Deterministic Python state machine + scripted event generator |
| Persistence | In-memory for the demo run (Postgres/MinIO from teammate's repo not required) |
| Deployment | Local run only (`uv run` + `pnpm dev` or equivalent) — Docker Compose optional convenience, not required for demo day |

Do not introduce new infra dependencies (message queues, hosted vector DBs,
new databases) without updating this table first.

---

## 5. Canonical event schema

All modules must agree on this shape (adapt existing teammate code to match,
don't invent a second schema):

```python
{
  "event_id": str,
  "timestamp": str,          # ISO 8601
  "event_type": str,         # e.g. "LOGIN_FAILED", "LOGIN_SUCCESS",
                              # "PRIVILEGE_ESCALATION", "DB_ACCESS"
  "severity": str,            # "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
  "source_ip": str,
  "target_asset": str,        # e.g. "auth-api", "app-server", "database"
  "actor": str,                # user/account identifier involved
  "raw_context": dict          # any extra fields specific to the event type
}
```

## 6. Canonical graph entities and relationships

Node types: `Asset`, `Service`, `User`, `Credential`, `Vulnerability`,
`Attack`, `Event`.

Core relationships used in the MVP:

```
User      --USES-->        Service
Service   --RUNS_ON-->     Server/Asset
Server    --CONNECTS_TO--> Database
Attack    --TARGETS-->     Service
Event     --INDICATES-->   Attack
```

Keep the graph abstraction backend-agnostic (a thin repository/interface
layer over NetworkX) so Neo4j can be substituted post-Round-1 without
touching calling code.

---

## 7. The LangGraph pipeline (exact node sequence)

```
START
  ↓
Event Aggregator
  ↓
Threat Detector
  ↓
Attack Graph Retriever
  ↓
Evidence Retriever (RAG)
  ↓
Threat Analyst
  ↓
Risk Assessor
  ↓
Response Planner
  ↓
Human Approval   ← blocking, UI-driven, not automatic
  ↓
Simulation Action
  ↓
Environment Updated
  ↓
END / Re-evaluate loop
```

Full node-by-node spec is in `03-analyst-langgraph-rulebased.md`. Do not
collapse nodes or skip Human Approval to "simplify" the demo — it is the
core intellectual claim of the project.

---

## 8. Dashboard layout contract

Four panels, roughly as sketched below. Full component spec is in
`04-dashboard-frontend.md`.

```
┌────────────────────────────────────────────────────┐
│ CYBERSIM AI              Scenario: Credential Attack│
├──────────────────┬─────────────────────────────────┤
│  EVENT STREAM     │        ATTACK GRAPH             │
├──────────────────┴─────────────────────────────────┤
│                 AI SECURITY ANALYST                 │
│  [ Explain ] [ Recommended Response ] [ Execute ]   │
└────────────────────────────────────────────────────┘
```

---

## 9. AI-use and authorship requirements (hard constraint)

The competition guidelines require projects to be built by team members and
require any GenAI use to be transparent and limited to ideation/support —
**not** full fabrication of the submission by an agent the team can't
explain.

Consequences for how these MD files must be used:

- These files are **engineering specifications** for you to direct coding
  agents against, review, and understand — not a black box you submit
  unread.
- Every file below ends with a short **"you must be able to explain this"**
  checklist. Before moving to the next file, you should genuinely be able to
  answer those questions out loud, unaided.
- Keep the `AUDIT.md` log (Section 3) and a short note of which parts were
  AI-assisted vs. hand-written/reviewed — useful both for your own
  understanding and if the rules require an AI-use disclosure.
- If a judge asks "walk me through what happens when a login fails," you
  should be able to trace it through Event Engine → Graph → LangGraph nodes
  → Dashboard without looking anything up.

---

## 10. File index

| File | Purpose | Depends on |
|---|---|---|
| `00-overview.md` | This contract | — |
| `01-simulator-and-events.md` | Vulnerable demo app, attack simulator, event engine | `00` |
| `02-attack-graph.md` | NetworkX graph engine, entity/relationship model | `00`, `01` |
| `03-analyst-langgraph-rulebased.md` | LangGraph pipeline, rule-based + optional LLM, RAG | `00`, `01`, `02` |
| `04-dashboard-frontend.md` | React/Tailwind/React Flow dashboard | `00`–`03` |
| `05-integration-and-demo-script.md` | Wiring, end-to-end run, live demo script, fallback plan | `01`–`04` |
| `06-pptx-deck-build.md` | Deck build against the actual competition template | All of the above |

Work through them roughly in order. Each file ends with a checkpoint you
should be able to run and see working before moving on — this gives you a
submittable fallback state at every stage, not just at the very end.

---

## 11. Definition of done for Round 1

Minimum bar to submit:
- [ ] Simulation runs end-to-end locally, deterministically, repeatably
- [ ] Attack graph visibly updates as events arrive
- [ ] LangGraph analyst produces a threat card with severity, confidence,
      evidence (cited from the RAG corpus), and attack path — using the
      rule-based path, no API key required
- [ ] Human clicks "Execute Response," environment visibly changes
      (isolated/blocked/contained state shown)
- [ ] Dashboard matches the four-panel contract
- [ ] Deck built against the real 6-slide template (see `06`), no leftover
      placeholder text, no invented statistics
- [ ] You can explain every component without notes
