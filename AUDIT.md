# CyberSim Graph Layer Audit — 02b Final Closure

## Environment Compatibility Fix (Stage 03.5, pre-04)

### Finding: `datetime.utcnow()` deprecated on Python 3.12

`pyproject.toml` escalates `DeprecationWarning` from `cybersim.*` to errors
(`filterwarnings = ["error::DeprecationWarning:cybersim.*"]`). Under Python
3.12.13 (this machine), `datetime.datetime.utcnow()` raises a
DeprecationWarning, turning the entire test suite red (30 failures/errors:
simulation, analyst, graph, API tests) even though the branch was green under
an older interpreter.

| File | Line | Fix |
|---|---|---|
| `cybersim/simulation/scenario.py` | 35 | `utcnow().isoformat()+"Z"` → `datetime.now(datetime.UTC).isoformat().replace("+00:00","Z")` |
| `cybersim/api/main.py` | 187 | Same pattern (synthetic containment event timestamp) |

`platform/auth/repo.py`, `platform/auth/models.py`,
`platform/simulation/store.py` already used `datetime.now(tz=UTC)` — kept
as-is.

### Result

```
222 passed, 14 skipped, 0 failed
```

---

## Stage 04 — Dashboard Frontend (four-panel demo dashboard)

### Backend gaps found during the frontend audit (all fixed)

The existing tests were only green because they *manually* worked around
backend gaps (several API tests re-applied events to the graph by hand,
with comments like "For now, let's manually apply them so the test passes").
Fixing those gaps is what makes the Stage 04 checkpoint actually work.

| # | File | Change |
|---|---|---|
| 1 | `cybersim/graph/repo_nx.py` | `snapshot()` now includes `overlay_edges` (kind, from, to, active) so the React Flow graph can render the attack narrative (INDICATES / TARGETS / USES / ACCESSED / …) — previously only env edges were serialized |
| 2 | `cybersim/simulation/scenario.py` | `start()` accepts an `on_event` callback invoked per emitted event; scenario now targets **real env node ids** (`login_ep`, `users_db` instead of phantom `auth-api`/`database`) and sets `raw_context.source_node_id` so the attack-path query has an origin |
| 3 | `cybersim/api/main.py` | `/simulation/start` is now a **sync route** (threadpool → event loop stays free for concurrent polls) and applies each event to the graph as it lands via `on_event`; clears stale `last_analysis`; module-level imports cleaned per ruff |
| 4 | `cybersim/graph/event_mutator.py` | Added `LAUNCHED` overlay edge (attacker → attack node) so paths originate at the attacker; added `rotate_credentials` handler (credential nodes → `status: rotated`, CONTAINED); `_quarantine_compromised` now covers USER nodes (sets `status: isolated`) and uses `contextlib.suppress` |
| 5 | `cybersim/analyst/response_catalog.py` | Web catalog now also allows `isolate_account`, `revoke_sessions`, `block_database` — the containment actions the demo actually executes |
| 6 | `cybersim/analyst/rules_fallback.py` | Response Planner is now a threat-class-keyed plan table with one-line reasons (03 §Step 2), filtered through the per-simulator catalog; empty-path fallback (`_attack_path_anchors`) kept |
| 7 | `cybersim/graph/repo_nx.py` | `attack_paths()` now walks env **and** overlay edges (on a copy) — the attack path is a real graph query: `Attacker → Attack (brute_force) → /api/login → User Database → user_data` |
| 8 | `tests/` | `test_full_scenario_produces_expected_graph_structure` updated for the real env id (`attack_bruteforce_login_ep`); `test_m1_pipeline` whitelist now reads `allowed_actions("web")` instead of a hardcoded copy |

### Frontend (new — `apps/web`)

Added `reactflow` + `dagre` dependencies. New files:

```
src/app/demo/page.tsx                    Four-panel layout + 1s polling
src/components/demo/EventStream.tsx      Reverse-chron events, severity badge
src/components/demo/AttackGraph.tsx      React Flow canvas (dagre LR layout)
src/components/demo/AnalystPanel.tsx     Threat card + Explain / Response / Execute
src/lib/demo/types.ts                    Demo API types
src/lib/demo/api.ts                      Demo API client (no auth)
src/lib/demo/graphLayout.ts              Snapshot → RF nodes/edges + styling
```

- Polls `GET /simulation/events` + `GET /graph` every 1s while running
  (events/graph build live because the backend applies events as they land);
  stops polling when idle/contained.
- Auto-runs `POST /analyst/analyze` when the scenario completes; `Execute
  Response` → `POST /analyst/approve-response` is the human-approval gate
  (deliberate confirm state). Card flips to `CONTAINED`; graph shows
  isolated/blocked state via foothold-state colors.
- Node color = kind, border color = foothold state (`compromised` red,
  `contained` green); animated dashed red edges = overlay attack links.
- Route is unauthenticated (`/demo`) — the demo endpoints need no auth.

### Verification

```
uv run pytest tests/           → 222 passed, 14 skipped
pnpm typecheck / lint / build  → clean; /demo route static
Live smoke test (uvicorn + built Next.js):
  start → events trickle in 0.5s apart → analyze → threat card with
  critical/data_exfiltration, 60% confidence, real attack path, 4 ordered
  actions with reasons → approve → users_db blocked, user isolated,
  CONTAINMENT_EXECUTED events in stream.
```

### Known follow-ups (not blocking)

- `ruff check cybersim` still reports 6 pre-existing issues in
  `events/normalizer.py` + `events/schema.py` (untouched by this stage).
- `mypy cybersim` fails on a numpy stub vs mypy 2.3 incompatibility —
  environment-level, pre-existing.

---

## Stage 05 — Integration, end-to-end run, demo script, fallback plan

### Deliverables

- **`RUNNING.md`** at repo root — exact run commands (backend `uv run
  uvicorn cybersim.api.main:create_app --factory`, frontend `pnpm dev` →
  `http://localhost:3000/demo`), the 2-minute demo narration beats, known
  fragile points with one-line workarounds, and the demo-day fallback plan.
- `USE_LLM=false` verified as the default: `create_app(analyst_mode="rules")`
  and blank `OPENAI_API_KEY` in `.env.example`; the demo makes zero external
  calls (rules path + TF-IDF RAG fallback).

### Determinism run (05 Step 1 item 3) — 5 consecutive full runs via API

Ran `start(delay=0) → analyze → approve-response → reset` 5× on one app:

```
run 1: baseline (6 events, 22 graph nodes)
run 2-5: events identical=True, threat card identical=True
         graph structure (kind/label/foothold) identical=True
         only 6 event_<uuid> node ids vary per run (uuid4 by design)
contained state every run: user=contained/isolated, db=contained/blocked
```

Event sequence: LOGIN_FAILED ×3 → LOGIN_SUCCESS → PRIVILEGE_ESCALATION →
DB_ACCESS. Threat card: critical / data_exfiltration / 60% confidence, 4
ordered actions. Matches the contract's "timing may vary slightly, content
should not".

### End-to-end checklist status

- [x] Start → events appear within a couple seconds (0.8s pacing, build live)
- [x] All 4 stages in order with escalating severities
- [x] Graph builds in sync with events (applied per event during start)
- [x] Threat card: severity, confidence (formula-traced), evidence, real
      attack path, ordered actions with reasons
- [x] Execute Response requires the click (confirm state), no auto-fire
- [x] After execute: graph isolated/blocked, card CONTAINED, containment
      events in stream
- [x] No external API calls in the full run (rules mode; offline RAG)
- [x] Full run ≈ 6s at 0.8s pacing — comfortably under 2 minutes
- [ ] Manual browser pass + screen recording (needs a human at the machine)

### Stage 06 — SKIPPED (user decision)

The deck build (`06-pptx-deck-build.md`) requires the official
`Shortlisting_PPT_Template__Round_1_.pptx` template, which is not available
on this machine. Per the human's decision on 11 Aug 2026, Stages 05 (manual
pass, screen recording) and 06 (deck build) are **skipped entirely**. Stage
05 deliverables produced before that decision (`RUNNING.md`, determinism
run) remain in the repo as-is.

---

## Stage 04 — Frontend Audit + Build

## Bypass Call Site Audit (Part 2, Step 1)

### Scope: all files in `cybersim/` and `tests/` outside `repo_nx.py`

Search performed for: `_require(`, `.env.nodes`, `.env.edges`, `.overlay.nodes`, `.overlay.edges`, `.overlay.remove_edge`

#### Violations Found & Fixed

| File | Line(s) | Pattern | Status |
|---|---|---|---|
| `cybersim/graph/event_mutator.py` | 151, 152, 161, 162, 172, 173, 181 | `repo._require(sim_id)`, direct `.env`, `.overlay` access | **Fixed** — full rewrite |
| `tests/graph/test_attack_graph_repository.py` | 50–54 | `repo._require(sim_id).overlay` | **Fixed** — replaced with `repo.find_overlay_edges()` |
| `tests/graph/test_attack_graph_repository.py` | 75 | `repo._require(sim_id).env.nodes()` | **Fixed** — replaced with `repo.get_node()` |

#### Remaining Violations After Fix

**Zero.** Confirmed by two searches after refactor.

---

## Part 1 — NodeKind Extensions

Added to `cybersim/graph/types.py`:
```python
USER = "USER"
ATTACK = "ATTACK"
EVENT = "EVENT"
VULNERABILITY = "VULNERABILITY"
```

Wired into real scenario-driven graph mutations in `event_mutator.py`:
- `LOGIN_FAILED` → `NodeKind.ATTACK` node + `NodeKind.EVENT` node per event
- `LOGIN_SUCCESS` → `NodeKind.USER` node
- `PRIVILEGE_ESCALATION` → updates `NodeKind.USER`, links `NodeKind.CREDENTIAL`
- `DB_ACCESS` → `NodeKind.USER` --ACCESSED--> Asset

---

## Part 2 — Protocol Extension

Added three methods to `GraphRepository` Protocol (`repo.py`) and implemented in `NetworkXGraphRepository` (`repo_nx.py`):

| Method | Purpose |
|---|---|
| `find_nodes_by_kind(sim_id, kind)` | Enumerate all env nodes of a given NodeKind |
| `find_overlay_edges(sim_id, kind=None)` | Read overlay edges, optionally filtered by kind |
| `remove_overlay_edge(sim_id, edge_key)` | Remove a single overlay edge by key |

---

## Part 3 — Test Suite

### New tests in `tests/graph/test_02b_nodekind_and_protocol.py`

| Test | What it actually asserts |
|---|---|
| `test_nodekind_includes_user_attack_event_vulnerability` | Set difference `{USER,ATTACK,EVENT,VULNERABILITY} - NodeKind members == ∅` |
| `test_credential_compromise_scenario_creates_user_and_attack_nodes` | Runs full 01 scenario; `find_nodes_by_kind(USER)`, `find_nodes_by_kind(ATTACK)`, `find_nodes_by_kind(EVENT)` all return `len > 0` |
| `test_apply_response_actions_uses_protocol_only` (regex) | Strips docstrings/comments from `event_mutator.py` source; asserts no regex match for `._require(`, `.env.nodes`, `.env.edges`, `.overlay.nodes`, `.overlay.edges`, `.overlay.remove_edge` in code |
| `test_apply_response_actions_mock_boundary` (hermetic) | `MagicMock(spec=GraphRepository)` — accessing `_require`/`.env`/`.overlay` raises `AttributeError` immediately; asserts only `find_nodes_by_kind` and `upsert_node` called; asserts `called_methods - protocol_methods == ∅` |
| `test_containment_updates_reflected_via_protocol_query` | After `apply_response_actions`, queries via `find_nodes_by_kind` and `get_node` — confirms `status=isolated` and `foothold_state=CONTAINED` visible through protocol reads |

### Results

```
Run 1: 222 passed, 14 skipped, 0 failed
Run 2: 222 passed, 14 skipped, 0 failed
```

---

## Stage 03 — Analyst Code Status (Post-02b Audit)

### Finding: concrete type leak in analyst layer

The following analyst files import and type-hint against `NetworkXGraphRepository` (the concrete class) rather than the `GraphRepository` Protocol:

| File | Line | Pattern |
|---|---|---|
| `cybersim/analyst/tools.py` | 11, 18 | `from cybersim.graph.repo_nx import NetworkXGraphRepository`; `__init__(self, repo: NetworkXGraphRepository, ...)` |
| `cybersim/analyst/nodes.py` | 14, 304, 415, 435 | Same import; type hints on `repo` parameters |
| `cybersim/analyst/graph.py` | 24, 35 | Same import; `LangGraphAnalyst.__init__(self, ..., repo: NetworkXGraphRepository, ...)` |
| `cybersim/analyst/runtime.py` | 17, 30 | Same import; `AnalystRuntime.repo: NetworkXGraphRepository` |
| `cybersim/api/main.py` | 60, 64, 99, 109, 121 | Instantiates `NetworkXGraphRepository()` at wiring point (this one is **correct** — the composition root is the right place to name the concrete type) |
| `cybersim/api/routers/simulations.py` | 179, 181 | Instantiates inside a route handler (same: composition root, acceptable) |

### Impact assessment

**No runtime bypass**: none of these files call `_require`, `.env`, or `.overlay` directly. The concrete type in the type hints does not cause a behavioral violation — all *calls* go through protocol methods.

**What it does break**: the type annotations lock the analyst layer to `NetworkXGraphRepository`. If the repo backend is swapped (the "abstracted, swappable" claim on the Feasibility slide), any `tools.py`/`nodes.py`/`graph.py`/`runtime.py` consumer would also need updating — the swap is not as clean as claimed.

### Recommendation

Change the four analyst files to accept `GraphRepository` (the Protocol) in their type hints. The composition root (`main.py`, `routers/simulations.py`) correctly names the concrete class at wiring time — that stays. This is a one-line type annotation change per file, zero behavioral change, but it makes the "swappable backend" claim actually true end-to-end.

**This is a 03-stage issue, not a runtime defect. Flagged for the next checkpoint.**
