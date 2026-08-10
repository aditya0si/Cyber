# CyberSim — AI-Powered Cybersecurity Simulation Platform

A real-time attack simulation engine with a LangGraph-powered AI analyst, RAG knowledge retrieval, and a React Flow attack graph frontend.

## What it does

CyberSim runs parameterised multi-stage attack scenarios (credential brute-force → privilege escalation → data exfiltration) against a modelled environment graph. As events fire, a rule-based or LLM-backed analyst pipeline detects threat patterns, cites evidence, and recommends containment actions. A human operator approves before anything executes — then the graph mutates and the frontend reflects the change live.

**Core pipeline:**
```
CredentialCompromiseScenario
  → CanonicalEvent stream
  → NetworkXGraphRepository (ASSET/SERVICE/USER/ATTACK/EVENT nodes)
  → AnalystRuntime (rules_fallback | LangGraph+LLM)
      → InMemoryKnowledgeRepository (TF-IDF or SentenceTransformer RAG)
  → DetectionProposal → human approval gate
  → apply_response_actions (protocol-only mutations)
  → React Flow graph update
```

---

## Project structure

```
cybersim/
  api/            FastAPI app — /graph, /simulation/*, /analyst/*
  analyst/        LangGraph nodes, runtime, rules fallback, RAG tools
  events/         CanonicalEvent schema (8-field), event bus, normalizer
  graph/          GraphRepository protocol + NetworkX implementation
    repo.py       Protocol (the only surface callers should reference)
    repo_nx.py    NetworkX implementation (swap target)
    event_mutator.py  Event→graph mutations, containment actions
    types.py      NodeKind, EdgeType, FootholdState, AttackPath, …
  knowledge/      InMemoryKnowledgeRepository, embedder seam
  simulation/     Scenario runner, web/api/network/supply simulators
instructions/     Stage-by-stage build spec (00-overview through 03)
tests/            222 passing, 14 skipped (missions — out of scope)
```

---

## Getting started

**Prerequisites:** Python 3.11+, [uv](https://github.com/astral-sh/uv)

```bash
# Clone and install
git clone https://github.com/<your-fork>/Cyber.git
cd Cyber
uv sync

# Run the test suite (should be 222 passed, 14 skipped)
uv run pytest tests/ -v

# Start the API server
uv run uvicorn cybersim.api.main:create_app --factory --reload
```

The API is at `http://localhost:8000`. Key endpoints:

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/simulation/start` | Seed the demo scenario and graph |
| `GET` | `/simulation/events` | All emitted CanonicalEvents |
| `GET` | `/graph` | React Flow-compatible graph snapshot |
| `POST` | `/analyst/analyze` | Run analyst pipeline, return threat card |
| `POST` | `/analyst/approve-response` | Execute containment, emit synthetic events |
| `GET` | `/analyst/rag-sources` | Evidence entries cited by last threat card |
| `POST` | `/simulation/reset` | Clear and re-seed graph |

---

## Architecture decisions worth knowing before building further

### CanonicalEvent is an 8-field schema — don't expand it
`event_id`, `timestamp`, `event_type`, `severity`, `source_ip`, `target_asset`, `actor`, `raw_context`. Everything else goes in `raw_context`. This was a deliberate constraint to keep the event bus contract narrow.

### GraphRepository is the only graph surface you should call
`cybersim/graph/repo.py` defines the `GraphRepository` Protocol. All business code — analyst, API, tests — calls only methods on this Protocol. `NetworkXGraphRepository` is named only at the composition root (`api/main.py`). If you want to swap NetworkX for Neo4j or a Postgres graph, implement the Protocol and change one line.

Do not import `NetworkXGraphRepository` in analyst code. Do not call `_require`, `.env`, `.overlay` outside `repo_nx.py`. These constraints are enforced by `tests/graph/test_02b_nodekind_and_protocol.py` — both a regex scan and a `MagicMock(spec=GraphRepository)` hermetic boundary test.

### NodeKind taxonomy
- **Environment layer** (infrastructure): `ASSET`, `SERVICE`, `CREDENTIAL`, `DATA`, `NETWORK_ZONE`, `EDGE_DEVICE`
- **Overlay layer** (attack narrative): `USER`, `ATTACK`, `EVENT`, `VULNERABILITY`

### Analyst pipeline modes
- `mode="rules"` (default): deterministic rule-based fallback via `rules_fallback.analyze_window()`. No LLM, no network calls. Safe for tests and offline demo.
- `mode="ai"`: LangGraph pipeline with LLM calls (needs `LLMClient` wired and API keys in `.env`). Falls back to rules on validation failure.

### RAG embedder fallback
`cybersim/knowledge/embeddings.get_best_embedder()` tries `SentenceTransformer("all-MiniLM-L6-v2")` first; falls back to `TfidfEmbedder` if the model isn't cached or `sentence-transformers` isn't installed. Tests run entirely offline via the fallback.

---

## How to build further

### Stage 04 — Frontend (React Flow) — DONE, live at `/demo`
The four-panel demo dashboard is implemented in `apps/web/src/app/demo/page.tsx`
(unauthenticated route). Backend: `cd cybersim && uv run uvicorn cybersim.api.main:create_app --factory`; frontend: `cd apps/web && pnpm dev`, then open `http://localhost:3000/demo`. Click Start Simulation — events stream in, the attack graph builds live (React Flow + dagre auto-layout), the analyst card appears with evidence + a real graph-query attack path, and `Execute Response` (the human-approval gate → `POST /analyst/approve-response`) flips the graph to isolated/blocked/contained state.

### Stage 05 — LLM analyst (real mode)
Set `OPENAI_API_KEY` in `.env`. Pass `LLMClient` and `knowledge_repo` into `AnalystRuntime(mode="ai", llm=..., knowledge_repo=...)`. The LangGraph pipeline in `cybersim/analyst/graph.py` is already wired — it just needs a live LLM.

### Stage 06 — Additional simulators
Add `cybersim/simulation/<name>/simulator.py` with a `build_environment_graph(scenario_id)` function returning an `EnvironmentGraph`. Add the scenario's event sequence as a `*Scenario` class matching the interface in `scenario.py`. Register in the simulator catalog.

### Stage 07 — Swap graph backend
Implement `GraphRepository` Protocol (all 21 methods in `repo.py`) for your target backend (Neo4j, Postgres graph extension, etc.). At `api/main.py` startup, replace `NetworkXGraphRepository()` with your new class. Nothing else changes — the protocol is the only surface.

### Adding knowledge base entries
```python
from cybersim.knowledge.repo import InMemoryKnowledgeRepository
from cybersim.knowledge.entries import KnowledgeEntry

repo.upsert_entry(KnowledgeEntry(
    entry_id="T1110",
    source="mitre",
    source_id="T1110",
    kind="technique",
    title="Brute Force",
    content="...",
))
```

---

## What's confirmed working (tested)

- Full event schema validation — 8-field `CanonicalEvent`, no extra fields
- Event → graph mutation for all four scenario stages with correct NodeKinds
- GraphRepository protocol enforcement — regex + `MagicMock(spec=GraphRepository)` hermetic test
- Rules-based analyst: `CredentialCompromiseScenario` triggers `credential_brute_force` / `credential_compromise` / `data_exfiltration` detections
- RAG retrieval: TF-IDF fallback works offline; SentenceTransformer used when available
- Human approval gate: `/analyst/analyze` → `/analyst/approve-response` two-call pattern
- Live attack path in the threat card (graph query, not hardcoded): `Attacker → Attack (brute_force) → /api/login → User Database → user_data`
- Full demo dashboard at `/demo`: event stream, React Flow attack graph (nodes color by kind, border by foothold state), analyst card, Execute button — all polling real backend state, zero external API calls
- All 222 tests pass, 14 skipped (mission-mode — out of scope for Stage 1–3 demo)

## What's not done yet

- LLM mode end-to-end (wiring only, not tested with live API)
- Postgres persistence (event log, graph deltas) — currently all in-memory
- Multi-tenancy / org isolation — EventBus routes by `org_id` parameter, not schema field; full isolation not implemented
- Mission scoring DSL (skipped tests)
