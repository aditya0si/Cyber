"""Deterministic UUIDv7 minting (docs/00 §3, docs/07 §1.2, docs/21 Task 1.2).

A UUIDv7 (RFC 9562) encodes:
    - 48 bits: unix epoch millis (big-endian) — time-ordered
    -  4 bits: version nibble (0x7)
    - 12 bits: random (`rand_a`)
    -  2 bits: variant (0b10)
    - 62 bits: random (`rand_b`)

Byte layout (16 bytes, big-endian):
    bytes 0..5   = unix_ts_ms (48 bits)
    bytes 6..7   = 0x7 (version) in high nibble of byte 6 + 12 bits of rand_a
    bytes 8      = 0b10 (variant) in high 2 bits + 6 high bits of rand_b
    bytes 9..15  = remaining 56 bits of rand_b

Cybersim mints deterministically from (clock ms + SeededRNG bytes) so
simulation event IDs are BOTH time-ordered AND reproducible per simulation.
Outside simulations, DB rows/audit/telemetry may freely use uuid4; the
determinism lint guard (infra/scripts/forbid_nondeterminism.py) excludes those
bookkeeping paths.
"""

from __future__ import annotations

from dataclasses import dataclass

UNIX_MS_48BIT_MAX = 1 << 48


def mint_v7(unix_ms: int, random_bytes: bytes) -> str:
    """Return the canonical lower-hex UUIDv7 string for given ms + >=10 bytes.

    Raises ValueError on out-of-range ms or insufficient randomness.
    """
    if len(random_bytes) < 10:
        raise ValueError("UUIDv7 needs at least 10 random bytes")
    if not 0 <= unix_ms < UNIX_MS_48BIT_MAX:
        raise ValueError("unix_ms must fit in 48 bits")
    rnd = random_bytes[:10]
    b = bytearray(16)
    b[0:6] = unix_ms.to_bytes(6, "big")
    rand_a = int.from_bytes(rnd[0:2], "big") & 0x0FFF
    b[6] = 0x70 | ((rand_a >> 8) & 0x0F)
    b[7] = rand_a & 0xFF
    rand_b_high = rnd[2] & 0x3F  # 6 high bits of rand_b
    b[8] = 0b10_000000 | rand_b_high  # variant 0b10 in MSB
    b[9:16] = rnd[3:10]
    h = b.hex()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


@dataclass(frozen=True)
class ParsedUUIDv7:
    unix_ms: int
    rand_a: int
    rand_b: int


def parse_v7(uuid_text: str) -> ParsedUUIDv7:
    """Inverse of mint_v7. Raises ValueError on malformed canonical input."""
    hex_only = uuid_text.replace("-", "").lower()
    if len(hex_only) != 32 or any(c not in "0123456789abcdef" for c in hex_only):
        raise ValueError(f"not a canonical uuid: {uuid_text!r}")
    b = bytes.fromhex(hex_only)
    unix_ms = int.from_bytes(b[0:6], "big")
    rand_a = ((b[6] & 0x0F) << 8) | b[7]
    rand_b_high = b[8] & 0x3F
    rand_b = (rand_b_high << 56) | int.from_bytes(b[9:16], "big")
    return ParsedUUIDv7(unix_ms=unix_ms, rand_a=rand_a, rand_b=rand_b)


def reconstruct_ms(uuid_text: str) -> int:
    """Return the unix_ms encoded in a UUIDv7 string."""
    return parse_v7(uuid_text).unix_ms
