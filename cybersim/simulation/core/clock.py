"""SimClock — deterministic sim-time clock (docs/06 §1.3, docs/07 §1.2).

Sim time advances in monotonic integer millis; ordering is guaranteed.
Independent of wall time so a sim can run at 0.1x/1x/10x speed without
affecting event content. Phase 1 keeps the API minimal.
"""

from __future__ import annotations


class SimClock:
    """Monotonic simulation clock in millis. NOT wall-clock-derived."""

    __slots__ = ("_ms", "duration_ms")

    def __init__(self, duration_ms: int = 0) -> None:
        if duration_ms < 0:
            raise ValueError("duration_ms must be >= 0")
        self._ms = 0
        self.duration_ms = duration_ms

    def now_ms(self) -> int:
        return self._ms

    def advance(self, delta_ms: int) -> int:
        if delta_ms < 0:
            raise ValueError("sim clock cannot go backwards")
        self._ms += delta_ms
        return self._ms

    def set_to(self, ms: int) -> None:
        """Snap to a forward-pointing timestamp (used by replay/scrub)."""
        if ms < self._ms:
            raise ValueError(f"set_to would rewind clock: now={self._ms}, asked={ms}")
        self._ms = ms

    def done(self) -> bool:
        return self.duration_ms > 0 and self._ms >= self.duration_ms

    def remaining_ms(self) -> int | None:
        if self.duration_ms <= 0:
            return None
        return max(0, self.duration_ms - self._ms)

    def __repr__(self) -> str:
        return f"SimClock(now_ms={self._ms}, duration_ms={self.duration_ms})"
