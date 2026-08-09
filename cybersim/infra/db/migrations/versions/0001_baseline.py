"""Initial schema baseline (docs/09 §1-§9, docs/21 Task 3.1).

Creates extensions, schemas, and every tenant-scoped table the platform owns
in Phase 3. Enum types use TEXT + CHECK constraints (portability — docs/09 §6
rationale). Migrations 0002 handles RLS baseline.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-08-09 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind()

    # ---- Extensions (per-cluster; ignored if already present) -----------------
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gin")
    # pgvector may already be installed per image; idempotent here.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ---- Schemas --------------------------------------------------------------
    op.execute("CREATE SCHEMA IF NOT EXISTS knowledge")
    op.execute("CREATE SCHEMA IF NOT EXISTS ops")

    # ---- orgs -----------------------------------------------------------------
    op.create_table(
        "orgs",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("slug", sa.String, nullable=False),
        sa.Column("default_density", sa.String, server_default="comfortable", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "default_density IN ('comfortable', 'compact', 'ultracompact')",
            name="ck_orgs_default_density",
        ),
    )
    op.create_unique_constraint("uq_orgs_slug", "orgs", ["slug"])

    # ---- users ----------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("email", sa.String, nullable=False),
        sa.Column("password_hash", sa.String, nullable=True),
        sa.Column("status", sa.String, server_default="active", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('active', 'disabled', 'invited')",
            name="ck_users_status",
        ),
    )
    op.create_unique_constraint("uq_users_email", "users", ["email"])

    # ---- org_members ----------------------------------------------------------
    op.create_table(
        "org_members",
        sa.Column("org_id", sa.String, sa.ForeignKey("orgs.id"), primary_key=True),
        sa.Column("user_id", sa.String, sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("role", sa.String, server_default="member", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('admin', 'member', 'analyst', 'viewer')",
            name="ck_org_members_role",
        ),
    )
    op.create_index("ix_org_members_user_id", "org_members", ["user_id"])

    # ---- sessions -------------------------------------------------------------
    op.create_table(
        "sessions",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("user_id", sa.String, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("org_id", sa.String, sa.ForeignKey("orgs.id"), nullable=False),
        sa.Column("refresh_token_hash", sa.String, nullable=False),
        sa.Column("user_agent", sa.String, nullable=True),
        sa.Column("ip", sa.String, nullable=True),
        sa.Column(
            "issued_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_refreshed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_unique_constraint("uq_sessions_refresh_hash", "sessions", ["refresh_token_hash"])
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])

    # ---- invites --------------------------------------------------------------
    op.create_table(
        "invites",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("org_id", sa.String, sa.ForeignKey("orgs.id"), nullable=False),
        sa.Column("email", sa.String, nullable=False),
        sa.Column("role", sa.String, server_default="member", nullable=False),
        sa.Column("invited_by", sa.String, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String, server_default="pending", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_invites_org_email", "invites", ["org_id", "email"])

    # ---- simulations ---------------------------------------------------------
    op.create_table(
        "simulations",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("org_id", sa.String, sa.ForeignKey("orgs.id"), nullable=False),
        sa.Column("scenario_id", sa.String, nullable=False),
        sa.Column("label", sa.String, nullable=True),
        sa.Column("seed", sa.BigInteger, nullable=False),
        sa.Column("params", sa.JSON, nullable=False),
        sa.Column("status", sa.String, server_default="queued", nullable=False),
        sa.Column("phase", sa.String, nullable=True),
        sa.Column("mission_id", sa.String, nullable=True),
        sa.Column("is_mission", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("public_share_token", sa.String, nullable=True),
        sa.Column("created_by", sa.String, sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_sec", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index("ix_simulations_org_created", "simulations", ["org_id", "created_at"])
    op.create_index("ix_simulations_status", "simulations", ["status"])
    op.create_index("ix_simulations_mission", "simulations", ["mission_id"])
    op.create_unique_constraint(
        "uq_simulations_public_share", "simulations", ["public_share_token"]
    )

    # ---- events (partitioned by received_at monthly) -------------------------
    # NOTE: PostgreSQL RANGE partitioning is created via raw SQL because
    # SQLAlchemy declarative doesn't express partitions cleanly.
    op.execute(
        """
        CREATE TABLE events (
            event_id          text PRIMARY KEY,
            simulation_id     text NOT NULL REFERENCES simulations(id) ON DELETE CASCADE,
            org_id            text NOT NULL,
            sequence          integer NOT NULL,
            sim_time_ms       bigint NOT NULL,
            received_at       timestamptz NOT NULL DEFAULT now(),
            origin            text NOT NULL,
            raw_type           text NOT NULL,
            category          text NOT NULL,
            subtype           text NOT NULL,
            severity_hint     text NOT NULL,
            attack_stage      text NULL,
            benign            boolean NOT NULL DEFAULT false,
            target_node_ids   text[] NOT NULL DEFAULT '{}',
            source_node_id    text NULL,
            via_edge_ids      text[] NOT NULL DEFAULT '{}',
            mitre_tactics     text[] NOT NULL DEFAULT '{}',
            mitre_techniques  text[] NOT NULL DEFAULT '{}',
            owasp_refs        text[] NOT NULL DEFAULT '{}',
            correlation_key   text NULL,
            payload           jsonb NOT NULL DEFAULT '{}'::jsonb,
            raw_ref           text NULL
        ) PARTITION BY RANGE (received_at)
        """
    )
    op.execute(
        """
        CREATE TABLE events_2026_08 PARTITION OF events
          FOR VALUES FROM ('2026-08-01') TO ('2026-09-01')
        """
    )
    op.execute(
        """
        CREATE TABLE events_2026_09 PARTITION OF events
          FOR VALUES FROM ('2026-09-01') TO ('2026-10-01')
        """
    )
    op.execute(
        """
        CREATE TABLE events_default PARTITION OF events DEFAULT
        """
    )
    op.create_index("ix_events_sim_seq", "events", ["simulation_id", "sequence"], unique=True)
    op.create_index("ix_events_sim_received", "events", ["simulation_id", "received_at"])
    op.execute("CREATE INDEX ix_events_target_node_ids ON events USING GIN (target_node_ids)")
    op.execute("CREATE INDEX ix_events_mitre_techniques ON events USING GIN (mitre_techniques)")
    op.execute("CREATE INDEX ix_events_payload ON events USING GIN (payload jsonb_path_ops)")

    # ---- graph_nodes / graph_edges / graph_overlay ---------------------------
    op.create_table(
        "graph_nodes",
        sa.Column(
            "simulation_id",
            sa.String,
            sa.ForeignKey("simulations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("node_id", sa.String, primary_key=True),
        sa.Column("kind", sa.String, nullable=False),
        sa.Column("type", sa.String, nullable=True),
        sa.Column("label", sa.String, nullable=False),
        sa.Column("foothold_state", sa.String, server_default="clean", nullable=False),
        sa.Column("attrs", sa.JSON, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("org_id", sa.String, nullable=False),
    )
    op.create_index("ix_graph_nodes_org", "graph_nodes", ["org_id"])

    op.create_table(
        "graph_edges",
        sa.Column(
            "simulation_id",
            sa.String,
            sa.ForeignKey("simulations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("edge_id", sa.String, primary_key=True),
        sa.Column("from_node", sa.String, nullable=False),
        sa.Column("to_node", sa.String, nullable=False),
        sa.Column("type", sa.String, nullable=False),
        sa.Column("attrs", sa.JSON, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("active", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.Column("org_id", sa.String, nullable=False),
    )
    op.create_index("ix_graph_edges_from", "graph_edges", ["simulation_id", "from_node"])
    op.create_index("ix_graph_edges_to", "graph_edges", ["simulation_id", "to_node"])

    op.create_table(
        "graph_overlay",
        sa.Column(
            "simulation_id",
            sa.String,
            sa.ForeignKey("simulations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("node_id", sa.String, primary_key=True),
        sa.Column("parent_node_id", sa.String, nullable=True),
        sa.Column("state", sa.String, nullable=False),
        sa.Column("flags", sa.JSON, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("org_id", sa.String, nullable=False),
    )

    # ---- detections + evidence + recommended_actions + executed_actions ------
    op.create_table(
        "detections",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column(
            "simulation_id",
            sa.String,
            sa.ForeignKey("simulations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("org_id", sa.String, nullable=False),
        sa.Column("threat_class", sa.String, nullable=False),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("severity", sa.String, nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False),
        sa.Column("confidence_band", sa.String, nullable=False),
        sa.Column("attack_path", sa.JSON, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("rationale", sa.String, nullable=False),
        sa.Column("source", sa.String, nullable=False),
        sa.Column("validated", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("status", sa.String, server_default="open", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_reason", sa.String, nullable=True),
    )
    op.create_index("ix_detections_sim_created", "detections", ["simulation_id", "created_at"])

    op.create_table(
        "detection_evidence",
        sa.Column(
            "detection_id",
            sa.String,
            sa.ForeignKey("detections.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("label", sa.String, primary_key=True),
        sa.Column("kind", sa.String, nullable=False),
        sa.Column("weight", sa.Numeric(5, 4), nullable=False),
        sa.Column("event_ids", sa.ARRAY(sa.String), nullable=False, server_default="{}"),
        sa.Column("graph_node_ids", sa.ARRAY(sa.String), nullable=False, server_default="{}"),
        sa.Column("citation_refs", sa.ARRAY(sa.String), nullable=False, server_default="{}"),
        sa.Column("extra", sa.JSON, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.execute(
        "CREATE INDEX ix_detection_evidence_event_ids ON detection_evidence USING GIN (event_ids)"
    )

    op.create_table(
        "recommended_actions",
        sa.Column(
            "detection_id",
            sa.String,
            sa.ForeignKey("detections.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("action_id", sa.String, nullable=False, primary_key=True),
        sa.Column("sort_order", sa.Integer, nullable=False),
        sa.Column("params", sa.JSON, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("rationale", sa.String, nullable=True),
        sa.Column("org_id", sa.String, nullable=False),
    )

    op.create_table(
        "response_actions",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("simulator", sa.String, nullable=False),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("description", sa.String, nullable=True),
        sa.Column("risk", sa.String, server_default="low", nullable=False),
        sa.Column("reversible", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.Column(
            "requires_confirmation", sa.Boolean, server_default=sa.text("false"), nullable=False
        ),
        sa.Column("schema_params", sa.JSON, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )

    op.create_table(
        "executed_actions",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("org_id", sa.String, nullable=False),
        sa.Column(
            "simulation_id",
            sa.String,
            sa.ForeignKey("simulations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "detection_id",
            sa.String,
            sa.ForeignKey("detections.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action_id", sa.String, nullable=False),
        sa.Column("params", sa.JSON, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("executed_by", sa.String, nullable=True),
        sa.Column(
            "executed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("result", sa.String, server_default="applied", nullable=False),
        sa.Column("audit_blob", sa.JSON, nullable=True),
    )
    op.create_index("ix_executed_actions_sim", "executed_actions", ["simulation_id", "executed_at"])

    # ---- mission tables -----------------------------------------------------
    op.create_table(
        "missions",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("org_id", sa.String, server_default="global", nullable=False),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("description", sa.String, nullable=True),
        sa.Column("simulator", sa.String, nullable=False),
        sa.Column("scenario_id", sa.String, nullable=False),
        sa.Column("objectives", sa.JSON, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("scoring_config", sa.JSON, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_public_default", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "mission_scores",
        sa.Column(
            "simulation_id",
            sa.String,
            sa.ForeignKey("simulations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("mission_id", sa.String, sa.ForeignKey("missions.id"), nullable=False),
        sa.Column("org_id", sa.String, nullable=False),
        sa.Column("score", sa.JSON, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("final", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("mission_scores")
    op.drop_table("missions")
    op.drop_table("executed_actions")
    op.drop_table("response_actions")
    op.drop_table("recommended_actions")
    op.execute("DROP INDEX IF EXISTS ix_detection_evidence_event_ids")
    op.drop_table("detection_evidence")
    op.drop_index("ix_detections_sim_created", table_name="detections")
    op.drop_table("detections")
    op.drop_table("graph_overlay")
    op.drop_index("ix_graph_edges_to", table_name="graph_edges")
    op.drop_index("ix_graph_edges_from", table_name="graph_edges")
    op.drop_table("graph_edges")
    op.drop_index("ix_graph_nodes_org", table_name="graph_nodes")
    op.drop_table("graph_nodes")
    op.execute("DROP INDEX IF EXISTS ix_events_payload")
    op.execute("DROP INDEX IF EXISTS ix_events_mitre_techniques")
    op.execute("DROP INDEX IF EXISTS ix_events_target_node_ids")
    op.drop_index("ix_events_sim_received", table_name="events")
    op.drop_index("ix_events_sim_seq", table_name="events")
    op.execute("DROP TABLE IF EXISTS events_2026_08")
    op.execute("DROP TABLE IF EXISTS events_2026_09")
    op.execute("DROP TABLE IF EXISTS events_default")
    op.execute("DROP TABLE IF EXISTS events")
    op.drop_index("ix_simulations_mission", table_name="simulations")
    op.drop_index("ix_simulations_status", table_name="simulations")
    op.drop_index("ix_simulations_org_created", table_name="simulations")
    op.drop_table("simulations")
    op.drop_index("ix_invites_org_email", table_name="invites")
    op.drop_table("invites")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")
    op.drop_index("ix_org_members_user_id", table_name="org_members")
    op.drop_table("org_members")
    op.drop_table("users")
    op.drop_table("orgs")
    op.execute("DROP SCHEMA IF EXISTS ops")
    op.execute("DROP SCHEMA IF EXISTS knowledge")
