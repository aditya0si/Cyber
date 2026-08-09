"""Knowledge endpoints (docs/08 §4.7). Wired to KnowledgeRepository (Phase 6)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request

from cybersim.api.deps import CurrentUser, get_current_user
from cybersim.infra.errors import AppError, ErrorCode

router = APIRouter()


@router.get("/knowledge/search")
async def search(
    request: Request,
    _current: Annotated[CurrentUser, Depends(get_current_user)],
    q: str = "",
    k: int = 8,
) -> dict[str, Any]:
    repo = getattr(request.app.state, "knowledge_repo", None)
    if repo is None:
        return {"query": q, "hits": []}
    hits = repo.retrieve(query=q, k=k)
    return {
        "query": q,
        "hits": [
            {
                "entry_id": h.entry.entry_id,
                "source": h.entry.source,
                "source_id": h.entry.source_id,
                "title": h.entry.title,
                "summary": h.entry.summary,
                "score": round(h.score, 3),
            }
            for h in hits
        ],
    }


@router.get("/knowledge/entries/{entry_id}")
async def get_entry(
    entry_id: str,
    request: Request,
    _current: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, Any]:
    repo = getattr(request.app.state, "knowledge_repo", None)
    entry = repo.get_entry(entry_id) if repo is not None else None
    if entry is None:
        raise AppError(ErrorCode.KNOWLEDGE_NOT_FOUND, f"No knowledge entry {entry_id!r}.")
    return {
        "entry_id": entry.entry_id,
        "source": entry.source,
        "source_id": entry.source_id,
        "kind": entry.kind,
        "title": entry.title,
        "summary": entry.summary,
        "content": entry.content,
        "tags": list(entry.tags),
    }
