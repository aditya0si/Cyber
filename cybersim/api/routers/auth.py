"""Auth endpoints (docs/08 §4.1)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from cybersim.api.deps import (
    CurrentUser,
    get_current_user,
    login_user,
)
from cybersim.infra.errors import AppError, ErrorCode
from cybersim.platform.auth.repo import (
    AuthRepository,
    generate_refresh_token,
    hash_refresh,
)

router = APIRouter()


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    org_name: str | None = None


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: str
    org_id: str
    org_role: str


def _issue_tokens(
    request: Request, auth_repo: AuthRepository, user_id: str, org_id: str, role: str
) -> TokenResponse:
    refresh_token = generate_refresh_token()
    session = auth_repo.create_session(user_id, org_id, refresh_token)
    access_token = request.app.state.jwt_mint.issue_access_token(
        user_id=user_id,
        org_id=org_id,
        org_role=role,
        scopes=["sim:run", "sim:read", "sim:respond"],
        session_id=session.id,
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=request.app.state.jwt_mint.access_ttl_sec,
        user_id=user_id,
        org_id=org_id,
        org_role=role,
    )


@router.post("/auth/register", response_model=TokenResponse)
async def register(payload: RegisterRequest, request: Request) -> TokenResponse:
    auth_repo: AuthRepository = request.app.state.auth_repo
    try:
        user = auth_repo.create_user(payload.email, payload.password, org_name=payload.org_name)
    except ValueError:
        raise AppError(ErrorCode.USER_EXISTS, "A user with this email already exists.") from None
    org_id = user.id[:8] and f"org_{user.id[:8]}"
    org = auth_repo.get_org(org_id)
    if org is None:
        raise AppError(ErrorCode.ORG_NOT_FOUND, "Org creation failed.")
    return _issue_tokens(request, auth_repo, user.id, org.id, "admin")


@router.post("/auth/login", response_model=TokenResponse)
async def login(payload: LoginRequest, request: Request) -> TokenResponse:
    auth_repo: AuthRepository = request.app.state.auth_repo
    user, org, role = login_user(auth_repo, payload.email, payload.password)
    auth_repo.record_login(user.id)
    return _issue_tokens(request, auth_repo, user.id, org.id, role)


class RefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str


@router.post("/auth/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, request: Request) -> TokenResponse:
    auth_repo: AuthRepository = request.app.state.auth_repo
    h = hash_refresh(payload.refresh_token)
    session = auth_repo.get_session_by_refresh_hash(h)
    if session is None:
        raise AppError(ErrorCode.AUTH_REFRESH_INVALID, "Refresh token not recognized.")
    if session.revoked_at is not None:
        raise AppError(ErrorCode.AUTH_REFRESH_INVALID, "Refresh token revoked.")
    user = auth_repo.get_user(session.user_id)
    org = auth_repo.get_org(session.org_id)
    if user is None or org is None:
        raise AppError(ErrorCode.AUTH_REFRESH_INVALID, "Session user/org missing.")
    role = auth_repo.get_membership(org.id, user.id) or "member"

    # Rotate: issue a NEW refresh token; old one becomes invalid.
    new_refresh = generate_refresh_token()
    auth_repo.rotate_session_refresh(session.id, new_refresh)
    access_token = request.app.state.jwt_mint.issue_access_token(
        user_id=user.id,
        org_id=org.id,
        org_role=role,
        scopes=["sim:run", "sim:read", "sim:respond"],
        session_id=session.id,
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh,
        expires_in=request.app.state.jwt_mint.access_ttl_sec,
        user_id=user.id,
        org_id=org.id,
        org_role=role,
    )


class LogoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str | None = None


@router.post("/auth/logout", status_code=204)
async def logout(
    payload: LogoutRequest,
    request: Request,
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> None:
    auth_repo: AuthRepository = request.app.state.auth_repo
    if payload.refresh_token:
        session = auth_repo.get_session_by_refresh_hash(hash_refresh(payload.refresh_token))
        if session is not None:
            auth_repo.revoke_session(session.id)


class WSTicketResponse(BaseModel):
    ticket: str
    expires_in: int = 60


@router.post("/auth/ws-ticket", response_model=WSTicketResponse)
async def ws_ticket(
    request: Request,
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> WSTicketResponse:
    session_id = _current_session_id(request)
    ticket = request.app.state.tickets.issue(session_id, current.org_id)
    return WSTicketResponse(ticket=ticket.token)


def _current_session_id(request: Request) -> str:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return "unknown"
    try:
        claims = request.app.state.jwt_mint.decode_access_token(auth_header.removeprefix("Bearer "))
        return str(claims.get("sid", "unknown"))
    except Exception:
        return "unknown"
