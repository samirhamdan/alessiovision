"""comodato e equipamentos: contratos, equipamentos por cliente e equipe Alessio

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-23 19:40:57.590951
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_TENANT_TABLES = ("comodato_contracts", "equipment")


def upgrade() -> None:
    op.create_table(
        "comodato_contracts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.String(length=64), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("notes", sa.String(length=2000), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("status IN ('active', 'ended')", name="contract_status"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "number"),
    )
    op.create_table(
        "equipment",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("brand", sa.String(length=100), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("serial_number", sa.String(length=100), nullable=True),
        sa.Column("ownership", sa.String(length=20), nullable=False),
        sa.Column("contract_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("camera_id", sa.Uuid(), nullable=True),
        sa.Column("agent_id", sa.Uuid(), nullable=True),
        sa.Column("reference_value_cents", sa.Integer(), nullable=True),
        sa.Column("monthly_fee_cents", sa.Integer(), nullable=True),
        sa.Column("delivered_on", sa.Date(), nullable=True),
        sa.Column("returned_on", sa.Date(), nullable=True),
        sa.Column("notes", sa.String(length=2000), nullable=True),
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
            "(ownership = 'comodato' AND contract_id IS NOT NULL) OR "
            "(ownership = 'client' AND contract_id IS NULL AND monthly_fee_cents IS NULL)",
            name="equipment_ownership_contract",
        ),
        sa.CheckConstraint(
            "kind IN ('camera', 'agent_host', 'recorder', 'switch', 'ups', 'other')",
            name="equipment_kind",
        ),
        sa.CheckConstraint("ownership IN ('client', 'comodato')", name="equipment_ownership"),
        sa.CheckConstraint(
            "status IN ('in_use', 'maintenance', 'returned', 'retired')", name="equipment_status"
        ),
        sa.CheckConstraint(
            "(reference_value_cents IS NULL OR reference_value_cents >= 0) AND "
            "(monthly_fee_cents IS NULL OR monthly_fee_cents >= 0)",
            name="equipment_values_positive",
        ),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["contract_id"], ["comodato_contracts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_equipment_contract_id"), "equipment", ["contract_id"], unique=False)
    op.create_index("ix_equipment_org_kind", "equipment", ["organization_id", "kind"], unique=False)
    op.add_column(
        "users",
        sa.Column(
            "is_platform_staff", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )

    for table in NEW_TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            "USING (organization_id = app_current_org()) "
            "WITH CHECK (organization_id = app_current_org())"
        )


def downgrade() -> None:
    for table in NEW_TENANT_TABLES:
        op.execute(f"DROP POLICY tenant_isolation ON {table}")
    op.drop_column("users", "is_platform_staff")
    op.drop_index("ix_equipment_org_kind", table_name="equipment")
    op.drop_index(op.f("ix_equipment_contract_id"), table_name="equipment")
    op.drop_table("equipment")
    op.drop_table("comodato_contracts")
