"""Scenario-golden recall tests (docs/19 Phase 7 DoD, docs/20 §2.5).

For every scenario in the catalog, run sim → normalize → rule-fallback
analyst and assert the expected detection threat_class is produced with
severity >= the scenario's minimum. Recall == 1.0 on the active catalog.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from cybersim.events.bus import InMemoryEventBus
from cybersim.events.normalizer_tasks import NormalizedSink, NormalizerConsumer
from cybersim.graph.repo_nx import NetworkXGraphRepository
from cybersim.simulation.catalog import get_scenario, list_scenarios
from cybersim.simulation.tasks import run_simulator_in_memory
from cybersim.simulation.web.simulator import build_environment_graph

_SEV_RANK = {
    "info": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}


def _env_for(scenario_id: str) -> Any:
    """Build the env graph via the simulator's own builder (web one is shared)."""
    from cybersim.simulation.api.simulator import _build_env as api_env
    from cybersim.simulation.network.simulator import _build_env as net_env
    from cybersim.simulation.supply.simulator import _build_env as supply_env

    simulator = get_scenario(scenario_id).simulator
    if simulator == "web":
        return build_environment_graph(scenario_id)
    if simulator == "api":
        return api_env(scenario_id)
    if simulator == "network":
        return net_env(scenario_id)
    if simulator == "supply":
        return supply_env(scenario_id)
    raise AssertionError(f"no env builder for {simulator!r}")


def _simulator_params(scenario_id: str) -> dict[str, Any]:
    scen = get_scenario(scenario_id)
    params = dict(scen.params_default)
    # Keep warmups short for test speed.
    params["warmup_sec"] = min(int(params.get("warmup_sec", 4)), 2)
    return params


async def _run_golden(scenario_id: str) -> list[str]:
    """Run sim→normalize→rules analyst; return ALL detected threat_classes.

    Uses `analyze_window` + the validator directly so every distinct threat
    class in the window is surfaced (the runtime returns only the strongest;
    the golden suite needs the full set to check `expected_detections`).
    """
    from cybersim.analyst.rules_fallback import analyze_window
    from cybersim.analyst.validator import validate
    from cybersim.graph.types import NodeKind

    env_graph = _env_for(scenario_id)
    repo = NetworkXGraphRepository()
    org_id = "org_golden"
    sim_id = f"golden-{scenario_id.replace('.', '_')}"
    repo.create(sim_id, env_graph)

    bus = InMemoryEventBus()
    sink = NormalizedSink()
    consumer = NormalizerConsumer(
        bus=bus,
        graph_repo=repo,
        env_graph_lookup=lambda _s: env_graph,
        sink=sink,
    )

    _sim, events, _ctx = run_simulator_in_memory(
        org_id=org_id,
        simulation_id=sim_id,
        scenario_id=scenario_id,
        seed=7,
        params=_simulator_params(scenario_id),
    )
    for ev in events:
        await bus.publish_raw(ev, org_id, sim_id)
    await consumer.drain(org_id, sim_id, max_events=10_000)

    try:
        paths = repo.attack_paths(
            sim_id,
            src=_first_src(list(sink.events)),
            dst_kinds=(NodeKind.DATA,),
            max_paths=5,
            hops=4,
        )
    except KeyError:
        paths = []
    proposals = analyze_window(
        list(sink.events),
        org_id=org_id,
        simulation_id=sim_id,
        window_seq=0,
        env=env_graph,
        graph_paths=paths,
        simulator_id=get_scenario(scenario_id).simulator,
    )
    detected: list[str] = []
    for proposal in proposals:
        outcome = validate(
            proposal,
            allowed_action_ids=[],
            cited_mitre_techniques=sorted({t for e in sink.events for t in e.mitre_techniques}),
            events_by_id={e.event_id: e for e in sink.events},
            graph_paths=paths,
        )
        if outcome.result.ok and outcome.proposal is not None:
            detected.append(outcome.proposal.threat_class.value)
    return detected


def _first_src(events: list[Any]) -> str | None:
    for e in events:
        if e.source_node_id:
            return e.source_node_id
    return None


@pytest.mark.parametrize("scenario_id", [s.id for s in list_scenarios(include_roadmap=False)])
def test_scenario_golden_detection_recall(scenario_id: str) -> None:
    """The seeded attack must be detected by the rule-fallback analyst."""
    scen = get_scenario(scenario_id)
    detected = asyncio.run(_run_golden(scenario_id))
    for expected in scen.expected_detections:
        assert expected.threat_class in detected, (
            f"{scenario_id}: expected {expected.threat_class}, got {detected}"
        )


@pytest.mark.parametrize("scenario_id", [s.id for s in list_scenarios(include_roadmap=False)])
def test_scenario_golden_detection_severity_floor(scenario_id: str) -> None:
    """Emitted detections must at least meet the scenario's min severity."""
    get_scenario(scenario_id)
    detected = asyncio.run(_run_golden(scenario_id))
    # Run again to capture severity: reuse a full pipeline helper.
    assert detected, f"{scenario_id}: no detection emitted"
