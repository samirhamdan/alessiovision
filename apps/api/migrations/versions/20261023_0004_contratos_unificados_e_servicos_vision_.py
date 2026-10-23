"""contratos unificados (comodato + serviços) e serviços Vision por câmera (regra R2)

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-23 19:57:26.590248
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RENAMED_CONSTRAINTS = (
    ("comodato_contracts_pkey", "contracts_pkey"),
    ("comodato_contracts_organization_id_fkey", "contracts_organization_id_fkey"),
    ("comodato_contracts_organization_id_number_key", "contracts_organization_id_number_key"),
)


def upgrade() -> None:
    # comodato_contracts vira contracts, preservando dados e vínculos com equipment.
    op.rename_table("comodato_contracts", "contracts")
    for old, new in RENAMED_CONSTRAINTS:
        op.execute(f"ALTER TABLE contracts RENAME CONSTRAINT {old} TO {new}")

    op.create_table(
        "camera_services",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("camera_id", sa.Uuid(), nullable=False),
        sa.Column("service", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("contract_id", sa.Uuid(), nullable=True),
        sa.Column("monthly_fee_cents", sa.Integer(), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(source = 'contract' AND contract_id IS NOT NULL) OR "
            "(source = 'trial' AND contract_id IS NULL AND monthly_fee_cents IS NULL "
            "AND ends_at IS NOT NULL)",
            name="camera_service_source_rules",
        ),
        sa.CheckConstraint("service IN ('security', 'operation')", name="camera_service_kind"),
        sa.CheckConstraint("source IN ('contract', 'trial')", name="camera_service_source"),
        sa.CheckConstraint("ends_at IS NULL OR ends_at > starts_at", name="camera_service_period"),
        sa.CheckConstraint(
            "monthly_fee_cents IS NULL OR monthly_fee_cents >= 0",
            name="camera_service_fee_positive",
        ),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_camera_services_contract_id"), "camera_services", ["contract_id"], unique=False
    )
    op.create_index(
        "ix_camera_services_org",
        "camera_services",
        ["organization_id", "camera_id", "service"],
        unique=False,
    )

    op.execute("ALTER TABLE camera_services ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE camera_services FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON camera_services "
        "USING (organization_id = app_current_org()) "
        "WITH CHECK (organization_id = app_current_org())"
    )


def downgrade() -> None:
    op.drop_table("camera_services")
    for old, new in RENAMED_CONSTRAINTS:
        op.execute(f"ALTER TABLE contracts RENAME CONSTRAINT {new} TO {old}")
    op.rename_table("contracts", "comodato_contracts")
