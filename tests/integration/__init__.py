"""Integration tests (docs/20 §2.2).

Tests marked `@pytest.mark.integration` REQUIRE a live Postgres (via
`docker compose up -d postgres`) and a Redis. Without them, pytest --mark
"not integration" skips them. Phase 3 PR-blocking runs skip them; the CI
image build job in `.github/workflows/ci.yml` runs them on merge groups or nightly.
"""
