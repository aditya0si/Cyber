"""Pytest config: regression markers + skip rules (docs/20 §2)."""

from __future__ import annotations

import os

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "integration: requires Postgres + Redis up")
    config.addinivalue_line("markers", "slow: long-running; gated to nightly")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    skip_integration = pytest.mark.skip(reason="requires Postgres+Redis; run with -m integration")
    slow_filter_active = "slow" not in (config.option.markexpr or "")

    pg_url = os.environ.get("DATABASE_URL", "")
    redis_url = os.environ.get("REDIS_URL", "")
    infra_up = bool(pg_url and redis_url)

    for item in items:
        if "integration" in item.keywords and not infra_up:
            item.add_marker(skip_integration)
        if "slow" in item.keywords and slow_filter_active:
            item.add_marker(pytest.mark.skip(reason="slow tests gated to nightly"))
