"""Public share endpoints for Mission Mode (docs/14 §5).

Judge-mode (pseudo-tenant `(public-mission)`) routes: no auth, token-addressed,
read-only except the whitelisted+validated execute gate, per-token rate limited.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import APIRouter, Query, Request

from cybersim.api.routers.detections import (
    ExecuteRequest,
    ExecuteResponse,
    _to_detection_response,
)
from cybersim.api.routers.missions import MissionDetail, MissionScoreOut
from cybersim.infra.errors import AppError, ErrorCode
from cybersim.missions.catalog import get_mission
from cybersim.missions.scoring import score_mission
from cybersim.platform.simulation.store import SimulationRecord, SimulationStore
from cybersim.response.executor import ResponseExecutor

router = APIRouter()

# Judge execute gate: max executes per token per window (docs/14 §5).
_MAX_EXECUTES = 5
_EXECUTE_WINDOW_SEC = 60.0
_execute_log: dict[str, list[float]] = {}


class PublicMissionView(MissionDetail):
    simulation_id: str
    sim_status: str
    started_at: str | None = None
    ended_at: str | None = None


def _by_token(request: Request, token: str) -> SimulationRecord:
    store: SimulationStore = request.app.state.sim_store
    rec = store.get_by_share_token(token)
    if rec is None:
        raise AppError(ErrorCode.SIM_NOT_FOUND, "Unknown or expired share link.")
    if not rec.is_mission or rec.mission_id is None:
        raise AppError(ErrorCode.SIM_STATUS_INVALID, "Simulation is not a mission.")
    return rec


def _mission_detail(rec: SimulationRecord) -> PublicMissionView:
    mission = get_mission(rec.mission_id)  # type: ignore[arg-type]
    return PublicMissionView(
        id=mission.id,
        title=mission.title,
        subtitle=mission.subtitle,
        simulator=mission.simulator,
        scenario_id=mission.scenario_id,
        duration_sec=mission.duration_sec,
        objectives=[
            {"id": o.id, "title": o.title, "kind": o.kind, "points": o.points}
            for o in mission.objectives
        ],
        max_score=mission.scoring.max_score,
        shareable=mission.sharing.public_default,
        simulation_id=rec.id,
        sim_status=rec.status,
        started_at=rec.started_at.isoformat() if rec.started_at else None,
        ended_at=rec.ended_at.isoformat() if rec.ended_at else None,
    )


def _check_rate_limit(token: str) -> None:
    now = time.monotonic()
    window = [t for t in _execute_log.get(token, []) if now - t < _EXECUTE_WINDOW_SEC]
    if len(window) >= _MAX_EXECUTES:
        raise AppError(
            ErrorCode.RATE_LIMITED,
            "Share link exceeded the judge action limit; try again later.",
        )


def _mark_execute(token: str) -> None:
    now = time.monotonic()
    _execute_log.setdefault(token, []).append(now)


@router.get("/public/missions/{token}", response_model=PublicMissionView)
async def mission_by_token(token: str, request: Request) -> PublicMissionView:
    return _mission_detail(_by_token(request, token))


@router.get("/public/simulations/{token}/events")
async def list_events(
    token: str,
    request: Request,
    limit: int = Query(default=200, le=500),
    cursor: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    rec = _by_token(request, token)
    events = rec.events[cursor : cursor + limit]
    return {
        "items": [e.model_dump(mode="json") for e in events],
        "cursor": cursor + len(events),
        "has_more": cursor + len(events) < len(rec.events),
        "total": len(rec.events),
    }


@router.get("/public/simulations/{token}/detections")
async def list_detections(token: str, request: Request) -> list[Any]:
    rec = _by_token(request, token)
    return [_to_detection_response(d) for d in rec.detections]


@router.get("/public/simulations/{token}/score", response_model=MissionScoreOut)
async def score(token: str, request: Request) -> MissionScoreOut:
    rec = _by_token(request, token)
    mission = get_mission(rec.mission_id)  # type: ignore[arg-type]
    result = score_mission(
        mission,
        events=rec.events,
        detections=rec.detections,
        actions=rec.executed_actions,
    )
    final = rec.status in ("completed", "failed", "stopped")
    return MissionScoreOut(
        mission_id=result.mission_id,
        score=result.score,
        max_score=result.max_score,
        final=final,
        objectives=[
            {
                "objective_id": o.objective_id,
                "achieved": o.achieved,
                "points": o.points,
                "detail": o.detail,
            }
            for o in result.objectives
        ],
    )


@router.post(
    "/public/simulations/{token}/detections/{detection_id}/execute",
    response_model=ExecuteResponse,
    status_code=202,
)
async def execute_response(
    token: str,
    detection_id: str,
    payload: ExecuteRequest,
    request: Request,
) -> ExecuteResponse:
    rec = _by_token(request, token)
    _check_rate_limit(token)

    matched = any(_to_detection_response(d).detection_id == detection_id for d in rec.detections)
    if not matched:
        raise AppError(ErrorCode.DETECTION_NOT_FOUND, f"No detection {detection_id!r}.")

    if rec.simulator is None or rec.ctx is None:
        raise AppError(ErrorCode.SIM_STATUS_INVALID, "Simulation not in a runnable state.")

    executor = ResponseExecutor(simulator_id="web")
    executor.check_allowed(payload.action_id)

    if payload.action_id in {"quarantine_host", "block_egress"} and not payload.confirm:
        raise AppError(
            ErrorCode.ACTION_UNCONFIRMED,
            "This action is high-risk and requires confirm=true.",
        )

    events = executor.execute(rec.simulator, rec.ctx, payload.action_id, payload.params)
    _mark_execute(token)
    execution_id = str(uuid.uuid4())
    store: SimulationStore = request.app.state.sim_store
    store.add_executed_action(
        rec.org_id,
        rec.id,
        execution_id=execution_id,
        detection_id=detection_id,
        action_id=payload.action_id,
        params=payload.params,
        executed_by="(public-mission)",
    )
    request.app.state.hub.publish(
        f"sim.{rec.id}",
        {
            "kind": "action.executed",
            "execution_id": execution_id,
            "detection_id": detection_id,
            "action_id": payload.action_id,
            "events_emitted": len(events),
        },
    )
    return ExecuteResponse(
        execution_id=execution_id,
        detection_id=detection_id,
        action_id=payload.action_id,
        applied_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        ack_channel=f"sim.{rec.id}/actions",
        events_emitted=len(events),
    )
