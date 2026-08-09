"""Detection endpoints (docs/08 §4.5)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from cybersim.api.deps import CurrentUser, get_current_user
from cybersim.infra.errors import AppError, ErrorCode
from cybersim.platform.simulation.store import SimulationStore
from cybersim.response.executor import ResponseExecutor

router = APIRouter()


class DetectionResponse(BaseModel):
    detection_id: str
    simulation_id: str
    created_at: str
    threat_class: str
    title: str
    severity: str
    confidence: float
    confidence_band: str
    mitre: list[str]
    owasp: list[str]
    attack_path: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    rationale: str
    recommended_actions: list[dict[str, Any]]
    source: str
    validated: bool = True


class ExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str
    params: dict[str, Any] = Field(default_factory=dict)
    confirm: bool = False


class ExecuteResponse(BaseModel):
    execution_id: str
    detection_id: str
    action_id: str
    applied_at: str
    ack_channel: str
    events_emitted: int


def _to_detection_response(proposal: Any) -> DetectionResponse:
    return DetectionResponse(
        detection_id=f"det-{abs(hash(proposal.simulation_id + proposal.title))}",
        simulation_id=proposal.simulation_id,
        created_at="",
        threat_class=proposal.threat_class.value,
        title=proposal.title,
        severity=proposal.severity.value,
        confidence=proposal.confidence,
        confidence_band=proposal.confidence_band.value,
        mitre=list(proposal.mitre_techniques),
        owasp=list(proposal.owasp_refs),
        attack_path=[n.model_dump() for n in proposal.attack_path],
        evidence=[e.model_dump() for e in proposal.evidence],
        rationale=proposal.rationale,
        recommended_actions=[a.model_dump() for a in proposal.recommended_actions],
        source=proposal.source.value,
    )


@router.get("/simulations/{sim_id}/detections", response_model=list[DetectionResponse])
async def list_detections(
    sim_id: str,
    current: Annotated[CurrentUser, Depends(get_current_user)],
    request: Request,
) -> list[DetectionResponse]:
    store: SimulationStore = request.app.state.sim_store
    rec = store.get(current.org_id, sim_id)
    if rec is None:
        raise AppError(ErrorCode.SIM_NOT_FOUND, f"No simulation {sim_id!r}.")
    return [_to_detection_response(d) for d in rec.detections]


@router.get("/simulations/{sim_id}/detections/{detection_id}", response_model=DetectionResponse)
async def get_detection(
    sim_id: str,
    detection_id: str,
    current: Annotated[CurrentUser, Depends(get_current_user)],
    request: Request,
) -> DetectionResponse:
    store: SimulationStore = request.app.state.sim_store
    rec = store.get(current.org_id, sim_id)
    if rec is None:
        raise AppError(ErrorCode.SIM_NOT_FOUND, f"No simulation {sim_id!r}.")
    for d in rec.detections:
        if _to_detection_response(d).detection_id == detection_id:
            return _to_detection_response(d)
    raise AppError(ErrorCode.DETECTION_NOT_FOUND, f"No detection {detection_id!r}.")


@router.post(
    "/simulations/{sim_id}/detections/{detection_id}/execute",
    response_model=ExecuteResponse,
    status_code=202,
)
async def execute_response(
    sim_id: str,
    detection_id: str,
    payload: ExecuteRequest,
    current: Annotated[CurrentUser, Depends(get_current_user)],
    request: Request,
) -> ExecuteResponse:
    import uuid

    store: SimulationStore = request.app.state.sim_store
    rec = store.get(current.org_id, sim_id)
    if rec is None:
        raise AppError(ErrorCode.SIM_NOT_FOUND, f"No simulation {sim_id!r}.")

    # Require a matching detection to execute a response (docs/01 §3:
    # every executed action is backed by a detection).
    matched = any(_to_detection_response(d).detection_id == detection_id for d in rec.detections)
    if not matched:
        raise AppError(ErrorCode.DETECTION_NOT_FOUND, f"No detection {detection_id!r}.")

    if rec.simulator is None or rec.ctx is None:
        raise AppError(ErrorCode.SIM_STATUS_INVALID, "Simulation not in a runnable state.")

    executor = ResponseExecutor(simulator_id=rec.scenario_id and _simulator_id(rec))
    executor.check_allowed(payload.action_id)

    if payload.action_id in {"quarantine_host", "block_egress"} and not payload.confirm:
        raise AppError(
            ErrorCode.ACTION_UNCONFIRMED,
            "This action is high-risk and requires confirm=true.",
        )

    events = executor.execute(rec.simulator, rec.ctx, payload.action_id, payload.params)
    execution_id = str(uuid.uuid4())
    sim_time_ms = rec.ctx.clock.now_ms() if rec.ctx is not None else None
    store.add_executed_action(
        current.org_id,
        sim_id,
        execution_id=execution_id,
        detection_id=detection_id,
        action_id=payload.action_id,
        params=payload.params,
        executed_by=current.user_id,
        sim_time_ms=sim_time_ms,
    )
    hub = request.app.state.hub
    hub.publish(
        f"sim.{sim_id}",
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
        applied_at=__import__("datetime", fromlist=["datetime"])
        .datetime.now(__import__("datetime", fromlist=["timezone"]).timezone.utc)
        .isoformat(),
        ack_channel=f"sim.{sim_id}/actions",
        events_emitted=len(events),
    )


def _simulator_id(rec: Any) -> str:
    from cybersim.simulation.catalog import get_scenario

    try:
        return get_scenario(rec.scenario_id).simulator
    except KeyError:
        return "web"
