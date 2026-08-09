"""WS tickets (docs/08 §2.1): one-time 60s-bound connections.

The ticket encodes (session_id, expiry); the hub verifies it on connect and
resolves the owning org from the session.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class Ticket:
    token: str
    session_id: str
    org_id: str
    expires_at: float  # epoch seconds


class TicketStore:
    """In-memory one-time tickets. Phase 9 may move to Redis with TTL."""

    def __init__(self, ttl_sec: float = 60.0) -> None:
        self._ttl = ttl_sec
        self._tickets: dict[str, Ticket] = {}

    def issue(self, session_id: str, org_id: str) -> Ticket:
        token = secrets.token_urlsafe(32)
        ticket = Ticket(
            token=token,
            session_id=session_id,
            org_id=org_id,
            expires_at=time.time() + self._ttl,
        )
        self._tickets[token] = ticket
        return ticket

    def consume(self, token: str) -> Ticket | None:
        ticket = self._tickets.pop(token, None)
        if ticket is None:
            return None
        if ticket.expires_at < time.time():
            return None
        return ticket

    def revoke_all_for_session(self, session_id: str) -> None:
        for token, ticket in list(self._tickets.items()):
            if ticket.session_id == session_id:
                self._tickets.pop(token, None)
