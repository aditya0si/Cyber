"""SimClock ordering & bounds (docs/06 §1.3)."""

from __future__ import annotations

import pytest

from cybersim.simulation.core.clock import SimClock


def test_starts_at_zero_no_duration() -> None:
    c = SimClock()
    assert c.now_ms() == 0
    assert not c.done()
    assert c.remaining_ms() is None


def test_advance_is_monotonic() -> None:
    c = SimClock(duration_ms=1_000)
    c.advance(250)
    c.advance(250)
    assert c.now_ms() == 500
    assert not c.done()
    c.advance(499)
    assert not c.done()
    c.advance(1)
    assert c.done()
    assert c.remaining_ms() == 0


def test_advance_rejects_negative() -> None:
    c = SimClock()
    with pytest.raises(ValueError, match="cannot go backwards"):
        c.advance(-1)


def test_set_to_cannot_rewind() -> None:
    c = SimClock()
    c.advance(100)
    with pytest.raises(ValueError, match="would rewind"):
        c.set_to(50)


def test_set_to_forward_works() -> None:
    c = SimClock()
    c.advance(100)
    c.set_to(150)
    assert c.now_ms() == 150


def test_repr_includes_state() -> None:
    c = SimClock(duration_ms=10)
    assert "SimClock" in repr(c)
    assert "duration_ms=10" in repr(c)
