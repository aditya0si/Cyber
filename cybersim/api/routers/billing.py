"""Billing endpoints (docs/08 §4.9, docs/16 §6). Phase 10 wires Stripe."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from cybersim.api.deps import CurrentUser, get_current_user

router = APIRouter()

# Free-tier entitlement snapshot (docs/16 §1); Phase 10 replaces this with the
# `entitlements` table row synced from Stripe webhooks.
_FREE_ENTITLEMENTS: dict[str, Any] = {
    "max_concurrent_sims": 1,
    "ai_tier": "default",
    "sim_minutes_month": 60,
    "missions_month": 3,
    "retention_days": 7,
    "public_mission_links_per_day": 3,
}

_FREE_USAGE: dict[str, int] = {
    "sim_minutes": 0,
    "llm_tokens": 0,
    "llm_calls": 0,
    "missions_started": 0,
    "exports": 0,
}


@router.get("/billing/plan")
async def plan(
    _current: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, Any]:
    return {
        "plan": "free",
        "entitlements": _FREE_ENTITLEMENTS,
        "current_period_usage": dict(_FREE_USAGE),
    }


@router.post("/billing/checkout")
async def checkout(
    _current: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, Any]:
    from cybersim.infra.errors import AppError, ErrorCode

    raise AppError(ErrorCode.NOT_IMPLEMENTED, "Stripe checkout lands in Phase 10.")


@router.post("/billing/portal")
async def portal(
    _current: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, Any]:
    from cybersim.infra.errors import AppError, ErrorCode

    raise AppError(ErrorCode.NOT_IMPLEMENTED, "Stripe portal lands in Phase 10.")
