"""RLS fail-closed isolation test (docs/09 §10, docs/15 §3).

@integration marker: skipped unless `DATABASE_URL` and `REDIS_URL` are set
(see tests/conftest.py).
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_orgs_rls_returns_no_rows_when_setting_unset() -> None:
    import os

    url = os.environ["DATABASE_URL"]
    engine = create_async_engine(url)
    async with engine.connect() as conn:
        # Without setting `app.current_org_id`, expect zero rows.
        rows = await conn.execute(text("SELECT COUNT(*) FROM orgs"))
        count = rows.scalar_one()
        assert count == 0, "RLS fail-closed violated: orgs readable without current_org_id"
    await engine.dispose()


@pytest.mark.asyncio
async def test_orgs_rls_returns_only_own_org_when_set() -> None:
    import os

    url = os.environ["DATABASE_URL"]
    engine = create_async_engine(url)
    sentinel_org = "org_test_only"
    async with engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO orgs (id, name, slug) VALUES (:i, :n, :s)"),
            {"i": sentinel_org, "n": "Test Org", "s": "test-org"},
        )
    try:
        async with engine.connect() as conn:
            await conn.execute(text(f"SET app.current_org_id = '{sentinel_org}'"))
            rows = await conn.execute(text("SELECT id FROM orgs"))
            ids = {r[0] for r in rows.fetchall()}
            assert ids == {sentinel_org}, f"RLS returned other-org rows: {ids}"
    finally:
        # Cleanup uses a SUPERUSER connection (BYPASSRLS) which the test role
        # doesn't have; the test infra destroys + recreates the scratch DB
        # between runs (CI), so we leave the row.
        pass
    await engine.dispose()
