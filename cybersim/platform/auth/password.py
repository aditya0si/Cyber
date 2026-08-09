"""Password hashing (argon2id) — docs/15 §2.1."""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=64 * 1024,  # 64 MiB
    parallelism=4,
    hash_len=32,
)


def hash_password(password: str) -> str:
    """Return an argon2id PHC string for `password`."""
    return _hasher.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    """Verify a password against its PHC hash; never raises on mismatch."""
    try:
        return _hasher.verify(encoded, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
