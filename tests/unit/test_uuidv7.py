"""Deterministic UUIDv7 (docs/00 Â§3, docs/21 Task 1.2)."""

from __future__ import annotations

import pytest

from cybersim.infra.uuidv7 import mint_v7, parse_v7, reconstruct_ms


def test_canonical_format_is_36_chars_lower_hex() -> None:
    s = mint_v7(1_723_000_000_000, b"\xaa\xbb\xcc" * 3 + b"\x01\x02")
    assert len(s) == 36
    parts = s.split("-")
    assert [len(p) for p in parts] == [8, 4, 4, 4, 12]
    assert s == s.lower()
    # version nibble is 7
    assert parts[2][0] == "7"
    # variant is 0b10xx
    assert parts[3][0] in {"8", "9", "a", "b"}


def test_mint_v7_rejects_underflow_randomness() -> None:
    with pytest.raises(ValueError, match="at least 10 random bytes"):
        mint_v7(0, b"\x00" * 9)


def test_mint_v7_rejects_overflow_ms() -> None:
    with pytest.raises(ValueError, match="48 bits"):
        mint_v7(1 << 48, b"\x00" * 10)


def test_mint_v7_is_deterministic_for_same_inputs() -> None:
    rnd = b"\x12\x34\x56\x78\x9a\xbc\xde\xf0\x11\x22"
    a = mint_v7(1234, rnd)
    b = mint_v7(1234, rnd)
    assert a == b


def test_round_trip_preserves_unix_ms_and_rand() -> None:
    rnd = b"\x77\x77\x77\x77\x77\x77\x77\x77\x77\x77"
    s = mint_v7(1_700_000_000_000, rnd)
    parsed = parse_v7(s)
    assert parsed.unix_ms == 1_700_000_000_000
    # the parsed rand_a + rand_b combine to give back the same bits modulo
    # what was filtered (only top 12 bits of first 2 bytes for rand_a, etc.)
    assert parsed.rand_a == 0x777 & 0x0FFF
    assert reconstruct_ms(s) == 1_700_000_000_000


@pytest.mark.parametrize("bad", ["", "xyz", "0123456789abcdef" * 8, "g" * 32])
def test_parse_rejects_malformed(bad: str) -> None:
    with pytest.raises(ValueError, match="not a canonical uuid"):
        parse_v7(bad)


def test_minted_ids_are_time_ordered() -> None:
    rnd = b"\x00" * 10
    ms_values = (1_000_000, 2_000_000, 1_999_999, 3_000_000)
    ids = [mint_v7(ms, rnd) for ms in ms_values]
    # Lexicographic sort yields ms-ordered output because ts is the prefix.
    sorted_lex = sorted(ids, key=lambda s: s.replace("-", ""))
    assert [reconstruct_ms(s) for s in sorted_lex] == sorted(ms_values)
