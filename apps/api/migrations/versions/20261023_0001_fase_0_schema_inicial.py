"""fase 0 schema inicial

Revision ID: 0001
Revises:
Create Date: 2026-10-23 18:27:32.180828
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "sites",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_sites_organization_id"), "sites", ["organization_id"], unique=False)
    op.create_table(
        "agents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("status IN ('active', 'revoked')", name="agent_status"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(op.f("ix_agents_organization_id"), "agents", ["organization_id"], unique=False)
    op.create_table(
        "cameras",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("source_ref", sa.String(length=128), nullable=False),
        sa.Column("analysis_fps", sa.Float(), nullable=False),
        sa.Column("min_confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("status_detail", sa.String(length=500), nullable=True),
        sa.Column("last_frame_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_id", "source_ref"),
    )
    op.create_index(op.f("ix_cameras_agent_id"), "cameras", ["agent_id"], unique=False)
    op.create_index(
        op.f("ix_cameras_organization_id"), "cameras", ["organization_id"], unique=False
    )
    op.create_table(
        "ingested_messages",
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("agent_session_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("message_id"),
    )
    op.create_index(
        op.f("ix_ingested_messages_received_at"), "ingested_messages", ["received_at"], unique=False
    )
    op.create_table(
        "zones",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("camera_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("polygon", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_zones_camera_id"), "zones", ["camera_id"], unique=False)
    op.create_index(op.f("ix_zones_organization_id"), "zones", ["organization_id"], unique=False)
    op.create_table(
        "event_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("camera_id", sa.Uuid(), nullable=False),
        sa.Column("zone_id", sa.Uuid(), nullable=False),
        sa.Column("rule_type", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("shadow", sa.Boolean(), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["zone_id"], ["zones.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_event_rules_camera_id"), "event_rules", ["camera_id"], unique=False)
    op.create_index(
        op.f("ix_event_rules_organization_id"), "event_rules", ["organization_id"], unique=False
    )
    op.create_table(
        "zone_metrics_1m",
        sa.Column("zone_id", sa.Uuid(), nullable=False),
        sa.Column("bucket_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("camera_id", sa.Uuid(), nullable=False),
        sa.Column("analyzed_seconds", sa.Float(), nullable=False),
        sa.Column("occupancy_avg", sa.Float(), nullable=False),
        sa.Column("occupancy_max", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["zone_id"], ["zones.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("zone_id", "bucket_start"),
    )
    op.create_index(
        "ix_zone_metrics_org_bucket",
        "zone_metrics_1m",
        ["organization_id", "bucket_start"],
        unique=False,
    )
    op.create_table(
        "occurrences",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=False),
        sa.Column("camera_id", sa.Uuid(), nullable=False),
        sa.Column("zone_id", sa.Uuid(), nullable=False),
        sa.Column("rule_id", sa.Uuid(), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("zone_version", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("is_shadow", sa.Boolean(), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("review_status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("close_reason", sa.String(length=20), nullable=True),
        sa.Column("max_people", sa.Integer(), nullable=False),
        sa.Column("max_confidence", sa.Float(), nullable=False),
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
        sa.CheckConstraint(
            "review_status IN ('new', 'acknowledged', 'resolved')", name="occurrence_review_status"
        ),
        sa.CheckConstraint("state IN ('open', 'closed')", name="occurrence_state"),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rule_id"], ["event_rules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["zone_id"], ["zones.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_occurrences_open",
        "occurrences",
        ["organization_id"],
        unique=False,
        postgresql_where=sa.text("state = 'open'"),
    )
    op.create_index(
        "ix_occurrences_org_camera_started",
        "occurrences",
        ["organization_id", "camera_id", sa.literal_column("started_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_occurrences_org_started",
        "occurrences",
        ["organization_id", sa.literal_column("started_at DESC")],
        unique=False,
    )
    op.create_table(
        "occurrence_updates",
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("occurrence_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["occurrence_id"], ["occurrences.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("message_id"),
    )
    op.create_index(
        op.f("ix_occurrence_updates_occurrence_id"),
        "occurrence_updates",
        ["occurrence_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_occurrence_updates_organization_id"),
        "occurrence_updates",
        ["organization_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_occurrence_updates_organization_id"), table_name="occurrence_updates")
    op.drop_index(op.f("ix_occurrence_updates_occurrence_id"), table_name="occurrence_updates")
    op.drop_table("occurrence_updates")
    op.drop_index("ix_occurrences_org_started", table_name="occurrences")
    op.drop_index("ix_occurrences_org_camera_started", table_name="occurrences")
    op.drop_index(
        "ix_occurrences_open", table_name="occurrences", postgresql_where=sa.text("state = 'open'")
    )
    op.drop_table("occurrences")
    op.drop_index("ix_zone_metrics_org_bucket", table_name="zone_metrics_1m")
    op.drop_table("zone_metrics_1m")
    op.drop_index(op.f("ix_event_rules_organization_id"), table_name="event_rules")
    op.drop_index(op.f("ix_event_rules_camera_id"), table_name="event_rules")
    op.drop_table("event_rules")
    op.drop_index(op.f("ix_zones_organization_id"), table_name="zones")
    op.drop_index(op.f("ix_zones_camera_id"), table_name="zones")
    op.drop_table("zones")
    op.drop_index(op.f("ix_ingested_messages_received_at"), table_name="ingested_messages")
    op.drop_table("ingested_messages")
    op.drop_index(op.f("ix_cameras_organization_id"), table_name="cameras")
    op.drop_index(op.f("ix_cameras_agent_id"), table_name="cameras")
    op.drop_table("cameras")
    op.drop_index(op.f("ix_agents_organization_id"), table_name="agents")
    op.drop_table("agents")
    op.drop_index(op.f("ix_sites_organization_id"), table_name="sites")
    op.drop_table("sites")
    op.drop_table("organizations")
