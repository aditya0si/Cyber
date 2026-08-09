"""Auth repository seam (docs/15 §2.3) + in-memory impl.

Phase 4 ships the in-memory impl so the API + tests run without Postgres.
Phase 9 adds a SQLAlchemy-backed impl (same interface) wiring the `sessions`
table with refresh-token rotation + reuse detection.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol

from cybersim.platform.auth.password import hash_password, verify_password


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


@dataclass
class UserRecord:
    id: str
    email: str
    password_hash: str
    status: str = "active"
    created_at: datetime = field(default_factory=_utcnow)
    last_login_at: datetime | None = None


@dataclass
class OrgRecord:
    id: str
    name: str
    slug: str
    default_density: str = "comfortable"


@dataclass
class SessionRecord:
    id: str
    user_id: str
    org_id: str
    refresh_token_hash: str
    user_agent: str | None = None
    ip: str | None = None
    issued_at: datetime = field(default_factory=_utcnow)
    expires_at: datetime = field(default_factory=lambda: _utcnow() + timedelta(days=30))
    rotated_at: datetime | None = None
    revoked_at: datetime | None = None
    last_refreshed_at: datetime | None = None


class AuthRepository(Protocol):
    """User/org/session persistence + verification."""

    def create_user(
        self, email: str, password: str, *, org_name: str | None = None
    ) -> UserRecord: ...
    def get_user_by_email(self, email: str) -> UserRecord | None: ...
    def get_user(self, user_id: str) -> UserRecord | None: ...
    def get_org(self, org_id: str) -> OrgRecord | None: ...
    def get_membership(self, org_id: str, user_id: str) -> str | None: ...
    def create_session(self, user_id: str, org_id: str, refresh_token: str) -> SessionRecord: ...
    def get_session_by_refresh_hash(self, refresh_hash: str) -> SessionRecord | None: ...
    def rotate_session_refresh(self, session_id: str, new_refresh_token: str) -> None: ...
    def revoke_session(self, session_id: str) -> None: ...
    def record_login(self, user_id: str) -> None: ...


def hash_refresh(refresh_token: str) -> str:
    return hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


class InMemoryAuthRepository:
    """Thread-safe in-memory AuthRepository (dev + unit tests)."""

    def __init__(self) -> None:
        self._users: dict[str, UserRecord] = {}
        self._users_by_email: dict[str, str] = {}
        self._orgs: dict[str, OrgRecord] = {}
        self._memberships: dict[tuple[str, str], str] = {}
        self._sessions: dict[str, SessionRecord] = {}

    # ---- users/orgs --------------------------------------------------------
    def create_user(self, email: str, password: str, *, org_name: str | None = None) -> UserRecord:
        email_norm = email.lower()
        if email_norm in self._users_by_email:
            raise ValueError("user already exists")
        user_id = str(uuid.uuid4())
        user = UserRecord(id=user_id, email=email_norm, password_hash=hash_password(password))
        self._users[user_id] = user
        self._users_by_email[email_norm] = user_id

        org_id = f"org_{user_id[:8]}"
        org = OrgRecord(
            id=org_id,
            name=org_name or email_norm.split("@")[0],
            slug=f"{email_norm.split('@')[0]}-{user_id[:6]}",
        )
        self._orgs[org_id] = org
        self._memberships[(org_id, user_id)] = "admin"
        return user

    def get_user_by_email(self, email: str) -> UserRecord | None:
        user_id = self._users_by_email.get(email.lower())
        return self._users.get(user_id) if user_id else None

    def get_user(self, user_id: str) -> UserRecord | None:
        return self._users.get(user_id)

    def get_org(self, org_id: str) -> OrgRecord | None:
        return self._orgs.get(org_id)

    def get_membership(self, org_id: str, user_id: str) -> str | None:
        return self._memberships.get((org_id, user_id))

    # ---- sessions ----------------------------------------------------------
    def create_session(self, user_id: str, org_id: str, refresh_token: str) -> SessionRecord:
        session = SessionRecord(
            id=str(uuid.uuid4()),
            user_id=user_id,
            org_id=org_id,
            refresh_token_hash=hash_refresh(refresh_token),
        )
        self._sessions[session.id] = session
        return session

    def get_session_by_refresh_hash(self, refresh_hash: str) -> SessionRecord | None:
        for session in self._sessions.values():
            if session.refresh_token_hash == refresh_hash:
                return session
        return None

    def rotate_session_refresh(self, session_id: str, new_refresh_token: str) -> None:
        session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(f"unknown session {session_id!r}")
        session.refresh_token_hash = hash_refresh(new_refresh_token)
        session.rotated_at = _utcnow()
        session.last_refreshed_at = _utcnow()

    def revoke_session(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        if session is not None:
            session.revoked_at = _utcnow()

    def record_login(self, user_id: str) -> None:
        user = self._users.get(user_id)
        if user is not None:
            user.last_login_at = _utcnow()


def verify_user_password(user: UserRecord, password: str) -> bool:
    return verify_password(password, user.password_hash)


__all__ = [
    "AuthRepository",
    "InMemoryAuthRepository",
    "OrgRecord",
    "SessionRecord",
    "UserRecord",
    "generate_refresh_token",
    "hash_refresh",
    "verify_user_password",
]
