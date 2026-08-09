"""Async SQLAlchemy engine + session factory (docs/09 §1, docs/15 §3).

Per-request, the FastAPI `current_user` dependency issues
    SET app.current_org_id = '<jwt.org_id>'
on the connection immediately after acquire. RLS enforces fail-closed:
any request without that setting returns zero tenant-owned rows (docs/09 §10).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def build_engine(database_url: str, *, echo: bool = False) -> AsyncEngine:
    return create_async_engine(database_url, echo=echo, pool_pre_ping=True, future=True)


def build_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class AsyncSessionMaker:
    """Thin wrapper around `async_sessionmaker` so callers don't import SQLAlchemy directly."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._factory = build_sessionmaker(engine)

    @asynccontextmanager
    async def session_for(self, org_id: str) -> AsyncIterator[AsyncSession]:
        """Acquire a session pre-bound to the given org (RLS scope applied)."""
        async with self._factory() as session:
            await session.execute(text(_make_set_org_sql(org_id)))
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    @asynccontextmanager
    async def raw_session(self) -> AsyncIterator[AsyncSession]:
        """No-RLS session for migrations / patient system diagnostics (BYPASSRLS)."""
        async with self._factory() as session:
            yield session


def set_org_id(session: AsyncSession, org_id: str) -> Any:
    """Issue `SET app.current_org_id = '<org>'` on the live connection.

    Fail-closed semantics: NOT calling this on a tenant-scoped row leaves RLS
    with no scope var — policies return zero rows.
    """
    return session.execute(text(_make_set_org_sql(org_id)))


_ORG_ID_SAFE = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-./")


def _make_set_org_sql(org_id: str) -> str:
    """Build a safe literal `SET LOCAL app.current_org_id = '...'`.

    The org_id is constrained to allow-listed chars + internal `'` rejection.
    """
    if not org_id:
        raise ValueError("org_id must be non-empty")
    if "'" in org_id or "\\" in org_id:
        raise ValueError("org_id contains forbidden characters")
    bad = set(org_id) - _ORG_ID_SAFE
    if bad:
        raise ValueError(f"org_id contains forbidden characters: {bad!r}")
    return f"SET LOCAL app.current_org_id = '{org_id}'"


__all__ = ["AsyncSessionMaker", "build_engine", "set_org_id"]
