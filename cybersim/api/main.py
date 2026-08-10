"""FastAPI gateway factory (docs/08, docs/21 Task 4.1).

Phase 4 wires the in-memory dependencies so the API runs and is testable
without Postgres/Redis; Phase 9 swaps in real backing stores.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from cybersim.events.schema import CanonicalEvent
from cybersim.graph.event_mutator import apply_event_to_graph
from cybersim.infra.config import get_settings
from cybersim.infra.errors import AppError, ErrorCode, problem_detail
from cybersim.infra.errors.codes import error_status
from cybersim.infra.middleware import IdempotencyMiddleware, RateLimitMiddleware
from cybersim.platform.auth.jwt import JWTMint, build_jwt_mint_from_settings
from cybersim.platform.auth.repo import AuthRepository, InMemoryAuthRepository
from cybersim.platform.simulation.store import SimulationStore
from cybersim.realtime.hub import RealtimeHub
from cybersim.realtime.ticket import TicketStore
from cybersim.simulation.scenario import CredentialCompromiseScenario

_VALIDATION_TITLE = "Invalid request payload"


def create_app(
    *,
    auth_repo: AuthRepository | None = None,
    jwt_mint: JWTMint | None = None,
    sim_store: SimulationStore | None = None,
    hub: RealtimeHub | None = None,
    tickets: TicketStore | None = None,
    analyst_mode: str = "rules",
    ws_enabled: bool = True,
) -> FastAPI:
    """Build the FastAPI application with in-memory defaults (Phase 4 MVP)."""
    app = FastAPI(
        title="CyberSim AI API",
        version="0.1.0",
        description="CyberSim AI — Autonomous Cybersecurity Simulation & Response Platform",
        docs_url="/v1/docs" if False else "/docs",
        openapi_url="/v1/openapi.json",
        redoc_url=None,
    )

    app.state.auth_repo = auth_repo or InMemoryAuthRepository()
    app.state.jwt_mint = jwt_mint or build_jwt_mint_from_settings()
    app.state.sim_store = sim_store or SimulationStore()
    app.state.hub = hub or RealtimeHub()
    app.state.tickets = tickets or TicketStore()
    app.state.analyst_mode = analyst_mode
    app.state.ws_enabled = ws_enabled
    app.state.demo_scenario = CredentialCompromiseScenario()

    # Checkpoint A: Demo graph singleton
    from cybersim.graph.repo_nx import NetworkXGraphRepository
    from cybersim.simulation.web.simulator import build_environment_graph
    
    DEMO_SIM_ID = "demo"
    demo_repo = NetworkXGraphRepository()
    env = build_environment_graph("web.app.sqli_login")
    demo_repo.create(DEMO_SIM_ID, env)
    app.state.demo_repo = demo_repo
    app.state.demo_sim_id = DEMO_SIM_ID
    app.state.env_graph = env

    from cybersim.analyst.runtime import AnalystRuntime
    app.state.analyst_runtime = AnalystRuntime(repo=demo_repo, simulator_id="web", mode="rules")
    app.state.last_analysis = None

    app.add_middleware(IdempotencyMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_allow_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _register_handlers(app)
    _register_routers(app)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz() -> dict[str, str]:
        return {"status": "ready"}

    @app.post("/simulation/start")
    def start_demo_scenario(delay: float = 0.8) -> dict[str, str]:
        """Reset, re-seed the graph, then replay the scenario — applying each
        event to the graph as it lands so polling clients watch it build live.

        Declared as a sync route on purpose: the scenario sleeps between
        events, and FastAPI runs sync routes in the threadpool so the event
        loop stays free for concurrent /simulation/events + /graph polls.
        """
        demo_repo: NetworkXGraphRepository = app.state.demo_repo
        demo_repo.drop(app.state.demo_sim_id)
        demo_repo.create(app.state.demo_sim_id, app.state.env_graph)

        app.state.last_analysis = None

        def _apply(event: CanonicalEvent) -> None:
            apply_event_to_graph(event, demo_repo, app.state.demo_sim_id)

        app.state.demo_scenario.start(delay=delay, on_event=_apply)
        return {"status": "started"}

    @app.post("/simulation/reset")
    async def reset_demo_scenario() -> dict[str, str]:
        # Reset graph
        demo_repo: NetworkXGraphRepository = app.state.demo_repo
        demo_repo.drop(app.state.demo_sim_id)
        demo_repo.create(app.state.demo_sim_id, app.state.env_graph)
        
        app.state.demo_scenario.reset()
        app.state.last_analysis = None
        return {"status": "reset"}

    @app.get("/graph")
    async def get_demo_graph() -> dict[str, Any]:
        """Returns the demo graph in React Flow format."""
        import json
        demo_repo: NetworkXGraphRepository = app.state.demo_repo
        snap = json.loads(demo_repo.snapshot(app.state.demo_sim_id, 0))
        return snap

    @app.get("/simulation/events")
    async def get_demo_events() -> list[dict[str, Any]]:
        return [e.model_dump(mode="json") for e in app.state.demo_scenario.get_events()]

    @app.post("/analyst/analyze")
    async def analyze_demo_scenario() -> dict[str, Any]:
        """Runs the event stream through the analyst and pauses before execution."""
        from cybersim.analyst.runtime import AnalystRuntime

        runtime: AnalystRuntime = app.state.analyst_runtime
        events_dicts = app.state.demo_scenario.get_events()
        # They are Pydantic objects from scenario.py, not dicts
        events = events_dicts
        
        # We must make sure they are CanonicalEvent, which they are
        outcome = runtime.ingest_window(
            events,
            org_id="global",
            simulation_id=app.state.demo_sim_id,
            window_seq=0,
            env=app.state.demo_repo.graph_view(app.state.demo_sim_id)
        )
        app.state.last_analysis = outcome
        
        if outcome and outcome.result.ok and outcome.proposal:
            proposal = outcome.proposal
            return {
                "threat_card": {
                    "severity": proposal.severity.value,
                    "confidence": proposal.confidence,
                    "threat_class": proposal.threat_class.value,
                    "rationale": proposal.rationale,
                    "evidence": [e.summary for e in proposal.evidence],
                    "attack_path": [str(p) for p in proposal.attack_path] if proposal.attack_path else []
                },
                "recommended_actions": [a.model_dump(mode="json") for a in proposal.recommended_actions]
            }
        return {"status": "no_threat_detected"}

    @app.post("/analyst/approve-response")
    async def approve_response() -> dict[str, Any]:
        """Approve and execute the containment actions."""
        import datetime
        import uuid

        from cybersim.graph.event_mutator import apply_response_actions

        outcome = app.state.last_analysis
        if not outcome or not outcome.result.ok or not outcome.proposal:
            return {"status": "nothing_to_approve"}
            
        proposal = outcome.proposal
        
        # Mutate the graph
        apply_response_actions(app.state.demo_repo, app.state.demo_sim_id, proposal.recommended_actions)
        
        # Emit synthetic events to reflect containment
        for act in proposal.recommended_actions:
            app.state.demo_scenario.events.append(
                CanonicalEvent(
                    event_id=str(uuid.uuid4()),
                    timestamp=datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z"),
                    event_type="CONTAINMENT_EXECUTED",
                    severity="LOW",
                    source_ip="127.0.0.1",
                    target_asset="system",
                    actor="system",
                    raw_context={"action": act.action_id, "isolate": True, "block": True}
                )
            )
                
        return {"status": "approved_and_executed"}

    @app.get("/analyst/rag-sources")
    async def get_rag_sources() -> list[dict[str, Any]]:
        outcome = app.state.last_analysis
        if not outcome or not outcome.result.ok or not outcome.proposal:
            return []
        proposal = outcome.proposal
        return [e.model_dump(mode="json") for e in proposal.evidence]

    @app.get("/v1/.well-known/jwks.json")
    async def jwks() -> dict[str, Any]:
        mint: JWTMint = app.state.jwt_mint
        return mint.jwks()

    if ws_enabled:

        @app.websocket("/v1/ws")
        async def websocket_endpoint(ws: WebSocket) -> None:
            ticket_token = ws.query_params.get("ticket", "")
            ticket = app.state.tickets.consume(ticket_token)
            if ticket is None:
                await ws.close(code=4401, reason="invalid ticket")
                return
            channel = ws.query_params.get("channel", "")
            channels = [channel] if channel else []
            await app.state.hub.handle_connection(
                ws, session_id=ticket.session_id, channels=channels
            )

    return app


def _register_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=error_status(exc.code),
            content=problem_detail(
                exc.code,
                exc.detail or exc.code.value,
                instance=str(request.url.path),
                extra=exc.extra or None,
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        violations = [
            {
                "field": ".".join(str(loc) for loc in err.get("loc", [])),
                "code": str(err.get("type", "validation")),
                "message": err.get("msg", ""),
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=problem_detail(
                ErrorCode.VALIDATION,
                "One or more request fields failed validation.",
                instance=str(request.url.path),
                violations=violations,
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content=problem_detail(
                ErrorCode.VALIDATION,
                "Internal error.",
                instance=str(request.url.path),
            ),
        )


def _register_routers(app: FastAPI) -> None:
    from cybersim.api.routers import (
        auth as auth_router,
    )
    from cybersim.api.routers import (
        billing as billing_router,
    )
    from cybersim.api.routers import (
        detections as detections_router,
    )
    from cybersim.api.routers import (
        graph as graph_router,
    )
    from cybersim.api.routers import (
        knowledge as knowledge_router,
    )
    from cybersim.api.routers import (
        missions as missions_router,
    )
    from cybersim.api.routers import (
        orgs as orgs_router,
    )
    from cybersim.api.routers import (
        public_missions as public_router,
    )
    from cybersim.api.routers import (
        scenarios as scenarios_router,
    )
    from cybersim.api.routers import (
        simulations as simulations_router,
    )

    app.include_router(auth_router.router, prefix="/v1", tags=["auth"])
    app.include_router(orgs_router.router, prefix="/v1", tags=["orgs"])
    app.include_router(scenarios_router.router, prefix="/v1", tags=["scenarios"])
    app.include_router(simulations_router.router, prefix="/v1", tags=["simulations"])
    app.include_router(detections_router.router, prefix="/v1", tags=["detections"])
    app.include_router(graph_router.router, prefix="/v1", tags=["graph"])
    app.include_router(knowledge_router.router, prefix="/v1", tags=["knowledge"])
    app.include_router(missions_router.router, prefix="/v1", tags=["missions"])
    app.include_router(billing_router.router, prefix="/v1", tags=["billing"])
    app.include_router(public_router.router, prefix="/v1", tags=["public"])
