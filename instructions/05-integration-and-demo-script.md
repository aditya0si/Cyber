# 05 — Integration, End-to-End Run, Demo Script, Fallback Plan

Depends on: `00-overview.md`, `01`–`04`, all of which should be individually
checkpointed and working before this file.

---

## Goal of this stage

A single, reliable, rehearsed run-through that works the same way every
time, plus a documented fallback if something breaks live in front of
judges.

---

## Step 1 — Wire it all together

1. Confirm all services start with a small number of commands (ideally 2:
   one for backend, one for frontend). Document exact commands in a
   `RUNNING.md` at repo root:
   ```
   # Backend
   cd cybersim && uv run uvicorn api.main:app --reload

   # Frontend
   cd apps/web && pnpm dev
   ```
   (adjust to actual entry points found during audits in `01`-`04`)
2. Confirm `USE_LLM=false` is the default in whatever config/env file is
   used, so a fresh clone/run never silently expects an API key.
3. Run the full scenario 5+ times in a row via `Reset` → `Start`, confirm
   identical structure every time (timing may vary slightly, content
   should not).

---

## Step 2 — End-to-end checklist

Run through this literally, checking each box, not from memory:

- [ ] Fresh reset → Start Simulation → events begin appearing within a
      couple seconds
- [ ] All 4-5 stages of events appear in order with correct severities
- [ ] Graph panel shows new nodes/edges appearing in sync with events,
      not all at once and not lagging noticeably behind
- [ ] Threat card appears with severity, confidence, evidence (with
      source citations), and attack path — all populated from real data,
      not placeholder text
- [ ] Execute Response button works, requires the click (doesn't
      auto-fire)
- [ ] After execute: graph shows isolated/blocked state visually, card
      shows contained status
- [ ] No console errors during the full run
- [ ] No network calls to any external API during the full run (confirm
      via browser network tab or backend logs) — this is your reliability
      guarantee for demo day
- [ ] Full run completes in under ~2 minutes so it fits a demo slot
      comfortably

---

## Step 3 — The demo script (2-3 minutes)

Rehearse this exact narration structure, adjust wording to your voice but
keep the beats:

1. **Open (10s):** "CyberSim AI simulates a real attack chain, builds a
   live attack graph, and has an AI analyst reason about what's happening —
   with a human approving any response, not the AI acting alone."
2. **Start simulation (20s):** Click start. Narrate the events as they
   stream: "Here's a brute-force attempt against our login API... now a
   successful login from the same source... privilege escalation...
   database access."
3. **Point at the graph (20s):** "As each event lands, we're not just
   logging it — we're placing it on a graph of the actual environment. You
   can see the attack path forming: API, to account, to admin, to
   database."
4. **Threat card (30s):** "The AI analyst combines the event pattern, the
   graph context, and evidence retrieved from MITRE ATT&CK and OWASP to
   produce this: high severity, 91% confidence, here's the evidence, here's
   the attack path." Click Explain briefly if time allows.
5. **Response + human approval (30s):** "It recommends isolating the
   account, revoking sessions, rotating credentials — but it doesn't do
   this on its own. A human has to approve." Click Execute. "Now watch the
   graph — account isolated, database access blocked, threat contained."
6. **Close (20s):** "This is one attack chain end to end. The architecture
   is built so we can plug in network, cloud, and supply-chain simulators
   through the same event, graph, and AI layers — that's the roadmap."

Total: ~2 minutes, leaves room for Q&A.

---

## Step 4 — Fallback plan (if something breaks live)

Prepare all of these in advance, don't improvise on the day:

1. **Screen recording backup.** Record a clean successful run once
   everything is stable. If live demo fails, say so plainly and play the
   recording — judges respect this far more than a frozen screen and dead
   silence.
2. **Screenshots in the deck.** The Prototype/screenshots content (see
   `06`) should already contain real screenshots of each stage, so even
   total demo failure doesn't leave the deck empty-handed.
3. **Known fragile points** — identify these explicitly once integration
   testing is done (e.g. "graph panel needs a manual refresh if the poll
   interval misses a fast state change") and have a one-line manual
   workaround ready for each, written down, not remembered under pressure.
4. **Offline-first is already your reliability story** — no external API
   calls means no wifi-related demo failure. Reiterate to yourself: the
   biggest common hackathon-demo failure mode (flaky API/wifi) is already
   designed out.

---

## Checkpoint — what should work at the end of this file

You've run the full scenario at least 5 times back to back with the
checklist passing every time, you have a recorded backup video, and you
have a written one-line fallback for every fragile point you found during
testing.

---

## You must be able to explain

- Every step of the demo script in your own words, unscripted, if asked to
  walk through it again differently
- What the fallback plan is and why it exists — this itself is a good
  answer if a judge asks "what would you do if this were a real
  production incident and the tooling failed"
