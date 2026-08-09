"""Mission share tokens (docs/14 §5.1): unlisted, short, revocable."""

from __future__ import annotations

import secrets


def generate_share_token() -> str:
    """~80 bits of randomness, URL-safe (docs/14 §5.1)."""
    return secrets.token_urlsafe(10)


__all__ = ["generate_share_token"]
