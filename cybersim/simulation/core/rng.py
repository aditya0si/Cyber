"""SeededRNG — deterministic randomness for simulations (docs/06 §1.1).

All simulators & the analyst normalizer draw randomness from one
`SeededRNG(seed=<int>)`, ensuring reproducibility (docs/00 §3 rule #4). The
lint guard infra/scripts/forbid_nondeterminism.py forbids `random.*`,
`time.time()`, `uuid.uuid4()` outside sanctioned files — this file is one of
the sanctioned homes.
"""

from __future__ import annotations

import random as _random  # sanctioned by the lint guard (infra/scripts/forbid_nondeterminism.py)
from typing import TypeVar

from cybersim.infra.uuidv7 import mint_v7

_T = TypeVar("_T")


class SeededRNG:
    """Deterministic RNG wrapping `random.Random`.

    Public methods mirror the most-used `random.*` callsites so simulators
    have no incentive to import `random` themselves. The seed is preserved
    so the same `(scenario, seed)` pair reproduces the event stream exactly.
    """

    __slots__ = ("_random", "seed")

    def __init__(self, seed: int) -> None:
        if not isinstance(seed, int):
            raise TypeError("seed must be int")
        self._random = _random.Random(seed)
        self.seed = seed

    def random(self) -> float:
        return self._random.random()

    def randint(self, lo: int, hi: int) -> int:
        if lo > hi:
            raise ValueError("lo must be <= hi")
        return self._random.randint(lo, hi)

    def choice(self, seq: list[_T] | tuple[_T, ...]) -> _T:
        if not seq:
            raise IndexError("cannot choose from empty sequence")
        return self._random.choice(seq)

    def choices(self, population: list[_T] | tuple[_T, ...], k: int = 1) -> list[_T]:
        if k < 0:
            raise ValueError("k must be >= 0")
        return self._random.choices(population, k=k)

    def sample(self, population: list[_T], k: int) -> list[_T]:
        if k < 0 or k > len(population):
            raise ValueError("k out of range for population")
        return self._random.sample(population, k)

    def bytes(self, n: int) -> bytes:
        if n < 0:
            raise ValueError("n must be >= 0")
        return self._random.randbytes(n)

    def bool(self, p: float = 0.5) -> bool:
        if not 0.0 <= p <= 1.0:
            raise ValueError("p must be in [0, 1]")
        return self._random.random() < p

    def getrandbits(self, k: int) -> int:
        return self._random.getrandbits(k)

    def uuid_v7(self, unix_ms: int) -> str:
        """Deterministic UUIDv7 for a sim-time ms (docs/00 §3)."""
        return mint_v7(unix_ms, self.bytes(10))

    def state(self) -> tuple[int | float, tuple[int, ...]] | None:
        """Read-only state introspection — used only by tests for determinism audit."""
        return self._random.getstate()
