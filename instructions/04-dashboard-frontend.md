# 04 — Dashboard Frontend

Depends on: `00-overview.md`, `01`–`03` (needs working API endpoints from
each to wire up against; can be scaffolded in parallel with mock data
before those are ready).

Target repo path (audit first per `00` Section 3): `apps/web/`

Stack (frozen, per `00` Section 4): React + TypeScript + Tailwind +
React Flow.

---

## Goal of this stage

At the end of this file, the four-panel dashboard from `00` Section 8 is
live, polling/reading real backend state (not mock data), and a full
run-through (start → events stream → graph builds → threat card appears →
click execute → containment shows) works end to end in the browser.

---

## Step 1 — Audit

1. Read `apps/web/` structure — Next.js App Router per the teammate's
   summary. Confirm what pages/components already exist.
2. Check whether any dashboard/graph-viz work is already started. Reuse
   scaffolding (routing, API client setup, Tailwind config) even if the
   actual dashboard content needs to be built fresh.
3. Record in `AUDIT.md`.

---

## Step 2 — Layout (four panels, per `00` Section 8)

```
┌────────────────────────────────────────────────────┐
│ CYBERSIM AI              Scenario: Credential Attack│
├──────────────────┬─────────────────────────────────┤
│  EVENT STREAM     │        ATTACK GRAPH             │
│  (left, ~35%)     │        (right, ~65%)            │
├──────────────────┴─────────────────────────────────┤
│                 AI SECURITY ANALYST                 │
│  [ Explain ] [ Recommended Response ] [ Execute ]   │
└────────────────────────────────────────────────────┘
```

Top bar: title + current scenario name + a `Start Simulation` / `Reset`
control.

### Panel 1 — Event Stream

- Reverse-chronological list, newest at top
- Each row: timestamp, event type (human-readable, e.g. "Failed login"
  not `LOGIN_FAILED`), severity as a colored dot/badge
  (`LOW`=gray/yellow, `MEDIUM`=amber, `HIGH`=orange, `CRITICAL`=red)
- Poll `GET /simulation/events` on an interval (1s is fine) while a
  simulation is running; stop polling once complete/idle
- Auto-scroll to newest, but don't fight the user if they've scrolled up
  to read something

### Panel 2 — Attack Graph (React Flow)

- Consume `GET /graph` (`to_dict()` output from `02`), map to React Flow
  `nodes`/`edges` arrays
- Node styling by type: `User`/`Attacker` distinct shape/color from
  `Service`/`Asset`/`Database`
- Node styling by state attribute (`00`/`02`): normal vs `compromised` vs
  `at_risk` vs `isolated`/`blocked`/`contained` — use color, not just a
  text label, so the state change on "Execute" is immediately visible
- Auto-layout is fine (dagre or React Flow's built-in layouting) — don't
  hand-position nodes, the graph is small enough this isn't necessary
- Re-fetch/update on the same polling cadence as the event stream, or
  trigger a refetch after each new event lands

### Panel 3 — AI Security Analyst

Threat card, populated from `POST /analyst/analyze` (or auto-triggered once
the scenario reaches a point where `Threat Detector` would fire — your
call on UX, but don't require a manual click just to see if anything was
detected; do require a click for `Execute`).

Card contents, matching `03`'s Threat Analyst/Risk Assessor/Response
Planner outputs:

```
🔴 HIGH — Credential Compromise          Confidence: 91%

Evidence
• 17 failed login attempts
• Successful login immediately afterward
• New privilege assignment
• Database access from same session

Attack Path
Auth API → Account Compromise → Privilege Escalation → Database

Sources
MITRE ATT&CK T1110 (Brute Force) · OWASP Credential Attacks
```

Buttons:
- `Explain` — expands/shows the fuller natural-language explanation (rule-
  based template text by default)
- `Recommended Response` — shows the ordered action list with reasons
- `Execute Response` — the Human Approval action. Calls
  `POST /analyst/approve-response`. Should feel deliberate (maybe a brief
  confirm state), since narratively this is "human approves AI-recommended
  action," not a throwaway button.

After execute: card updates to show `CONTAINED` status, graph panel
reflects isolation/block state, event stream shows any synthetic
containment events.

---

## Step 3 — State management

Keep it simple — this doesn't need Redux/Zustand for a demo this size.
React Query (or even plain `useState` + polling `useEffect`s) is
sufficient. Prioritize correctness and demo-day reliability over
architectural purity here.

---

## Step 4 — Visual design notes

- This is a security tool — dark background, high-contrast severity
  colors, monospace for event timestamps/IDs reads as credible for the
  genre. Don't over-theme it into a generic dark-mode SaaS template; a few
  deliberate choices (severity color system, clean graph node styling)
  go further than heavy decoration.
- Keep the whole thing legible on a shared demo screen — err toward larger
  text and fewer, clearer elements over dense information density.

---

## Checkpoint — what should work at the end of this file

Open the app, click Start Simulation, and watch — without touching
anything else — events stream in, the graph build itself stage by stage,
the threat card appear with real evidence and a real attack path, then
click Execute and watch the graph/card reflect containment. This is
functionally the whole live demo already at this checkpoint.

---

## You must be able to explain

- How the frontend gets graph/event updates (polling vs. real push) and
  why that choice was made given the scope constraints in `00`
- How node/edge state (compromised, isolated, etc.) flows from the backend
  attribute values to the actual rendered color/style
- What "Execute Response" actually triggers end to end, across all four
  files so far
