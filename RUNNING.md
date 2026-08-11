# RUNNING.md — how to run the CyberSim AI demo

Two commands, offline, no API keys, no Docker. Everything is in-memory.

## Prerequisites

- Python 3.11+ with [uv](https://github.com/astral-sh/uv)
- Node 20+ with [pnpm](https://pnpm.io) (11.x)

## 1. Backend (terminal A)

```powershell
cd cybersim && uv sync          # once
uv run uvicorn cybersim.api.main:create_app --factory --port 8000
```

- API docs: `http://localhost:8000/docs`
- Demo endpoints (no auth): `POST /simulation/start`, `GET /simulation/events`,
  `GET /graph`, `POST /analyst/analyze`, `POST /analyst/approve-response`,
  `GET /analyst/rag-sources`, `POST /simulation/reset`
- Default analyst mode is `mode="rules"` — zero LLM/network calls.
  LLM mode is only active if `OPENAI_API_KEY` is set in `.env`.

## 2. Frontend (terminal B)

```powershell
cd apps/web && pnpm install     # once
pnpm dev                        # http://localhost:3000
```

Open **http://localhost:3000/demo** — the four-panel demo dashboard.

## 3. The 2-minute demo run

1. Click **Start Simulation**. Events stream in ~0.8s apart (failed logins →
   successful login → privilege escalation → database access).
2. Watch the **attack graph** build live: attacker node, brute-force attack,
   compromised account, DB at-risk — animated dashed edges are the attack
   narrative links.
3. When the scenario finishes, the **AI analyst card** appears automatically:
   CRITICAL / data exfiltration, 60% confidence, evidence list, and the real
   graph-query attack path:
   `Attacker (192.168.1.100) → Attack (brute_force) → /api/login → User Database → user_data`
   Click **Explain** / **Recommended response** to expand.
4. Click **Execute Response** (deliberate confirm step — this is the human
   approval gate). Watch the graph flip: account **isolated**, database
   **blocked**, containment events in the stream, card shows **CONTAINED**.
5. **Reset** and re-run anytime — deterministic, repeatable, no restart.

## Known fragile points + one-line workarounds

| Fragile point | Workaround |
|---|---|
| Graph panel looks empty until first event lands | It renders the seeded environment as soon as you open the page; first attack node appears within ~1s of starting |
| Backend port 8000 already in use | Run `uv run uvicorn ... --port 8123` and set `NEXT_PUBLIC_API_ORIGIN=http://localhost:8123` before `pnpm dev` |
| `sentence-transformers` model download fails (no internet) | Not a problem — RAG auto-falls back to TF-IDF offline (logged, not shown in UI) |
| Event stream jumps to the end after a burst | It's reverse-chronological (newest on top) by design; polling is 1s so bursts land within one tick |
| Anything crashes mid-demo | `POST /simulation/reset` (or the Reset button) restores a clean seeded state |

## Demo-day fallback plan

1. **Screen recording** of a clean run is the primary fallback (record once
   everything is stable).
2. **Screenshots** of each stage belong on slide 3 of the deck.
3. **Offline-first is the reliability story**: no external API calls means no
   wifi-related failure — this is deliberate (see `instructions/00` scope).
4. If the live backend is down, the demo cannot run without it — start it
   first and keep the terminal visible; healthcheck at `GET /healthz`.

## Determinism guarantee

The scenario is a scripted state machine — same event sequence, severities,
actors, and graph structure on every run (timestamps/uuids vary by design).
See `tests/simulation/test_scenario.py` and the Stage 05 run log in
`AUDIT.md`.
