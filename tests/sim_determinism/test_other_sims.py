"""Determinism tests for API / Network / Supply simulators (docs/20 §2.4)."""

from __future__ import annotations

import json

import pytest

from cybersim.simulation.base import RawEvent
from cybersim.simulation.tasks import run_simulator_in_memory

_SIMS = [
    ("api.idor_orders", {"warmup_sec": 1, "request_rate_per_sec": 2}),
    ("api.brute_force", {}),
    ("net.recon_lateral", {}),
    ("supply.malicious_package", {}),
]


def _serialise(event: RawEvent) -> str:
    return "|".join(
        [
            event.id,
            str(event.sim_time_ms),
            event.origin,
            event.type,
            event.node_ref or "",
            event.src_ip or "",
            "1" if event.benign else "0",
            json.dumps(event.payload, sort_keys=True, default=str),
        ]
    )


def _run(scenario_id: str, params: dict, seed: int = 7) -> list[RawEvent]:
    _sim, events, _ctx = run_simulator_in_memory(
        org_id="org_test",
        simulation_id="sim_det",
        scenario_id=scenario_id,
        seed=seed,
        params=params,
    )
    return events


@pytest.mark.parametrize(("scenario_id", "params"), _SIMS)
def test_simulator_is_deterministic(scenario_id: str, params: dict) -> None:
    a = [_serialise(e) for e in _run(scenario_id, params, seed=11)]
    b = [_serialise(e) for e in _run(scenario_id, params, seed=11)]
    assert len(a) == len(b), f"{scenario_id}: event count differs"
    assert a == b, f"{scenario_id}: event stream differs across runs"


@pytest.mark.parametrize(("scenario_id", "params"), _SIMS)
def test_simulator_produces_events(scenario_id: str, params: dict) -> None:
    events = _run(scenario_id, params)
    assert len(events) > 0, f"{scenario_id}: no events produced"


@pytest.mark.parametrize(("scenario_id", "params"), _SIMS)
def test_simulator_emits_expected_raw_types(scenario_id: str, params: dict) -> None:
    events = _run(scenario_id, params)
    types = {e.type for e in events}
    expected = {
        "api.idor_orders": {"api.request", "api.data_response"},
        "api.brute_force": {"api.request"},
        "net.recon_lateral": {
            "net.scan_probe",
            "net.service_discovered",
            "host.login_attempt",
            "host.session",
            "host.process_spawn",
            "net.lateral_hop",
            "evidence.data_exfil",
        },
        "supply.malicious_package": {
            "build.dependency_resolve",
            "package.installed",
            "package.lifecycle.hook",
            "process.exec",
            "process.env_exfil",
            "net.connection",
        },
    }[scenario_id]
    assert expected <= types, f"{scenario_id}: missing types {expected - types}; got {types}"


def test_api_command_fix_idor_authz_blocks_subsequent() -> None:
    from cybersim.simulation.tasks import build_context, get_simulator_class

    ctx = build_context(
        org_id="org_test",
        simulation_id="sim_cmd",
        scenario_id="api.idor_orders",
        seed=7,
        params={"warmup_sec": 0},
    )
    sim = get_simulator_class("api")()
    sim.init(ctx)
    from cybersim.simulation.base import ResponseCommand

    sim.apply_command(ResponseCommand(action_id="fix_idor_authz", params={}), ctx)
    blocked = False
    for beat in sim.beats(ctx):
        for ev in beat.events:
            if (
                ev.type == "api.request"
                and ev.payload.get("status") == 403
                and ev.payload.get("authz_denied")
            ):
                blocked = True
                break
        if blocked:
            break
    assert blocked, "post-fix IDOR requests should return 403"
