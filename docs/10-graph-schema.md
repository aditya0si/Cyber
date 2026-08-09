# 10 — Attack Graph Engine & Schema

The graph is the product's heart. This doc specifies the in-memory graph model (NetworkX for v0.1), its on-disk serialization to Postgres, the **`GraphRepository` abstraction seam** that makes the v0.2 Neo4j swap a one-package change, the canonical query API the analyst/dashboard use, snapshot/delta semantics, and the concrete NetworkX implementation contract.

> **Normative reference:** node/edge taxonomies and foothold semantics live in `05`. This doc covers the *engine* and the *repository API*. No business code imports `networkx` directly (`04` §2.8, `05` §8).

---

## 1. Two-tier model

```
EnvironmentGraph (graph_env)        AttackerOverlay (overlay)
 └─ what exists / what's reachable   └─ what attacker has done / has access to
    - mutated by responses (Executor)    - append-only during analysis
    - persisted in graph_nodes/edges     - persisted in graph_overlay
```
A *view* (`AttackView`) combines the two: "given what the attacker has now, where can they go (i.e., traversable edges in the current env)?" This view answers path queries. (`05` §3.3 motivates the split.)

## 2. The `GraphRepository` seam (normative interface)

```python
# cybersim/graph/repo.py
from typing import Protocol, Iterable
from .types import GraphNode, GraphEdge, OverlayNode, AttackPath, FootholdState

class GraphRepository(Protocol):
    # ---- lifecycle ---------------------------------------------------
    def create(self, simulation_id: str, env_template: dict) -> None: ...
    def load(self, simulation_id: str) -> None: ...
    def drop(self, simulation_id: str) -> None: ...

    # ---- mutations (env) --------------------------------------------
    def upsert_node(self, simulation_id: str, node: GraphNode) -> None: ...
    def upsert_edge(self, simulation_id: str, edge: GraphEdge) -> None: ...
    def deactivate_edge(self, simulation_id: str, edge_id: str) -> None: ...
    def update_foothold(self, simulation_id: str, node_id: str, state: FootholdState, flags: dict | None = None) -> None: ...

    # ---- overlay (attacker-side) ------------------------------------
    def append_overlay(self, simulation_id: str, overlay: OverlayNode) -> None: ...
    def add_overlay_edge(self, simulation_id: str, *, kind: str, from_id: str, to_id: str, via_env_edge_id: str | None = None, evidence_event_id: str | None = None) -> None: ...

    # ---- queries (read-only view) -----------------------------------
    def get_node(self, simulation_id: str, node_id: str) -> GraphNode | None: ...
    def get_edges(self, simulation_id: str, node_id: str) -> list[GraphEdge]: ...
    def neighbors(self, simulation_id: str, node_id: str, types: list[str] | None = None) -> list[str]: ...
    def can_reach(self, simulation_id: str, src: str, dst: str, *, hops: int = 4) -> bool: ...
    def attack_paths(self, simulation_id: str, *, src: str | None = None, dst_kinds: list[str] = ("DATA",), max_paths: int = 5, hops: int = 4) -> list[AttackPath]: ...
    def graph_view(self, simulation_id: str) -> dict: """nodes+edges+overlay foothold states, ready for UI.""" ...
    def snapshot(self, simulation_id: str, at_seq: int) -> bytes: """full snapshot (json-encoded) for replay."""
    def delta(self, simulation_id: str, from_seq: int, to_seq: int) -> dict: ...
```

### 2.1 Type model (`cybersim/graph/types.py`)
```python
@dataclass(frozen=True)
class GraphNode:
    node_id: str
    kind: NodeKind                # ASSET|SERVICE|CREDENTIAL|DATA|NETWORK_ZONE
    type: AssetType | None        # only for kind=ASSET
    label: str
    attrs: dict
    foothold_state: FootholdState = FootholdState.CLEAN

@dataclass(frozen=True)
class GraphEdge:
    edge_id: str
    from_node: str
    to_node: str
    type: EdgeType                # EXPOSES|CONNECTS_TO|READS|WRITES|AUTHENTICATES_WITH|...
    attrs: dict
    active: bool = True

@dataclass(frozen=True)
class OverlayNode:
    node_id: str                  # overlay-local id
    parent_node_id: str           # graph node it annotates
    state: FootholdState
    flags: dict

@dataclass(frozen=True)
class AttackPath:
    nodes: list[str]              # ordered node ids
    edges: list[EdgeTransition]
    closes_at_node_kind: NodeKind # DATA for exfil detection
    length: int
```

## 3. NetworkX implementation (v0.1)

### 3.1 Graph holder
- A `MultiDiGraph` per simulation (multi-edges between same endpoints because multiple edge types coexist). Edge `type` is a key attribute; we add a synthetic composite key `key = (type, edge_id)` to NetworkX edge keys.
- Two **sets** per node: `attrs` (free) + `foothold_state` (env) plus overlay edge dict overlay.
- In-memory object cached in `GraphCache` (LRU, capacity configurable, default 256 simulations; evict cold; re-hydrate from latest snapshot + deltas since).

```python
class NetworkXGraphRepository(GraphRepository):
    def __init__(self, db: GraphDAL, cache: GraphCache, publish: Callable):
        self._db = db; self._cache = cache; self._publish = publish

    def upsert_node(self, sim_id, node):
        g = self._cache.get_or_load(sim_id)
        g.add_node(node.node_id, **asdict(node))          # idempotent upsert
        self._db.upsert_node(sim_id, node)                # mirror to PG
        self._publish("graph.delta", sim_id, delta_for_node(node))
```

### 3.2 Concrete query implementations
| API | Implementation |
|-----|-----------------|
| `neighbors(types)` | `g.successors(n)` filtered by `edge['type'] in types` and `edge['active']`. |
| `can_reach(src,dst,hops)` | Bidirectional BFS using `AttackView` (env + overlay conquest). Bounded `hops` (≤6). O(|V|+|E|) per query, fine for ≤100 nodes. |
| `attack_paths(...)` | `nx.all_simple_paths(G_view, src, [data nodes], cutoff=hops)` with a custom predecessor constraint (no escaping containment edges), capped at `max_paths`. |
| `graph_view()` | Build JSON envelope: `{nodes, edges, overlay_footholds, live_paths?}` (paths optional; precompute only for ≤ 5 critical data nodes; for UI perf). |
| `delta(from,to)` | Replay `graph_edges`/`graph_nodes` since `from_seq` plus overlay additions; compose deltas since last full snapshot; if span > N, ship a full snapshot. |

### 3.3 Snapshot/delta + Postgres interplay
- Every `apply_event` (handler) writes a `graph_delta` row to `ops`-like deltas in `cybersim.graph.delta_store` (table `graph_deltas`).
- Every `Δtick = 2s` sim-time, write a `graph_snapshot` (full) and zero ongoing deltas. Cheap coalescing.
- Re-hydration: read latest full snapshot ≤ seq, apply subsequent deltas. Bounded replay.
- The repository **publishes** via the event bus (`graph.delta.<sim>`) so the dashboard receives incremental updates rather than full-refresh (see `02` §4.5 for animation hooks).

### 3.4 Deterministic layout seed for UI rendering
- The vector coordinates of a node in the dashboard's `GraphView` are derved by a **seeded force-directed layout** keyed on `(simulation_id, graph_revision)` — we DO NOT want the graph to reflow whimsically between renders. Use `networkx.spring_layout(G, seed=simulation_seed)` and persist coordinate offsets when the user drags (stored client-side, per simulation, in user prefs).
- For `prefers-reduced-motion`, skip spring animation and render statically. (`02` §7-3.8.)

## 4. Neo4j migration plan (v0.2)

The same `GraphRepository` is implemented by `Neo4jGraphRepository`. Mappings:

| Concept | NetworkX | Neo4j |
|---------|----------|-------|
| Node | node attr | `(:Asset {id, kind, type, label, attrs})` label per `kind` |
| Edge type | `type` attribute | relationship type per `EdgeType` enum (uppercase) |
| Overlay | overlay side-graph | `(:AttackerFoothold {state})-[:ON]->(:Asset)` plus `[:EXPLOITED|TRAVERSED|EXFILTRATED]` relationships |
| Multi-edge between same endpoints | MultiDiGraph | several relationships with distinct `type` (native) |
| Per-sim isolation | one graph per sim | graph label `(:Sim {sim_id})` + node attribute `sim_id` + RLS-equivalent via Cypher scope OR separate database per enterprise tenant (tuned by tenant tier). |
| Paths | `all_simple_paths` | Cypher `MATCH p = shortestPath((a)-[:CONNECTS_TO|...*..]->(b))` |
| Snapshot/delta | our Postgres table | (still our PG table for cross-cutting audit) + Neo4j periodic dumps/restore |

Swap is bounded to `cybersim/graph/repo_neo4j.py`; feature-flagged via `GRAPH_BACKEND=nx|neo4j`. The CI test suite (`20`) runs the *same* `GraphRepository` tests against (a) NetworkX, (b) a fake in-memory impl, and (c) **when env has Neo4j up** (e.g., nightly) the Neo4j impl — proving the abstraction.

## 5. Concrete attack graph queries the analyst uses

### 5.1 "Is the attacker within K hops of sensitive data?" (severity input)
```python
paths = repo.attack_paths(sim_id, src=attacker_zone_node,
                          dst_kinds=[NodeKind.DATA], max_paths=5, hops=4)
sev_input = "high" if any(p.length <= 2 for p in paths) else \
            "medium" if paths else "low"
```
This is a deterministic input the validator uses to clamp AI severity (`05` §6.1).

### 5.2 "Find the chain that closed at DATA (exfil candidate)"
```python
closed = [p for p in repo.attack_paths(sim_id, hops=5) if p.closes_at_node_kind == NodeKind.DATA]
# returned as evidence with every detection whose threat spans exfil
```

### 5.3 "What changed since last detection?" (incremental evidence)
```python
delta = repo.delta(sim_id, from_seq=last_d_seq, to_seq=current_seq)
# delta.added_nodes/delta.updated_footholds feed the analyst's *graph_traversal* evidence.
```

### 5.4 UI helper: graph_view payload
```json
{
  "simulation_id":"01J9Z...",
  "seq": 412,
  "nodes":[
    {"id":"lb1","kind":"ASSET","type":"load_balancer","label":"Load Balancer","foothold":"clean","attrs":{"vip":"198.51.100.10"}},
    {"id":"login_ep","kind":"SERVICE","label":"/api/login","foothold":"compromised","attrs":{"sqli_vulnerable":true}},
    {"id":"user_data","kind":"DATA","label":"User Data","foothold":"clean","attrs":{"kind":"pii","sensitivity":"high"}}
  ],
  "edges":[
    {"id":"e1","from":"lb1","to":"login_ep","type":"EXPOSES","active":true,"attrs":{"proto":"https"}},
    {"id":"e27","from":"login_ep","to":"user_data","type":"READS","active":true,"attrs":{"priv":"r"}}
  ],
  "overlay_footholds":[
    {"node_id":"ov_attacker","parent":"zone_internet_attacker","state":"recon"},
    {"node_id":"ov_login","parent":"login_ep","state":"compromised"}
  ],
  "live_paths":[
    {"nodes":["ov_attacker","lb1","login_ep","users_db","user_data"],"length":4,"closes_at":"DATA"}
  ]
}
```

## 6. Performance & guardrails
- Cap per-sim graph size at ≤2,000 nodes / 10,000 edges (assertion in repo create from env template). MVP scenarios ~100 nodes.
- Path queries: `hops ≤ 6`, `max_paths ≤ 10` (valid build-time args; CI test enforces).
- LRU cache size default 256 sims; configurable; eviction writes a final snapshot.
- Concurrent per-sim writes serialized via `asyncio.Lock` keyed on `simulation_id` (graph state must serialize per-sim; `03` §1).
- UI rendering: layout computed server-side (seeded) and shipped as coordinates + node attrs; client only does pan/zoom/highlight. (`02` §4.5.)

## 7. Self-questioning & decisions (graph engine)

| Decision | Chosen | Rejected | Why |
|----------|--------|----------|-----|
| In-memory NetworkX v0.1, Neo4j seam behind repo | Yes | Neo4j day 1 | Per-sim graphs ≤100 nodes & ephemeral; NetworkX is trivial + testable; migration bounded (`04` §2.8). |
| Environment + AttackerOverlay split | Yes | one labeled graph | Mutation disjoint + unambiguous evidence (`05` §3.3.1). |
| Snapshot + delta hybrid | Yes | pure deltas | Bounded replay cost; recent-read hot path supported. |
| Persist env graph to `graph_nodes/edges` | Yes | PG JSONB blob | Indexable; UI queries via SQL fallback. |
| Force-directed UI uses seeded layout | Yes | re-layout every render | Deterministic UX; user drag offsets stored client-side. |
| Repo interface with three test impls (NX/fake/Neo4j nightly) | Yes | direct NX | Swap-safe; the seam is a quality gate (`20`). |
| Path cap (6 hops, 10 paths) | Yes | unbounded | Realistic + perf-safe; was tuned against scenario graph metrics. |

---

End of `10-graph-schema.md`. Next: `11-ai-analyst-langgraph.md`.
