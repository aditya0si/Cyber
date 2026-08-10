# CyberSim Graph Layer Audit — 02b Final Closure

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
