"""Determinism test: web.app.sqli_login reproduces the same event stream twice.

A test case MUST:
  - Run with the same (scenario, seed, params).
  - Produce identical event sequences modulo `received_at_ms` and
    UUID-derived bits in `event_id`. (received_at_ms is not set by simulators;
    event_id *IS* set deterministically from clock+rng, so it should be byte-
    equal too as long as the sim path is identical.)
  - Produce at least one event per expected category: http.request, db.error,
    auth.attempt, auth.success, db.query, session.created.
"""

from __future__ import annotations

import json

import pytest

from cybersim.simulation.base import RawEvent, ResponseCommand
from cybersim.simulation.tasks import run_simulator_in_memory


def _serialise_for_determinism(event: RawEvent) -> str:
    """A deterministic projection of an event (everything except RNG-derived edge ids)."""
    payload_norm = json.dumps(event.payload, sort_keys=True, default=str)
    return "|".join(
        [
            event.id,
            str(event.sim_time_ms),
            event.origin,
            event.type,
            event.node_ref or "",
            event.src_ip or "",
            "1" if event.benign else "0",
            payload_norm,
        ]
    )


def _run(seed: int = 7, duration_ms: int | None = None) -> list[RawEvent]:
    _sim, events, _ctx = run_simulator_in_memory(
        org_id="org_test",
        simulation_id="sim_test",
        scenario_id="web.app.sqli_login",
        seed=seed,
        params={"warmup_sec": 2, "request_rate_per_sec": 2},
        duration_ms=duration_ms,
    )
    return events


def test_web_sqli_produces_nonempty_event_stream() -> None:
    events = _run()
    assert len(events) > 30, f"expected many events, got {len(events)}"


def test_web_sqli_is_deterministic_across_runs_idempotent_id() -> None:
    a_list = _run(seed=11)
    b_list = _run(seed=11)
    assert len(a_list) == len(b_list)
    a_serial = [_serialise_for_determinism(e) for e in a_list]
    b_serial = [_serialise_for_determinism(e) for e in b_list]
    assert a_serial == b_serial


def test_web_sqli_different_seeds_yield_different_streams() -> None:
    a = _run(seed=11)
    b = _run(seed=99)
    a_serial = [_serialise_for_determinism(e) for e in a]
    b_serial = [_serialise_for_determinism(e) for e in b]
    assert a_serial != b_serial
    assert len(a) > 0
    assert len(b) > 0


@pytest.mark.parametrize(
    "raw_type",
    [
        "http.request",
        "db.error",
        "auth.attempt",
        "auth.success",
        "db.query",
        "session.created",
    ],
)
def test_web_sqli_emits_each_expected_event_type(raw_type: str) -> None:
    events = _run()
    types_present = {e.type for e in events}
    assert raw_type in types_present, (
        f"expected {raw_type!r} in stream, got only these: {sorted(types_present)}"
    )


def test_apply_command_block_source_ip_returns_response_event() -> None:
    from cybersim.simulation.tasks import build_context, get_simulator_class

    ctx = build_context(
        org_id="org_test",
        simulation_id="sim_test",
        scenario_id="web.app.sqli_login",
        seed=7,
        params={"warmup_sec": 0},
    )
    sim = get_simulator_class("web")()
    sim.init(ctx)
    out = sim.apply_command(
        ResponseCommand(action_id="block_source_ip", params={"ip": "203.0.113.42"}),
        ctx,
    )
    assert len(out) == 1
    assert out[0].origin == "exec"
    assert out[0].type == "response.applied"
    assert out[0].payload["action_id"] == "block_source_ip"
    assert out[0].payload["applied"] is True


def test_block_source_ip_subsequent_beats_respond_403() -> None:
    from cybersim.simulation.tasks import build_context, get_simulator_class

    ctx = build_context(
        org_id="org_test",
        simulation_id="sim_test",
        scenario_id="web.app.sqli_login",
        seed=42,
        params={"warmup_sec": 0},
    )
    sim = get_simulator_class("web")()
    sim.init(ctx)
    sim.apply_command(
        ResponseCommand(action_id="block_source_ip", params={"ip": "203.0.113.42"}),
        ctx,
    )
    # Pull a beat (warmup may be empty; burst beats emit 401 for attacker)
    any_blocked = False
    for beat in sim.beats(ctx):
        for ev in beat.events:
            if ev.src_ip == "203.0.113.42" and not ev.benign and ev.payload.get("status") == 403:
                any_blocked = True
                break
        if any_blocked:
            break
    assert any_blocked, "blocked IP should produce a 403 after block_source_ip"


def test_patch_sqli_subsequent_db_query_becomes_parameterized() -> None:
    from cybersim.simulation.tasks import build_context, get_simulator_class

    ctx = build_context(
        org_id="org_test",
        simulation_id="sim_test",
        scenario_id="web.app.sqli_login",
        seed=42,
        params={"warmup_sec": 0},
    )
    sim = get_simulator_class("web")()
    sim.init(ctx)
    sim.apply_command(ResponseCommand(action_id="patch_sqli", params={}), ctx)

    has_parameterized_after_patch = False
    for beat in sim.beats(ctx):
        for ev in beat.events:
            if ev.type == "db.query" and ev.payload.get("parameterized"):
                has_parameterized_after_patch = True
                break
        if has_parameterized_after_patch:
            break
    assert has_parameterized_after_patch, (
        "post-patch db.query events should be marked parameterized=True"
    )
