"""Catalog loader + index (docs/06 §7, docs/21 Task 2.1).

`load_catalog()` walks `catalog/*.yaml`, classifying each file as either a
scenario (top-level keys: id/simulator/display/...) or an env template
(top-level keys: id/assets/services/...). The pattern `*.env.yaml` (or any
file where the only structured body is `assets: [...]`) is classified as an
env template; otherwise scenario. Both classes are bound to Pydantic models
so malformed files fail at startup, not at sim-run time.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from cybersim.simulation.catalog.loader import (
    EnvironmentTemplate,
    ScenarioSpec,
    parse_env_yaml,
    parse_scenario_yaml,
)

CATALOG_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=1)
def load_catalog() -> tuple[dict[str, ScenarioSpec], dict[str, EnvironmentTemplate]]:
    """Scan `cybersim/simulation/catalog/*.yaml`; return (scenarios, env_templates).

    Both maps are keyed by id. Raises if two entries share the same id.
    """
    scenarios: dict[str, ScenarioSpec] = {}
    env_templates: dict[str, EnvironmentTemplate] = {}

    for path in sorted(CATALOG_DIR.glob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        if path.name.endswith(".env.yaml"):
            env = parse_env_yaml(path, text)
            if env.id in env_templates:  # pragma: no cover — explicit guard
                raise ValueError(f"duplicate env template id={env.id!r}")
            env_templates[env.id] = env
            continue
        # heuristic: env templates contain `assets:` as their first list-shaped key
        first_line_keys = _top_keys(text)
        if first_line_keys and set(first_line_keys) <= {
            "id",
            "assets",
            "services",
            "edges",
            "credentials",
            "data",
        }:
            env = parse_env_yaml(path, text)
            if env.id in env_templates:  # pragma: no cover
                raise ValueError(f"duplicate env template id={env.id!r}")
            env_templates[env.id] = env
            continue
        scen = parse_scenario_yaml(path, text)
        if scen.id in scenarios:  # pragma: no cover
            raise ValueError(f"duplicate scenario id={scen.id!r}")
        scenarios[scen.id] = scen

    _cross_check(scenarios, env_templates)
    return scenarios, env_templates


def _top_keys(text: str) -> list[str]:
    import yaml

    raw = yaml.safe_load(text)
    if not isinstance(raw, dict):
        return []
    return list(raw.keys())


def _cross_check(
    scenarios: dict[str, ScenarioSpec],
    env_templates: dict[str, EnvironmentTemplate],
) -> None:
    """Ensure every scenario's `environment` slug resolves to a template."""
    for sid, scen in scenarios.items():
        if scen.environment not in env_templates:
            raise ValueError(
                f"scenario {sid!r} references unknown env template {scen.environment!r}"
            )


def list_scenarios(
    simulator: str | None = None,
    category: str | None = None,
    difficulty: str | None = None,
    include_roadmap: bool = False,
) -> list[ScenarioSpec]:
    """Return scenarios filtered by simulator/category/difficulty."""
    scenarios, _ = load_catalog()
    out: list[ScenarioSpec] = []
    for s in scenarios.values():
        if not include_roadmap and s.status == "roadmap":
            continue
        if simulator and s.simulator != simulator:
            continue
        if category and s.display.category != category:
            continue
        if difficulty and s.display.difficulty != difficulty:
            continue
        out.append(s)
    return sorted(out, key=lambda s: s.id)


def get_scenario(scenario_id: str) -> ScenarioSpec:
    scenarios, _ = load_catalog()
    if scenario_id not in scenarios:
        raise KeyError(f"unknown scenario_id={scenario_id!r}")
    return scenarios[scenario_id]


def env_template(env_slug: str) -> EnvironmentTemplate:
    _, env_templates = load_catalog()
    if env_slug not in env_templates:
        raise KeyError(f"unknown env template slug={env_slug!r}")
    return env_templates[env_slug]


def env_template_for_scenario(scenario_id: str) -> EnvironmentTemplate:
    return env_template(get_scenario(scenario_id).environment)


def scenario_params(scenario_id: str, override: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the scenario's default params merged with caller overrides."""
    base = dict(get_scenario(scenario_id).params_default)
    if override:
        base.update(override)
    return base


__all__ = [
    "EnvironmentTemplate",
    "ScenarioSpec",
    "env_template",
    "env_template_for_scenario",
    "get_scenario",
    "list_scenarios",
    "load_catalog",
    "scenario_params",
]
