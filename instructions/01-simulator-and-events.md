# 01 — Vulnerable Demo App, Attack Simulator, Event Engine

Depends on: `00-overview.md` (read it first — this file does not repeat the
scope boundaries, event schema, or codebase policy defined there).

Target repo paths (audit these first per `00` Section 3):
`cybersim/simulation/`, `cybersim/events/`

---

## Goal of this stage

At the end of this file you can run one command, watch a scripted attack
unfold as a stream of canonical events in a terminal or simple API response,
and every event matches the schema in `00` Section 5. Nothing graph- or
AI-related yet — that's `02` and `03`.

---

## Step 1 — Audit

Before writing anything:

1. Read `cybersim/simulation/` and `cybersim/events/` in full.
2. Answer and record in `AUDIT.md`:
   - Is there already an event contract/schema defined? Does it match `00`
     Section 5? If not, note the delta.
   - Is there an event bus (in-process, Redis-backed, etc.)? Does it require
     Redis to run? If yes, it needs an in-process fallback per `00` scope.
   - Is there any existing scenario/scripted simulation logic? Is it a stub
     or functional?
3. Decide per module: keep as-is / extend / adapt-and-keep / rewrite. One
   line each in `AUDIT.md`.

---

## Step 2 — The vulnerable demo app (target of the simulated attack)

This does **not** need to be a real, separately running vulnerable web app
with actual exploitable code. Building and securing a real toy app adds risk
without adding demo value. Instead:

- Model it as a **simulated environment description** — a small config or
  in-code structure representing:
  ```
  Internet → Web/API Gateway → Authentication Service → Application Server → Database
  ```
- Represent each as an `Asset`/`Service` node (matches `00` Section 6) with a
  name, type, and a couple of illustrative "vulnerabilities" as metadata
  (e.g. `auth-api: {"weak_lockout_policy": true}`). These are descriptive
  labels used for narrative/graph purposes, not real exploitable code.
- If time allows and it's genuinely fun to demo, a minimal Flask/FastAPI
  stub with a `/login` endpoint that the simulator "attacks" is fine — but
  it must never be exposed publicly, must run only on localhost, and its
  entire purpose is to be a believable target for the scripted simulator
  below, not a real security-testing surface. Do not add real SQLi/IDOR
  vulnerabilities that could be misused if the demo device is on a shared
  network — simulate their *effects* via scripted events instead of
  implementing genuine exploitable flaws.

**Recommendation: skip the real toy app entirely for Round 1.** Emit the
attack purely as a scripted event sequence against the modeled environment
(Step 3). This is faster, safer, and the judges only see the dashboard, not
the target app anyway.

---

## Step 3 — Attack Simulator (deterministic state machine)

Build a Python state machine that plays out exactly one attack chain,
deterministically and repeatably, emitting canonical events with realistic
timing.

### Required scenario: Credential Compromise Chain

```
Stage 1: Brute Force
  → multiple LOGIN_FAILED events, increasing severity as attempt count grows
Stage 2: Account Compromise
  → one LOGIN_SUCCESS event, same source_ip as the failed attempts, HIGH severity
Stage 3: Privilege Escalation
  → PRIVILEGE_ESCALATION event, actor now has elevated role, HIGH severity
Stage 4: Database Access
  → DB_ACCESS event, target_asset = "database", CRITICAL severity
Stage 5 (optional, only if time allows): Exfiltration Signal
  → DATA_TRANSFER event, unusually large payload flag, CRITICAL severity
```

### Implementation requirements

- A `Scenario` class/config drives the stage sequence — do not hardcode a
  single unrepeatable script; make it replayable so you can demo it more
  than once without restarting the whole stack.
- Emit events with a configurable delay between them (default: 1–2 seconds)
  so the dashboard event stream feels live rather than dumping everything
  instantly. Make delay configurable — you'll want it faster while
  iterating and closer to 1-2s for the actual judge demo.
- Every emitted event must validate against the canonical schema (`00`
  Section 5). Add a schema validation step (pydantic model) that raises
  loudly if a stage emits a malformed event — catch this in development, not
  during the demo.
- Expose a simple control surface: `start_scenario()`, `reset_scenario()`,
  and ideally `step()` for manual single-stepping during development/testing.

### Event Engine responsibilities

- Receives raw stage output from the simulator, normalizes to the canonical
  schema, assigns `event_id`/`timestamp` if not already set.
- Publishes events to whatever bus exists (in-process pub/sub is sufficient;
  do not require Redis per `00` scope — if the existing code requires Redis,
  add an in-process fallback path, don't remove the Redis option, just don't
  require it to run).
- Keeps an ordered in-memory log of all events in the current run — the
  dashboard's Event Stream panel and the LangGraph pipeline both read from
  this log.

---

## Step 4 — Minimal API surface for this stage

Expose via FastAPI (extend `cybersim/api/` if it exists):

- `POST /simulation/start` — begins the scenario
- `POST /simulation/reset` — clears state, ready to run again
- `GET /simulation/events` — returns the event log so far (poll-friendly;
  full WebSocket/Redis real-time layer is optional per `00` scope)

---

## Checkpoint — what should work at the end of this file

Run the scenario and confirm, via terminal output or `GET /simulation/events`:

- Events appear in order, with realistic pacing
- Every event matches the canonical schema
- Severity escalates appropriately across the chain
- You can reset and re-run without restarting the process

This checkpoint has no graph or AI yet — that's expected. A judge could not
be shown this stage alone as "the demo," but it's the foundation everything
else reads from.

---

## You must be able to explain

- What triggers each stage transition in the state machine, and why it's
  deterministic rather than random
- What the canonical event schema is and why every module agrees on it
- Why the "vulnerable app" is simulated rather than a real exploitable
  target, and why that was a deliberate choice, not a shortcut you're
  hiding
- How you'd add a second attack chain (e.g. supply-chain) without touching
  the Event Engine — this is the "one slice, many future extensions"
  architecture story
