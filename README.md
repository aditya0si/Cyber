# CyberSim AI

> **CyberSim AI** creates controlled cyberattack scenarios, models their progression as an **attack graph**, and uses an **evidence-grounded AI agent** to **detect, explain, and recommend responses** to evolving threats.

This repository implements the platform described in `docs/`. The docs are the contract; code follows them verbatim where names, interfaces, and file paths are normative.

## Repository layout

```
cybersim/                  Python workspace (uv)
  events/                  canonical event contract + normalization + bus
  simulation/              scenario catalog + deterministic simulators (web/api/network/supply)
  graph/                   attack graph engine (NetworkX → Neo4j seam)
  analyst/                 LangGraph AI analyst + rule-based fallback + validator
  knowledge/               RAG knowledge base (MITRE/OWASP/CVE)
  api/                     FastAPI gateway (REST + WebSocket)
  realtime/                WS hub + Redis pub/sub fan-out
  platform/                auth, tenants, billing
  missions/                Mission Mode DSL + scoring
  infra/                   config, db, logging, telemetry
apps/web/                  Next.js 14 (App Router) frontend
infra/                     docker, terraform IaC
docs/                      Build documentation suite (00–21)
tests/                     Integration, replay, scenario-golden, e2e
```

## Prerequisites

- Python **3.11** (managed automatically by `uv`)
- Node **20+**, `pnpm` 9+
- Docker + Docker Compose

## Local dev (5 minutes)

```bash
# --- Backend ---
uv sync                       # create venv + install all deps
uv run python -m cybersim.tools.cli db upgrade      # apply migrations (when added)
uv run python -m cybersim.tools.cli seed --demo      # seed admin + free org

# --- Realtime infra ---
docker compose up -d postgres redis minio            # backing services

# --- Run API + worker ---
uv run uvicorn cybersim.api.main:app --reload --port 8000

# --- Frontend ---
cd apps/web
pnpm install
pnpm dev
```

## Verify (CI parity)

```bash
# Backend fast lane
uv run task verify-fast         # ruff + ruff format + mypy + pytest unit

# Web
cd apps/web && pnpm verify      # typecheck + lint + build
```

## Doc index

See `docs/00-README.md`. Build order lives in `docs/19-development-roadmap.md`; per-task AI-agent instructions live in `docs/21-ai-agent-build-instructions.md`.

## Status

Phase 0 — repository bootstrap — complete. Later phases track in `docs/19`.
