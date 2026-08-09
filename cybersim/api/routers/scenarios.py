"""Scenario catalog endpoints (docs/08 §4.3)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from cybersim.api.deps import CurrentUser, get_current_user
from cybersim.infra.errors import AppError, ErrorCode
from cybersim.simulation.catalog import get_scenario, list_scenarios

router = APIRouter()


class ScenarioDisplay(BaseModel):
    title: str
    blurb: str
    category: str
    difficulty: str
    duration_sec: int


class ScenarioSummary(BaseModel):
    id: str
    simulator: str
    category: str
    status: str
    display: ScenarioDisplay


class ScenarioDetail(ScenarioSummary):
    params_default: dict[str, object]


@router.get("/scenarios", response_model=list[ScenarioSummary])
async def list_endpoint(
    _current: Annotated[CurrentUser, Depends(get_current_user)],
    simulator: str | None = Query(default=None),
    category: str | None = Query(default=None),
    difficulty: str | None = Query(default=None),
    include_roadmap: bool = Query(default=False),
) -> list[ScenarioSummary]:
    out: list[ScenarioSummary] = []
    for scen in list_scenarios(
        simulator=simulator,
        category=category,
        difficulty=difficulty,
        include_roadmap=include_roadmap,
    ):
        out.append(
            ScenarioSummary(
                id=scen.id,
                simulator=scen.simulator,
                category=scen.display.category,
                status=scen.status,
                display=ScenarioDisplay(
                    title=scen.display.title,
                    blurb=scen.display.blurb,
                    category=scen.display.category,
                    difficulty=scen.display.difficulty,
                    duration_sec=scen.display.duration_sec,
                ),
            )
        )
    return out


@router.get("/scenarios/{scenario_id}", response_model=ScenarioDetail)
async def detail(
    scenario_id: str,
    _current: Annotated[CurrentUser, Depends(get_current_user)],
) -> ScenarioDetail:
    try:
        scen = get_scenario(scenario_id)
    except KeyError:
        raise AppError(ErrorCode.SCENARIO_NOT_FOUND, f"Unknown scenario {scenario_id!r}.") from None
    return ScenarioDetail(
        id=scen.id,
        simulator=scen.simulator,
        category=scen.display.category,
        status=scen.status,
        display=ScenarioDisplay(
            title=scen.display.title,
            blurb=scen.display.blurb,
            category=scen.display.category,
            difficulty=scen.display.difficulty,
            duration_sec=scen.display.duration_sec,
        ),
        params_default=dict(scen.params_default),
    )
