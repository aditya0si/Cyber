"""Simulation endpoints + background run orchestration (docs/08 §4.4)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from cybersim.api.deps import CurrentUser, get_current_user
from cybersim.events.normalizer_tasks import NormalizedSink, NormalizerConsumer
from cybersim.infra.errors import AppError, ErrorCode
from cybersim.platform.simulation.store import SimulationRecord, SimulationStore
from cybersim.simulation.catalog import get_scenario, scenario_params
from cybersim.simulation.tasks import build_context, get_simulator_class
from cybersim.simulation.web.simulator import build_environment_graph

router = APIRouter()

MAX_CONCURRENT_SIMS = 20  # MVP entitlement floor (docs/16 Free tier cap 1 → pro 5)


class CreateSimulationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    params: dict[str, Any] = Field(default_factory=dict)
    seed: int | None = None
    label: str | None = None


class SimulationCreated(BaseModel):
    simulation_id: str
    status: str
    ws_channel: str
    scenario: dict[str, Any]
    graph_seed_seq: int = 0
    entitlements: dict[str, Any]


class SimulationSummary(BaseModel):
    id: str
    org_id: str
    scenario_id: str
    seed: int
    status: str
    phase: str | None
    label: str | None
    created_at: str
    started_at: str | None
    ended_at: str | None
    events_count: int
    detections_count: int
    actions_count: int


class SimulationDetail(SimulationSummary):
    params: dict[str, Any]
    error: str | None = None


@router.post("/simulations", response_model=SimulationCreated, status_code=202)
async def create_simulation(
    payload: CreateSimulationRequest,
    background: BackgroundTasks,
    request: Request,
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> SimulationCreated:
    scen, record = start_simulation(
        request,
        org_id=current.org_id,
        scenario_id=payload.scenario_id,
        seed=payload.seed if payload.seed is not None else 7,
        params=payload.params,
        label=payload.label,
    )
    background.add_task(
        _run_simulation,
        request,
        current.org_id,
        record.id,
        payload.scenario_id,
        payload.seed if payload.seed is not None else 7,
        payload.params,
    )
    return SimulationCreated(
        simulation_id=record.id,
        status="queued",
        ws_channel=f"sim.{record.id}",
        scenario={
            "id": scen.id,
            "display": {
                "title": scen.display.title,
                "blurb": scen.display.blurb,
                "category": scen.display.category,
                "difficulty": scen.display.difficulty,
                "duration_sec": scen.display.duration_sec,
            },
        },
        entitlements={
            "max_concurrent_sims": MAX_CONCURRENT_SIMS,
            "ai_tier": request.app.state.analyst_mode,
        },
    )


def start_simulation(
    request: Request,
    *,
    org_id: str,
    scenario_id: str,
    seed: int,
    params: dict[str, Any],
    label: str | None = None,
    mission_id: str | None = None,
    is_mission: bool = False,
    public_share_token: str | None = None,
) -> tuple[Any, SimulationRecord]:
    """Create + queue a simulation record (shared by sim + mission start)."""
    try:
        scen = get_scenario(scenario_id)
    except KeyError:
        raise AppError(ErrorCode.SCENARIO_NOT_FOUND, f"Unknown scenario {scenario_id!r}.") from None

    store: SimulationStore = request.app.state.sim_store
    if store.running_count(org_id) >= MAX_CONCURRENT_SIMS:
        raise AppError(
            ErrorCode.SIM_CONCURRENCY_LIMIT,
            f"Org already has {MAX_CONCURRENT_SIMS} concurrent simulations.",
        )

    record = store.create(
        org_id=org_id,
        scenario_id=scenario_id,
        seed=seed,
        params=params,
        label=label,
        mission_id=mission_id,
        is_mission=is_mission,
        public_share_token=public_share_token,
    )
    store.set_status(org_id, record.id, "queued", phase="scheduling")
    return scen, record


async def _run_simulation(
    request: Request,
    org_id: str,
    sim_id: str,
    scenario_id: str,
    seed: int,
    params: dict[str, Any],
) -> None:
    """Background task: drive the simulator, normalize, analyze, publish WS."""
    store: SimulationStore = request.app.state.sim_store
    record = store.get(org_id, sim_id)
    if record is None:
        return
    store.set_status(org_id, sim_id, "running", phase="init")
    hub = request.app.state.hub
    channel = f"sim.{sim_id}"
    hub.publish(channel, {"kind": "sim.status", "status": "running", "phase": "init"})

    try:
        env_graph = build_environment_graph(scenario_id)
        ctx = build_context(
            org_id=org_id,
            simulation_id=sim_id,
            scenario_id=scenario_id,
            seed=seed,
            params=scenario_params(scenario_id, override=params),
        )
        simulator_class = get_simulator_class(get_scenario(scenario_id).simulator)
        simulator = simulator_class()
        simulator.init(ctx)
        record.simulator = simulator
        record.ctx = ctx

        from cybersim.graph.repo_nx import NetworkXGraphRepository

        repo = NetworkXGraphRepository()
        repo.create(sim_id, env_graph)

        sink = NormalizedSink()

        from cybersim.events.bus import InMemoryEventBus

        bus = InMemoryEventBus()
        consumer = NormalizerConsumer(
            bus=bus,
            graph_repo=repo,
            env_graph_lookup=lambda _s: env_graph,
            sink=sink,
        )

        # Beat loop: emit raw events per beat; drain the bus after each beat so
        # WS frames stream as the sim progresses.
        for beat in simulator.beats(ctx):
            for ev in beat.events:
                await bus.publish_raw(ev, org_id, sim_id)
                ctx.clock.set_to(beat.sim_time_ms)
            await consumer.drain(org_id, sim_id, max_events=10_000)
            for ce in sink.events[len(record.events) :]:
                record.events.append(ce)
                hub.publish(
                    channel,
                    {
                        "kind": "event.upsert",
                        "event": ce.model_dump(mode="json"),
                    },
                )
            hub.publish(channel, {"kind": "sim.lag", "lag_ms": 0})

        # Analyst pass over the full canonical window (rules mode in Phase 4;
        # ai mode in Phase 6 — wired via app.state for injectable deps).
        from cybersim.analyst import AnalystRuntime

        runtime = AnalystRuntime(
            repo=repo,
            simulator_id=simulator.id,
            mode=request.app.state.analyst_mode,
            llm=getattr(request.app.state, "analyst_llm", None),
            knowledge_repo=getattr(request.app.state, "knowledge_repo", None),
            allowed_action_ids=tuple(getattr(request.app.state, "analyst_allowed", ())),
        )
        outcomes = runtime.ingest_window_all(
            list(sink.events),
            org_id=org_id,
            simulation_id=sim_id,
            window_seq=0,
            env=env_graph,
        )
        from cybersim.api.routers.detections import _to_detection_response

        for outcome in outcomes:
            if outcome.result.ok and outcome.proposal is not None:
                proposal = outcome.proposal
                record.detections.append(proposal)
                hub.publish(
                    channel,
                    {
                        "kind": "detection.created",
                        "detection": _to_detection_response(proposal).model_dump(mode="json"),
                    },
                )

        store.set_status(org_id, sim_id, "completed", phase="finished")
        hub.publish(channel, {"kind": "sim.status", "status": "completed", "phase": "finished"})
    except Exception as exc:
        record.error = str(exc)
        store.set_status(org_id, sim_id, "failed")
        hub.publish(channel, {"kind": "sim.status", "status": "failed", "reason": str(exc)})


@router.get("/simulations", response_model=list[SimulationSummary])
async def list_simulations(
    current: Annotated[CurrentUser, Depends(get_current_user)],
    request: Request,
    status: str | None = Query(default=None),
) -> list[SimulationSummary]:
    store: SimulationStore = request.app.state.sim_store
    out: list[SimulationSummary] = []
    for rec in sorted(store.list(current.org_id), key=lambda r: r.created_at, reverse=True):
        if status and rec.status != status:
            continue
        out.append(_to_summary(rec))
    return out


@router.get("/simulations/{sim_id}", response_model=SimulationDetail)
async def get_simulation(
    sim_id: str,
    current: Annotated[CurrentUser, Depends(get_current_user)],
    request: Request,
) -> SimulationDetail:
    store: SimulationStore = request.app.state.sim_store
    rec = store.get(current.org_id, sim_id)
    if rec is None:
        raise AppError(ErrorCode.SIM_NOT_FOUND, f"No simulation {sim_id!r}.")
    return _to_detail(rec)


@router.get("/simulations/{sim_id}/events")
async def list_events(
    sim_id: str,
    current: Annotated[CurrentUser, Depends(get_current_user)],
    request: Request,
    limit: int = Query(default=200, le=500),
    cursor: int = Query(default=0, ge=0),
    category: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    benign: bool | None = Query(default=None),
) -> dict[str, Any]:
    store: SimulationStore = request.app.state.sim_store
    rec = store.get(current.org_id, sim_id)
    if rec is None:
        raise AppError(ErrorCode.SIM_NOT_FOUND, f"No simulation {sim_id!r}.")
    # `category`/`benign` are carried in raw_context (CanonicalEvent itself only
    # exposes the 8 contract fields, docs/00 §5); `severity` is the contract field.
    page = rec.events[cursor : cursor + limit]
    events = page
    if category:
        events = [e for e in events if e.raw_context.get("category") == category]
    if severity:
        events = [e for e in events if e.severity == severity]
    if benign is not None:
        events = [e for e in events if bool(e.raw_context.get("benign", False)) == benign]
    return {
        "items": [e.model_dump(mode="json") for e in events],
        "cursor": cursor + len(page),
        "has_more": cursor + len(page) < len(rec.events),
        "total": len(rec.events),
    }


@router.post("/simulations/{sim_id}/stop", status_code=202)
async def stop_simulation(
    sim_id: str,
    current: Annotated[CurrentUser, Depends(get_current_user)],
    request: Request,
) -> dict[str, Any]:
    store: SimulationStore = request.app.state.sim_store
    rec = store.get(current.org_id, sim_id)
    if rec is None:
        raise AppError(ErrorCode.SIM_NOT_FOUND, f"No simulation {sim_id!r}.")
    if rec.status in ("completed", "failed", "stopped"):
        raise AppError(ErrorCode.SIM_STATUS_INVALID, f"Simulation already {rec.status}.")
    store.set_status(current.org_id, sim_id, "stopped", phase="stopped")
    return {"simulation_id": sim_id, "status": "stopped"}


def _to_summary(rec: SimulationRecord) -> SimulationSummary:
    return SimulationSummary(
        id=rec.id,
        org_id=rec.org_id,
        scenario_id=rec.scenario_id,
        seed=rec.seed,
        status=rec.status,
        phase=rec.phase,
        label=rec.label,
        created_at=rec.created_at.isoformat(),
        started_at=rec.started_at.isoformat() if rec.started_at else None,
        ended_at=rec.ended_at.isoformat() if rec.ended_at else None,
        events_count=len(rec.events),
        detections_count=len(rec.detections),
        actions_count=len(rec.executed_actions),
    )


def _to_detail(rec: SimulationRecord) -> SimulationDetail:
    summary = _to_summary(rec)
    return SimulationDetail(**summary.model_dump(), params=dict(rec.params), error=rec.error)
