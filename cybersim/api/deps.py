"""Shared FastAPI dependencies (docs/08 Â§2, docs/21 Task 4.1)."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from cybersim.infra.errors import AppError, ErrorCode
from cybersim.platform.auth.repo import (
    AuthRepository,
    OrgRecord,
    UserRecord,
    verify_user_password,
)

_bearer = HTTPBearer(auto_error=False)


class CurrentUser:
    """Resolved from the verified access token (docs/08 Â§2.2)."""

    def __init__(self, user: UserRecord, org: OrgRecord, role: str) -> None:
        self.user = user
        self.org = org
        self.role = role

    @property
    def user_id(self) -> str:
        return self.user.id

    @property
    def org_id(self) -> str:
        return self.org.id

    @property
    def email(self) -> str:
        return self.user.email


def get_auth_repo(request: Request) -> AuthRepository:
    repo = request.app.state.auth_repo
    return repo  # type: ignore[no-any-return]


def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> CurrentUser:
    if credentials is None:
        raise AppError(ErrorCode.AUTH_MISSING, "Bearer token required.")
    token = credentials.credentials
    try:
        claims = request.app.state.jwt_mint.decode_access_token(token)
    except Exception:
        raise AppError(ErrorCode.AUTH_INVALID, "Access token invalid or expired.") from None
    auth_repo = request.app.state.auth_repo
    user = auth_repo.get_user(claims["sub"])
    if user is None or user.status != "active":
        raise AppError(ErrorCode.AUTH_INVALID, "User not found or inactive.")
    org = auth_repo.get_org(claims["org_id"])
    if org is None:
        raise AppError(ErrorCode.AUTH_INVALID, "Org no longer exists.")
    role = claims.get("org_role", "member")
    return CurrentUser(user=user, org=org, role=role)


def login_user(
    auth_repo: AuthRepository, email: str, password: str
) -> tuple[UserRecord, OrgRecord, str]:
    """Validate credentials; return (user, org, role) or raise LOGIN_FAILED."""
    user = auth_repo.get_user_by_email(email)
    if user is None:
        raise AppError(ErrorCode.LOGIN_FAILED, "Invalid email or password.")
    if not verify_user_password(user, password):
        raise AppError(ErrorCode.LOGIN_FAILED, "Invalid email or password.")
    org_id = _first_membership_org(auth_repo, user)
    org = auth_repo.get_org(org_id)
    if org is None:
        raise AppError(ErrorCode.ORG_NOT_FOUND, "No org membership for user.")
    role = auth_repo.get_membership(org_id, user.id) or "member"
    return user, org, role


def _first_membership_org(auth_repo: AuthRepository, user: UserRecord) -> str:
    # MVP: single-org per user â€” pick the first membership we can find.
    for org in _all_orgs(auth_repo):
        if auth_repo.get_membership(org.id, user.id) is not None:
            return org.id
    raise AppError(ErrorCode.ORG_NOT_FOUND, "User has no org membership.")


def _all_orgs(auth_repo: AuthRepository) -> list[OrgRecord]:
    # In-memory repo: introspect via attribute (Phase 9: query DB).
    if hasattr(auth_repo, "_orgs") and isinstance(auth_repo._orgs, dict):
        return list(auth_repo._orgs.values())
    return []
