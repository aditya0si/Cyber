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

from cybersim.infra.config import get_settings
from cybersim.infra.errors import AppError, ErrorCode, problem_detail
from cybersim.infra.errors.codes import error_status
from cybersim.infra.middleware import IdempotencyMiddleware, RateLimitMiddleware
from cybersim.platform.auth.jwt import JWTMint, build_jwt_mint_from_settings
from cybersim.platform.auth.repo import AuthRepository, InMemoryAuthRepository
from cybersim.platform.simulation.store import SimulationStore
from cybersim.realtime.hub import RealtimeHub
from cybersim.realtime.ticket import TicketStore

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
