"""Scenario + EnvironmentTemplate Pydantic models (docs/06 §2.1)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from cybersim.simulation.base import RawEvent  # noqa: F401  (re-export in catalog)

SIMULATORS = ("web", "api", "network", "supply")
CATEGORIES = (
    "web_application_attack",
    "api_abuse",
    "credential_attack",
    "network_intrusion",
    "supply_chain_compromise",
    "phishing_social_engineering",
    "cloud_misconfiguration",
)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DisplaySpec(_Strict):
    title: str = Field(min_length=1)
    blurb: str = ""
    category: str = Field(min_length=1)
    difficulty: str = Field(min_length=1)
    duration_sec: int = Field(gt=0)


class ExpectedDetection(_Strict):
    threat_class: str
    min_severity: str
    within_sec: int = Field(gt=0)


class AdversarySpec(_Strict):
    origin: dict[str, Any] = Field(default_factory=dict)
    skill: str = "intermediate"
    kill_chain: str | None = None
    intent: str | None = None


class ScoringSpec(_Strict):
    speed_weight: float = 0.3
    correctness_weight: float = 0.5
    containment_weight: float = 0.2


class ScenarioSpec(_Strict):
    """A loaded scenario definition (per docs/06 §2)."""

    id: str = Field(min_length=1)
    simulator: str
    display: DisplaySpec
    environment: str = Field(description="env template slug")
    adversary: AdversarySpec = Field(default_factory=AdversarySpec)
    params_default: dict[str, Any] = Field(default_factory=dict)
    dependencies: dict[str, Any] = Field(default_factory=dict)
    expected_detections: list[ExpectedDetection] = Field(default_factory=list)
    scoring: ScoringSpec = Field(default_factory=ScoringSpec)
    status: str = "active"

    @field_validator("simulator")
    @classmethod
    def _known_simulator(cls, v: str) -> str:
        if v not in SIMULATORS:
            raise ValueError(f"unknown simulator: {v!r}; expected one of {SIMULATORS}")
        return v

    @field_validator("display")
    @classmethod
    def _category_known(cls, display: DisplaySpec) -> DisplaySpec:
        if display.category not in CATEGORIES:
            raise ValueError(f"unknown category {display.category!r}; expected one of {CATEGORIES}")
        return display


class EnvAsset(_Strict):
    id: str
    type: str
    label: str = ""
    attrs: dict[str, Any] = Field(default_factory=dict)


class EnvService(_Strict):
    id: str
    asset: str
    kind: str = "http"
    endpoint: str = ""
    attrs: dict[str, Any] = Field(default_factory=dict)


class EnvEdge(_Strict):
    from_: str = Field(alias="from")
    type: str
    to: str
    attrs: dict[str, Any] = Field(default_factory=dict)


class EnvCredential(_Strict):
    id: str
    owner: str
    attrs: dict[str, Any] = Field(default_factory=dict)


class EnvData(_Strict):
    id: str
    store: str | None = None
    attrs: dict[str, Any] = Field(default_factory=dict)


class EnvironmentTemplate(_Strict):
    """A reusable environment template (docs/06 §2.1)."""

    id: str
    assets: list[EnvAsset] = Field(default_factory=list)
    services: list[EnvService] = Field(default_factory=list)
    edges: list[EnvEdge] = Field(default_factory=list)
    credentials: list[EnvCredential] = Field(default_factory=list)
    data: list[EnvData] = Field(default_factory=list)


def parse_scenario_yaml(path: Path, text: str) -> ScenarioSpec:
    """Parse a scenario YAML file; raises informative Schema errors on misuse."""
    import yaml

    raw = yaml.safe_load(text)
    if not isinstance(raw, dict):  # pragma: no cover — defensive
        raise ValueError(f"{path}: top-level YAML must be a mapping")
    return ScenarioSpec.model_validate(raw)


def parse_env_yaml(path: Path, text: str) -> EnvironmentTemplate:
    import yaml

    raw = yaml.safe_load(text)
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: top-level YAML must be a mapping")
    return EnvironmentTemplate.model_validate(raw)
