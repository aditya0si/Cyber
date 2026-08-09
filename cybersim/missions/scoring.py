"""Mission scoring engine (docs/14 §4).

Evaluates objectives deterministically against the simulation record:
  - events (CanonicalEvent: sim_time_ms, subtype, attack_stage, benign)
  - detections (DetectionProposal: threat_class, severity, evidence event_ids)
  - executed_actions (dict: action_id, detection_id, sim_time_ms)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

_SEV_RANK = {
    "info": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}


@dataclass
class ObjectiveResult:
    objective_id: str
    achieved: bool
    points: int
    detail: str = ""


@dataclass
class MissionScore:
    mission_id: str
    total_points: int
    max_score: int
    objectives: list[ObjectiveResult] = field(default_factory=list)
    final: bool = True

    @property
    def score(self) -> int:
        earned = sum(o.points for o in self.objectives if o.achieved)
        return min(earned, self.max_score)


def _events_by_id(events: list[Any]) -> dict[str, Any]:
    return {e.event_id: e for e in events}


def _detection_time(detection: Any, events_by_id: dict[str, Any]) -> int | None:
    """Approximate when a detection 'fired': earliest sim_time_ms among the
    events it cites (docs/14 §4 — deterministic, no wall-clock dependence)."""
    earliest: int | None = None
    for ev_item in getattr(detection, "evidence", []):
        for eid in getattr(ev_item, "event_ids", ()):
            ev = events_by_id.get(eid)
            if ev is not None:
                t = ev.sim_time_ms
                if earliest is None or t < earliest:
                    earliest = t
    return earliest


def _stop_event_time(events: list[Any], stop_subtype: str) -> int | None:
    for ev in events:
        if ev.subtype == stop_subtype:
            return int(ev.sim_time_ms)
    return None


def _collateral_pct(events: list[Any], actions: list[dict[str, Any]]) -> float:
    """Fraction of events affected by a response that were benign
    (over-broad containment, docs/14 §1 `minimal_collateral`)."""
    affected_benign = 0
    affected_total = 0
    for ev in events:
        payload = ev.payload or {}
        if payload.get("blocked") or payload.get("status") == 403:
            affected_total += 1
            if ev.benign:
                affected_benign += 1
    if affected_total == 0:
        return 0.0
    return affected_benign / affected_total


def _stages_covered_by_detections(detections: list[Any], events_by_id: dict[str, Any]) -> set[str]:
    covered: set[str] = set()
    for det in detections:
        for ev_item in getattr(det, "evidence", []):
            for eid in getattr(ev_item, "event_ids", ()):
                ev = events_by_id.get(eid)
                if ev is not None and ev.attack_stage is not None:
                    covered.add(ev.attack_stage.value)
    return covered


def evaluate_objective(
    objective: Any,
    *,
    events: list[Any],
    detections: list[Any],
    actions: list[dict[str, Any]],
) -> ObjectiveResult:
    """Evaluate one objective (docs/14 §4 kinds)."""
    events_by_id = _events_by_id(events)
    params = objective.params or {}
    kind = objective.kind

    if kind == "detection_within":
        tc = params.get("threat_class")
        min_sev = params.get("severity", "low")
        within_sec = int(params.get("within_sec", 90)) * 1000
        for det in detections:
            if det.threat_class.value != tc:
                continue
            if _SEV_RANK.get(det.severity.value, 0) < _SEV_RANK.get(min_sev, 0):
                continue
            t = _detection_time(det, events_by_id)
            if t is not None and t <= within_sec:
                return ObjectiveResult(
                    objective.id, True, objective.points, f"detected {tc} at {t}ms"
                )
            if t is not None:
                return ObjectiveResult(
                    objective.id, False, 0, f"detected {tc} but at {t}ms (> {within_sec}ms)"
                )
        return ObjectiveResult(objective.id, False, 0, f"no detection for {tc}")

    if kind == "detection_covers_stages":
        required = set(params.get("stages", []))
        covered = _stages_covered_by_detections(detections, events_by_id)
        achieved = required <= covered
        return ObjectiveResult(
            objective.id,
            achieved,
            objective.points,
            f"covered={sorted(covered)} required={sorted(required)}",
        )

    if kind == "action_executed_before_event":
        allowed = set(params.get("action_ids", []))
        stop_subtype = params.get("stop_event_subtype")
        stop_t = _stop_event_time(events, stop_subtype) if stop_subtype else None
        for action in actions:
            if action.get("action_id") not in allowed:
                continue
            action_t = action.get("sim_time_ms")
            if action_t is None:
                continue
            if stop_t is None or action_t < stop_t:
                return ObjectiveResult(
                    objective.id,
                    True,
                    objective.points,
                    f"action {action['action_id']} at {action_t}ms before stop-event@{stop_t}ms",
                )
        return ObjectiveResult(
            objective.id, False, 0, f"no allowed action before stop-event {stop_subtype}"
        )

    if kind == "benign_collateral_below":
        max_pct = float(params.get("max_pct", 10.0))
        pct = _collateral_pct(events, actions) * 100.0
        return ObjectiveResult(
            objective.id,
            pct <= max_pct,
            objective.points,
            f"collateral={pct:.1f}% (max {max_pct}%)",
        )

    if kind == "every_executed_action_backed_by_detection":
        unbacked = [a for a in actions if not a.get("detection_id")]
        return ObjectiveResult(
            objective.id, not unbacked, objective.points, f"unbacked={len(unbacked)}"
        )

    # Unknown objective kinds count as unachieved (schema drift guard).
    return ObjectiveResult(objective.id, False, 0, f"unknown kind {kind!r}")


def score_mission(
    mission: Any,
    *,
    events: list[Any],
    detections: list[Any],
    actions: list[dict[str, Any]],
) -> MissionScore:
    results = [
        evaluate_objective(obj, events=events, detections=detections, actions=actions)
        for obj in mission.objectives
    ]
    total = sum(o.points for o in results if o.achieved)
    return MissionScore(
        mission_id=mission.id,
        total_points=total,
        max_score=mission.scoring.max_score,
        objectives=results,
    )


__all__ = ["MissionScore", "ObjectiveResult", "evaluate_objective", "score_mission"]
