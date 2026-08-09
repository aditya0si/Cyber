"""Mission endpoints (docs/08 §4.8, docs/14)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel

from cybersim.api.deps import CurrentUser, get_current_user
from cybersim.api.routers.simulations import _run_simulation, start_simulation
from cybersim.infra.errors import AppError, ErrorCode
from cybersim.missions.catalog import get_mission, list_missions
from cybersim.missions.scoring import score_mission
from cybersim.missions.share import generate_share_token
from cybersim.platform.simulation.store import SimulationStore

router = APIRouter()


class MissionObjective(BaseModel):
    id: str
    title: str
    kind: str
    points: int


class MissionDetail(BaseModel):
    id: str
    title: str
    subtitle: str
    simulator: str
    scenario_id: str
    duration_sec: int
    objectives: list[MissionObjective]
    max_score: int
    shareable: bool


class MissionStarted(BaseModel):
    simulation_id: str
    mission_id: str
    ws_channel: str
    share_url: str | None = None
    status: str = "queued"


class ObjectiveResultOut(BaseModel):
    objective_id: str
    achieved: bool
    points: int
    detail: str


class MissionScoreOut(BaseModel):
    mission_id: str
    score: int
    max_score: int
    final: bool
    objectives: list[ObjectiveResultOut]


@router.get("/missions", response_model=list[MissionDetail])
async def list_endpoint(
    _current: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[MissionDetail]:
    out: list[MissionDetail] = []
    for m in list_missions():
        out.append(
            MissionDetail(
                id=m.id,
                title=m.title,
                subtitle=m.subtitle,
                simulator=m.simulator,
                scenario_id=m.scenario_id,
                duration_sec=m.duration_sec,
                objectives=[
                    MissionObjective(id=o.id, title=o.title, kind=o.kind, points=o.points)
                    for o in m.objectives
                ],
                max_score=m.scoring.max_score,
                shareable=m.sharing.public_default,
            )
        )
    return out


@router.get("/missions/{mission_id}", response_model=MissionDetail)
async def detail(
    mission_id: str,
    _current: Annotated[CurrentUser, Depends(get_current_user)],
) -> MissionDetail:
    try:
        m = get_mission(mission_id)
    except KeyError:
        raise AppError(ErrorCode.MISSION_NOT_FOUND, f"No mission {mission_id!r}.") from None
    return MissionDetail(
        id=m.id,
        title=m.title,
        subtitle=m.subtitle,
        simulator=m.simulator,
        scenario_id=m.scenario_id,
        duration_sec=m.duration_sec,
        objectives=[
            MissionObjective(id=o.id, title=o.title, kind=o.kind, points=o.points)
            for o in m.objectives
        ],
        max_score=m.scoring.max_score,
        shareable=m.sharing.public_default,
    )


@router.post("/missions/{mission_id}/start", response_model=MissionStarted, status_code=202)
async def start(
    mission_id: str,
    background: BackgroundTasks,
    request: Request,
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> MissionStarted:
    try:
        mission = get_mission(mission_id)
    except KeyError:
        raise AppError(ErrorCode.MISSION_NOT_FOUND, f"No mission {mission_id!r}.") from None

    share_token = generate_share_token() if mission.sharing.public_default else None
    _scen, record = start_simulation(
        request,
        org_id=current.org_id,
        scenario_id=mission.scenario_id,
        seed=7,
        params={"mission": mission_id},
        label=f"mission:{mission_id}",
        mission_id=mission_id,
        is_mission=True,
        public_share_token=share_token,
    )
    background.add_task(
        _run_simulation,
        request,
        current.org_id,
        record.id,
        mission.scenario_id,
        7,
        {"mission": mission_id},
    )
    return MissionStarted(
        simulation_id=record.id,
        mission_id=mission_id,
        ws_channel=f"sim.{record.id}",
        share_url=f"/m/{share_token}" if share_token else None,
    )


@router.get("/simulations/{sim_id}/score", response_model=MissionScoreOut)
async def score(
    sim_id: str,
    current: Annotated[CurrentUser, Depends(get_current_user)],
    request: Request,
) -> MissionScoreOut:
    store: SimulationStore = request.app.state.sim_store
    rec = store.get(current.org_id, sim_id)
    if rec is None:
        raise AppError(ErrorCode.SIM_NOT_FOUND, f"No simulation {sim_id!r}.")
    if not rec.is_mission or rec.mission_id is None:
        raise AppError(ErrorCode.SIM_STATUS_INVALID, "Simulation is not a mission.")

    mission = get_mission(rec.mission_id)
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
            ObjectiveResultOut(
                objective_id=o.objective_id,
                achieved=o.achieved,
                points=o.points,
                detail=o.detail,
            )
            for o in result.objectives
        ],
    )
