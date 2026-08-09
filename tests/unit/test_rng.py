"""SeededRNG determinism (docs/06 Â§1.1)."""

from __future__ import annotations

from cybersim.simulation.core.rng import SeededRNG


def test_same_seed_yields_same_randbytes() -> None:
    a = SeededRNG(42)
    b = SeededRNG(42)
    assert a.bytes(16) == b.bytes(16)
    assert a.bytes(64) == b.bytes(64)


def test_different_seed_yields_different_bytes() -> None:
    a = SeededRNG(1)
    b = SeededRNG(2)
    assert a.bytes(16) != b.bytes(16)


def test_randint_in_range_inclusive() -> None:
    rnd = SeededRNG(0)
    for _ in range(1_000):
        n = rnd.randint(5, 10)
        assert 5 <= n <= 10


def test_randint_rejects_lo_gt_hi() -> None:
    import pytest

    rnd = SeededRNG(0)
    with pytest.raises(ValueError, match="lo must be <= hi"):
        rnd.randint(10, 5)


def test_choice_and_sample_deterministic() -> None:
    a = SeededRNG(99)
    b = SeededRNG(99)
    pop = list(range(50))
    assert a.choice(pop) == b.choice(pop)
    assert a.sample(pop, 5) == b.sample(pop, 5)


def test_uuid_v7_is_deterministic_and_ordered() -> None:
    rnd_a = SeededRNG(7)
    rnd_b = SeededRNG(7)
    ms = 1_700_000_000_000
    u_a = rnd_a.uuid_v7(ms)
    u_b = rnd_b.uuid_v7(ms)
    assert u_a == u_b
    # advancing ms yields a larger string prefix
    later = SeededRNG(7).uuid_v7(ms + 5_000)
    assert later > u_a  # canonical prefix encodes ms
