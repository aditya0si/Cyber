"""Event-level enumerations (docs/05 §6.1, docs/07 §1)."""

from __future__ import annotations

from cybersim.events.types import AttackStage, EventCategory, Severity


def test_severity_rank_is_monotonic() -> None:
    assert Severity.rank(Severity.INFO) == 0
    assert Severity.rank(Severity.LOW) == 1
    assert Severity.rank(Severity.MEDIUM) == 2
    assert Severity.rank(Severity.HIGH) == 3
    assert Severity.rank(Severity.CRITICAL) == 4
    assert (
        Severity.rank(Severity.INFO)
        < Severity.rank(Severity.LOW)
        < Severity.rank(Severity.MEDIUM)
        < Severity.rank(Severity.HIGH)
        < Severity.rank(Severity.CRITICAL)
    )


def test_event_category_examples() -> None:
    assert EventCategory.AUTH.value == "auth"
    assert EventCategory.NETWORK.value == "network"


def test_attack_stage_benign_is_explicit() -> None:
    assert AttackStage.BENIGN.value == "benign"
