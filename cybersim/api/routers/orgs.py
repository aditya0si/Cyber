"""Org endpoints (docs/08 §4.2)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from cybersim.api.deps import CurrentUser, get_current_user

router = APIRouter()


class OrgResponse(BaseModel):
    id: str
    name: str
    slug: str
    default_density: str


class MeResponse(BaseModel):
    user_id: str
    email: str
    org: OrgResponse
    role: str


@router.get("/me", response_model=MeResponse)
async def me(current: Annotated[CurrentUser, Depends(get_current_user)]) -> MeResponse:
    return MeResponse(
        user_id=current.user_id,
        email=current.email,
        org=OrgResponse(
            id=current.org.id,
            name=current.org.name,
            slug=current.org.slug,
            default_density=current.org.default_density,
        ),
        role=current.role,
    )


@router.get("/orgs/{org_id}", response_model=OrgResponse)
async def get_org(
    org_id: str,
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> OrgResponse:
    if org_id != current.org_id:
        from cybersim.infra.errors import AppError, ErrorCode

        raise AppError(ErrorCode.FORBIDDEN, "Cannot access another org.")
    return OrgResponse(
        id=current.org.id,
        name=current.org.name,
        slug=current.org.slug,
        default_density=current.org.default_density,
    )
