"""CanonicalEvent â€” frozen + extra-forbid + assembly helper (docs/07 Â§1)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from cybersim.events.schema import assemble
from cybersim.events.types import (
    AttackStage,
    EventCategory,
    Severity,
)


def _minimal_kwargs() -> dict:
    return dict(
        event_id="01J9a-event-id",
        simulation_id="01J9y-sim-id",
        org_id="org_demo",
        sequence=0,
        sim_time_ms=0,
        received_at_ms=1,
        origin="web",
        raw_type="http.request",
        category=EventCategory.HTTP,
        subtype="http_request",
        severity_hint=Severity.INFO,
    )


def test_canonical_event_is_immutable() -> None:
    ev = assemble(**_minimal_kwargs())
    with pytest.raises(ValidationError):
        ev.sequence = 99  # type: ignore[misc]


def test_canonical_event_rejects_extra_fields_via_assemble() -> None:
    from cybersim.events.schema import CanonicalEvent

    extras = _minimal_kwargs()
    extras["bogus"] = "nope"  # type: ignore[typeddict-unknown-key]
    with pytest.raises(ValidationError):
        CanonicalEvent(**extras)  # type: ignore[arg-type]


def test_canonical_event_defaults() -> None:
    ev = assemble(**_minimal_kwargs())
    assert ev.attack_stage is None
    assert ev.target_node_ids == ()
    assert ev.source_node_id is None
    assert ev.mitre_tactics == ()
    assert ev.mitre_techniques == ()
    assert ev.payload == {}
    assert ev.benign is False


def test_canonical_event_preserves_payload() -> None:
    kw = _minimal_kwargs()
    kw["payload"] = {"method": "POST", "path": "/api/login"}
    ev = assemble(**kw)
    assert ev.payload == {"method": "POST", "path": "/api/login"}


def test_canonical_event_severity_hint_validation() -> None:
    from cybersim.events.schema import CanonicalEvent

    base = _minimal_kwargs()
    base["severity_hint"] = Severity.HIGH
    ev = CanonicalEvent(**base)  # type: ignore[arg-type]
    assert ev.severity_hint == Severity.HIGH


def test_canonical_event_attack_stage_is_valid_enum() -> None:
    kw = _minimal_kwargs()
    kw["attack_stage"] = AttackStage.INITIAL_ACCESS
    ev = assemble(**kw)
    assert ev.attack_stage == AttackStage.INITIAL_ACCESS
