"""In-memory simulation registry (Phase 4 MVP; Phase 9 swaps to Postgres)."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from cybersim.analyst.dto import DetectionProposal
from cybersim.events.schema import CanonicalEvent


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


@dataclass
class SimulationRecord:
    id: str
    org_id: str
    scenario_id: str
    seed: int
    params: dict[str, Any] = field(default_factory=dict)
    status: str = "queued"  # queued|running|paused|completed|failed|stopped
    phase: str | None = None
    label: str | None = None
    mission_id: str | None = None
    is_mission: bool = False
    public_share_token: str | None = None
    created_at: datetime = field(default_factory=_utcnow)
    started_at: datetime | None = None
    ended_at: datetime | None = None
    events: list[CanonicalEvent] = field(default_factory=list)
    detections: list[DetectionProposal] = field(default_factory=list)
    executed_actions: list[dict[str, Any]] = field(default_factory=list)
    simulator: Any = None  # live Simulator instance (Phase 4 MVP)
    ctx: Any = None  # SimContext used to drive the sim
    error: str | None = None

    @property
    def mission_score(self) -> dict[str, Any] | None:
        """Cached MissionScore dict (set by the missions router after compute)."""
        return self._mission_score

    @mission_score.setter
    def mission_score(self, value: dict[str, Any] | None) -> None:
        self._mission_score = value

    def __post_init__(self) -> None:
        object.__setattr__(self, "_mission_score", None)


class SimulationStore:
    """Thread-safe in-memory registry keyed by org_id then simulation_id."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sims: dict[str, dict[str, SimulationRecord]] = {}

    def create(
        self,
        org_id: str,
        scenario_id: str,
        seed: int,
        params: dict[str, Any],
        label: str | None = None,
        mission_id: str | None = None,
        is_mission: bool = False,
        public_share_token: str | None = None,
    ) -> SimulationRecord:
        sim_id = str(uuid.uuid4())
        record = SimulationRecord(
            id=sim_id,
            org_id=org_id,
            scenario_id=scenario_id,
            seed=seed,
            params=dict(params),
            label=label,
            mission_id=mission_id,
            is_mission=is_mission,
            public_share_token=public_share_token,
        )
        with self._lock:
            self._sims.setdefault(org_id, {})[sim_id] = record
        return record

    def get(self, org_id: str, sim_id: str) -> SimulationRecord | None:
        with self._lock:
            return self._sims.get(org_id, {}).get(sim_id)

    def get_by_share_token(self, token: str) -> SimulationRecord | None:
        """Resolve a public share token to a mission run (docs/14 §5)."""
        with self._lock:
            for org_sims in self._sims.values():
                for rec in org_sims.values():
                    if rec.public_share_token == token:
                        return rec
        return None

    def list(self, org_id: str) -> list[SimulationRecord]:
        with self._lock:
            return list(self._sims.get(org_id, {}).values())

    def running_count(self, org_id: str) -> int:
        with self._lock:
            return sum(
                1
                for rec in self._sims.get(org_id, {}).values()
                if rec.status in ("queued", "running")
            )

    def set_status(self, org_id: str, sim_id: str, status: str, phase: str | None = None) -> None:
        record = self.get(org_id, sim_id)
        if record is None:
            raise KeyError(f"no simulation {sim_id!r} for org {org_id!r}")
        record.status = status
        if phase is not None:
            record.phase = phase
        if status == "running" and record.started_at is None:
            record.started_at = _utcnow()
        if status in ("completed", "failed", "stopped") and record.ended_at is None:
            record.ended_at = _utcnow()

    def add_event(self, org_id: str, sim_id: str, event: CanonicalEvent) -> None:
        record = self.get(org_id, sim_id)
        if record is not None:
            record.events.append(event)

    def add_detection(self, org_id: str, sim_id: str, proposal: DetectionProposal) -> None:
        record = self.get(org_id, sim_id)
        if record is not None:
            record.detections.append(proposal)

    def add_executed_action(
        self,
        org_id: str,
        sim_id: str,
        *,
        execution_id: str,
        detection_id: str | None,
        action_id: str,
        params: dict[str, Any],
        executed_by: str,
        result: str = "applied",
        sim_time_ms: int | None = None,
    ) -> None:
        record = self.get(org_id, sim_id)
        if record is not None:
            record.executed_actions.append(
                {
                    "execution_id": execution_id,
                    "detection_id": detection_id,
                    "action_id": action_id,
                    "params": params,
                    "executed_by": executed_by,
                    "result": result,
                    "sim_time_ms": sim_time_ms,
                    "executed_at": _utcnow().isoformat(),
                }
            )
