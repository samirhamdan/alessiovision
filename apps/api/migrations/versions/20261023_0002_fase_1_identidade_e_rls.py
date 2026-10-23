"""fase 1: identidade, sessões, auditoria, ativação de agentes e Row-Level Security

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-23 18:59:06.122831
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Lista congelada: as tabelas que existiam nesta migração. Tabelas novas ganham RLS
# nas próprias migrações.
TENANT_TABLES = (
    "sites",
    "agents",
    "cameras",
    "zones",
    "event_rules",
    "occurrences",
    "occurrence_updates",
    "zone_metrics_1m",
    "audit_logs",
)

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("invite_token_hash", sa.String(length=64), nullable=True),
        sa.Column("invite_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_login_count", sa.Integer(), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("status IN ('active', 'invited', 'disabled')", name="user_status"),
        sa.CheckConstraint("email = lower(email)", name="user_email_lowercase"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("invite_token_hash"),
    )
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=True),
        sa.Column("target_id", sa.String(length=64), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_audit_org_created",
        "audit_logs",
        ["organization_id", sa.literal_column("created_at DESC")],
        unique=False,
    )
    op.create_table(
        "memberships",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('owner', 'admin', 'operator', 'viewer')", name="membership_role"
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("organization_id", "user_id"),
    )
    op.create_index(op.f("ix_memberships_user_id"), "memberships", ["user_id"], unique=False)
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("active_organization_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["active_organization_id"], ["organizations.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        op.f("ix_user_sessions_expires_at"), "user_sessions", ["expires_at"], unique=False
    )
    op.create_index(op.f("ix_user_sessions_user_id"), "user_sessions", ["user_id"], unique=False)
    op.add_column("agents", sa.Column("enrollment_code_hash", sa.String(length=64), nullable=True))
    op.add_column(
        "agents", sa.Column("enrollment_expires_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("agents", sa.Column("hostname", sa.String(length=255), nullable=True))
    op.add_column("agents", sa.Column("enrolled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("agents", sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True))
    op.alter_column("agents", "token_hash", existing_type=sa.VARCHAR(length=64), nullable=True)
    op.add_column(
        "occurrences", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("occurrences", sa.Column("reviewed_by", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "occurrences_reviewed_by_fkey",
        "occurrences",
        "users",
        ["reviewed_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint(
        "agents_enrollment_code_hash_key", "agents", ["enrollment_code_hash"]
    )
    op.drop_constraint("agent_status", "agents", type_="check")
    op.create_check_constraint(
        "agent_status", "agents", "status IN ('pending', 'active', 'revoked')"
    )

    # Row-Level Security. FORCE faz a política valer também para o dono das tabelas,
    # que é o papel usado pela aplicação.
    op.execute(
        """
        CREATE FUNCTION app_current_org() RETURNS uuid
        LANGUAGE sql STABLE
        AS $$ SELECT NULLIF(current_setting('app.current_org', true), '')::uuid $$
        """
    )
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            "USING (organization_id = app_current_org()) "
            "WITH CHECK (organization_id = app_current_org())"
        )
    op.execute(
        """
        CREATE POLICY agent_lookup ON agents FOR SELECT
        USING (
            token_hash = NULLIF(current_setting('app.agent_lookup', true), '')
            OR enrollment_code_hash = NULLIF(current_setting('app.agent_lookup', true), '')
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY agent_lookup ON agents")
    for table in TENANT_TABLES:
        op.execute(f"DROP POLICY tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.execute("DROP FUNCTION app_current_org()")
    # Agentes nunca ativados não têm token e não cabem no esquema anterior.
    op.execute("DELETE FROM agents WHERE token_hash IS NULL")
    op.execute("UPDATE agents SET status = 'revoked' WHERE status = 'pending'")
    op.drop_constraint("agent_status", "agents", type_="check")
    op.create_check_constraint("agent_status", "agents", "status IN ('active', 'revoked')")
    op.drop_constraint("agents_enrollment_code_hash_key", "agents", type_="unique")
    op.drop_constraint("occurrences_reviewed_by_fkey", "occurrences", type_="foreignkey")
    op.drop_column("occurrences", "reviewed_by")
    op.drop_column("occurrences", "reviewed_at")
    op.alter_column("agents", "token_hash", existing_type=sa.VARCHAR(length=64), nullable=False)
    op.drop_column("agents", "revoked_at")
    op.drop_column("agents", "enrolled_at")
    op.drop_column("agents", "hostname")
    op.drop_column("agents", "enrollment_expires_at")
    op.drop_column("agents", "enrollment_code_hash")
    op.drop_index(op.f("ix_user_sessions_user_id"), table_name="user_sessions")
    op.drop_index(op.f("ix_user_sessions_expires_at"), table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_index(op.f("ix_memberships_user_id"), table_name="memberships")
    op.drop_table("memberships")
    op.drop_index("ix_audit_org_created", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_table("users")
