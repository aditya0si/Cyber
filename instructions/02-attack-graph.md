# 02 — Attack Graph Engine

Depends on: `00-overview.md`, `01-simulator-and-events.md`.

Target repo path (audit first per `00` Section 3): `cybersim/graph/`

---

## Goal of this stage

At the end of this file, every event from `01` updates a live NetworkX graph
according to the entity/relationship model in `00` Section 6, and you can
query "what's the current attack path to the database" and get a real
answer, not a hardcoded string.

---

## Step 1 — Audit

1. Read `cybersim/graph/` fully.
2. Check specifically: does it assume a live Neo4j connection anywhere? If
   the module errors out without Neo4j running, that's the first thing to
   fix — not by deleting Neo4j support, but by making the backend
   swappable (see Step 2).
3. Record keep/extend/rewrite decisions in `AUDIT.md`.

---

## Step 2 — Backend-agnostic graph interface

Do not let calling code (the LangGraph analyst, the API layer) talk to
NetworkX or Neo4j directly. Define a thin interface, e.g.:

```python
class AttackGraphRepository(Protocol):
    def add_node(self, node_id: str, node_type: str, **attrs) -> None: ...
    def add_edge(self, source: str, target: str, relation: str, **attrs) -> None: ...
    def get_path(self, source: str, target: str) -> list[str]: ...
    def get_neighbors(self, node_id: str) -> list[str]: ...
    def to_dict(self) -> dict: ...  # for sending to frontend / React Flow
    def get_critical_assets_reachable_from(self, node_id: str) -> list[str]: ...
```

Implement `NetworkXAttackGraph` for Round 1. If the existing repo has a
`Neo4jAttackGraph` implementation or stub, **keep the file, don't delete
it** — just don't wire it into the running demo. This is genuinely worth
having on the Feasibility slide ("graph backend is already abstracted;
Neo4j implementation exists for production scale").

---

## Step 3 — Populate the environment graph

Before any attack events arrive, seed the graph with the modeled environment
from `01` Step 2:

```
User(attacker) --USES--> Service(auth-api)
Service(auth-api) --RUNS_ON--> Asset(app-server)
Asset(app-server) --CONNECTS_TO--> Asset(database)
```

This is the "infrastructure" layer the attack graph overlays on top of.

---

## Step 4 — Event → graph update mapping

Each canonical event type triggers a specific graph mutation. Define this
mapping explicitly (a dict or small dispatch table, not ad hoc if/else
scattered through the codebase):

| Event type | Graph mutation |
|---|---|
| `LOGIN_FAILED` | Add/increment an `Attack(brute_force)` node, edge `Event --INDICATES--> Attack`, edge `Attack --TARGETS--> Service(auth-api)` |
| `LOGIN_SUCCESS` (after failures) | Add `User(compromised_account)` node, edge `Attack --RESULTED_IN--> User`, mark node attribute `status: compromised` |
| `PRIVILEGE_ESCALATION` | Add edge `User --GAINED--> Credential(admin)`, update node attribute `privilege: admin` |
| `DB_ACCESS` | Add edge `User --ACCESSED--> Asset(database)`, mark `Asset(database)` attribute `status: at_risk` |
| `DATA_TRANSFER` (optional stage) | Mark `Asset(database)` attribute `status: exfiltration_suspected` |

This table is also useful raw material for the "How it Works" narrative on
the Technical Approach slide.

---

## Step 5 — Response actions mutate the graph too

When the Human-Approved response executes (see `03`), the graph must update
to visibly reflect containment:

| Response action | Graph mutation |
|---|---|
| Isolate account | `User(compromised_account)` attribute `status: isolated` |
| Revoke sessions | Remove/mark inactive the `USES` edge from that user |
| Block database access | `Asset(database)` attribute `status: blocked`, remove/mark inactive the `ACCESSED` edge |

The dashboard reads these attributes to render color/state changes on the
graph (`04`).

---

## Step 6 — Query methods the AI analyst needs

The LangGraph `Attack Graph Retriever` node (see `03`) needs, at minimum:

- `get_path(attacker_node, database_node)` → ordered list of nodes/edges,
  used to render "Attack Path: Auth API → Account → Admin → Database"
- `get_critical_assets_reachable_from(compromised_node)` → used for risk
  assessment ("this account can reach the database")
- `to_dict()` → serialized graph for the frontend, shaped for direct
  consumption by React Flow (nodes array + edges array, see `04`)

---

## Checkpoint — what should work at the end of this file

Running the `01` scenario end to end should leave you with a graph you can
serialize and inspect (print `to_dict()` or hit a `GET /graph` endpoint)
showing:

- The seeded environment nodes/edges
- New attack-related nodes/edges appearing as each event lands
- A queryable path from the attacker to the database once the chain
  completes
- Node/edge state changes when a (manually triggered, for now) response
  action runs

---

## API surface to add

- `GET /graph` — current graph as `to_dict()` output, for the frontend and
  for manual debugging

---

## You must be able to explain

- Why the graph backend is behind an interface rather than NetworkX calls
  scattered through the codebase
- The exact node/edge types in the model and what real-world entity each
  represents
- How a single `LOGIN_FAILED` event becomes graph structure, step by step
- Why "attack path" is a graph query rather than something inferred by the
  LLM — this is the "graph engineering, not just an LLM reading logs" pitch
