"""Scenario catalog (docs/06 §2). Bundled YAML scenarios + env templates."""

from cybersim.simulation.catalog.index import (
    EnvironmentTemplate,
    ScenarioSpec,
    env_template,
    env_template_for_scenario,
    get_scenario,
    list_scenarios,
    load_catalog,
    scenario_params,
)

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
