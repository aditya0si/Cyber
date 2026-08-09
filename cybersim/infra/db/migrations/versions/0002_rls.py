"""Row-Level Security baseline (docs/09 §10, docs/15 §3 — fail-closed).

Enables RLS on every tenant-scoped table, creates the org-isolation policy,
and asserts fail-closed semantics: an unset `app.current_org_id` returns
zero tenant-owned rows.

This migration is HIGH-RISK and must be reviewed with the `tenant-change` tag
(docs/09 §11). DO NOT use autogenerate; this is hand-written.

Revision ID: 0002_rls
Revises: 0001_baseline
Create Date: 2026-08-09 00:01:00
"""

from __future__ import annotations

from alembic import op

revision = "0002_rls"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


# Tables accessible bytenant-bearing JWTs (org_id resolves from JWT).
_TENANT_TABLES = (
    "orgs",
    "users",
    "org_members",
    "sessions",
    "invites",
    "simulations",
    "events",
    "graph_nodes",
    "graph_edges",
    "graph_overlay",
    "detections",
    "detection_evidence",
    "recommended_actions",
    "executed_actions",
    "mission_scores",
)


def upgrade() -> None:
    for tbl in _TENANT_TABLES:
        op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY")
        # Fail-closed: when `app.current_org_id` is unset, the function
        # `current_setting(..., true)` returns NULL (because `missing_ok=true`),
        # and NULL = NULL is FALSE, so the policy drops all rows.
        op.execute(
            f"""
            CREATE POLICY {tbl}_org_isolation ON {tbl}
            USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::text)
            """
        )

    # The `orgs` table itself uses `id` not `org_id`; add per-table policy.
    op.execute("DROP POLICY orgs_org_isolation ON orgs")
    op.execute(
        """
        CREATE POLICY orgs_org_isolation ON orgs
        USING (id = NULLIF(current_setting('app.current_org_id', true), '')::text)
        """
    )

    # `response_actions` is a global catalog (no RLS).
    # `missions` is partially global (org_id='global' on default rows); policy
    # matches global OR org.
    op.execute("ALTER TABLE missions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE missions FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY missions_visibility ON missions
        USING (
            org_id = 'global'
            OR org_id = NULLIF(current_setting('app.current_org_id', true), '')::text
        )
        """
    )


def downgrade() -> None:
    for tbl in _TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {tbl}_org_isolation ON {tbl}")
        op.execute(f"ALTER TABLE {tbl} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS missions_visibility ON missions")
    op.execute("ALTER TABLE missions NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE missions DISABLE ROW LEVEL SECURITY")
