"""Mission DSL loader (docs/14 §1)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

_MISSION_DIR = Path(__file__).resolve().parent / "catalog"


class ObjectiveSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    kind: str  # detection_within|detection_covers_stages|action_executed_before_event|...
    params: dict[str, Any] = Field(default_factory=dict)
    points: int = Field(ge=0)


class ScoringSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_score: int = 100


class SharingSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    public_default: bool = True


class MissionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    subtitle: str = ""
    simulator: str
    scenario_id: str
    duration_sec: int = Field(gt=0)
    objectives: list[ObjectiveSpec]
    scoring: ScoringSpec = Field(default_factory=ScoringSpec)
    sharing: SharingSpec = Field(default_factory=SharingSpec)
    status: str = "active"


def _load_mission(path: Path) -> MissionSpec:
    import yaml

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: mission YAML must be a mapping")
    return MissionSpec.model_validate(raw)


@lru_cache(maxsize=1)
def load_missions() -> dict[str, MissionSpec]:
    out: dict[str, MissionSpec] = {}
    for path in sorted(_MISSION_DIR.glob("*.yaml")):
        mission = _load_mission(path)
        if mission.id in out:
            raise ValueError(f"duplicate mission id {mission.id!r}")
        out[mission.id] = mission
    return out


def list_missions(include_roadmap: bool = False) -> list[MissionSpec]:
    return [m for m in load_missions().values() if include_roadmap or m.status == "active"]


def get_mission(mission_id: str) -> MissionSpec:
    missions = load_missions()
    if mission_id not in missions:
        raise KeyError(f"unknown mission_id={mission_id!r}")
    return missions[mission_id]


__all__ = ["MissionSpec", "ObjectiveSpec", "get_mission", "list_missions", "load_missions"]
