"""Migration up/down smoke (docs/20 §2.10)."""

from __future__ import annotations

import os
import subprocess

import pytest

pytestmark = pytest.mark.integration


def test_alembic_upgrade_then_downgrade_is_clean() -> None:
    """Apply all migrations, then downgrade to base, then upgrade again.

    A clean second upgrade means no migration introduced non-idempotent DDL.
    """
    pg_url = os.environ["DATABASE_URL"]
    env = {**os.environ, "DATABASE_URL": pg_url}
    cmds = [
        ["uv", "run", "alembic", "upgrade", "head"],
        ["uv", "run", "alembic", "downgrade", "base"],
        ["uv", "run", "alembic", "upgrade", "head"],
    ]
    for cmd in cmds:
        rc = subprocess.call(cmd, env=env)
        assert rc == 0, f"alembic command failed: {' '.join(cmd)}"
