"""cadastro de clientes (dados fiscais, contato, endereço), endereço dos locais e campos do contrato

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-23 20:13:59.227834
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHECKS = (
    ("organizations", "organization_person_type", "person_type IN ('pj', 'pf')"),
    ("organizations", "organization_status", "status IN ('active', 'inactive')"),
    ("contracts", "contract_billing_day", "billing_day IS NULL OR billing_day BETWEEN 1 AND 28"),
    ("contracts", "contract_term", "term_months IS NULL OR term_months > 0"),
    (
        "contracts",
        "contract_payment_method",
        "payment_method IS NULL OR payment_method IN ('boleto', 'pix', 'cartao', 'transferencia')",
    ),
    (
        "contracts",
        "contract_adjustment_index",
        "adjustment_index IS NULL OR adjustment_index IN ('ipca', 'igpm', 'none')",
    ),
)


def upgrade() -> None:
    op.add_column("contracts", sa.Column("signed_on", sa.Date(), nullable=True))
    op.add_column("contracts", sa.Column("term_months", sa.Integer(), nullable=True))
    op.add_column(
        "contracts",
        sa.Column("auto_renew", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column("contracts", sa.Column("billing_day", sa.Integer(), nullable=True))
    op.add_column("contracts", sa.Column("payment_method", sa.String(length=20), nullable=True))
    op.add_column("contracts", sa.Column("adjustment_index", sa.String(length=20), nullable=True))
    op.add_column("equipment", sa.Column("asset_tag", sa.String(length=50), nullable=True))
    op.add_column(
        "organizations",
        sa.Column("person_type", sa.String(length=2), server_default="pj", nullable=False),
    )
    op.add_column("organizations", sa.Column("document", sa.String(length=14), nullable=True))
    op.add_column("organizations", sa.Column("legal_name", sa.String(length=200), nullable=True))
    op.add_column(
        "organizations", sa.Column("state_registration", sa.String(length=30), nullable=True)
    )
    op.add_column("organizations", sa.Column("email", sa.String(length=320), nullable=True))
    op.add_column("organizations", sa.Column("phone", sa.String(length=20), nullable=True))
    op.add_column("organizations", sa.Column("contact_name", sa.String(length=200), nullable=True))
    op.add_column("organizations", sa.Column("contact_email", sa.String(length=320), nullable=True))
    op.add_column("organizations", sa.Column("contact_phone", sa.String(length=20), nullable=True))
    op.add_column("organizations", sa.Column("notes", sa.String(length=2000), nullable=True))
    op.add_column(
        "organizations", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("organizations", sa.Column("postal_code", sa.String(length=8), nullable=True))
    op.add_column("organizations", sa.Column("street", sa.String(length=200), nullable=True))
    op.add_column("organizations", sa.Column("street_number", sa.String(length=20), nullable=True))
    op.add_column("organizations", sa.Column("complement", sa.String(length=100), nullable=True))
    op.add_column("organizations", sa.Column("district", sa.String(length=100), nullable=True))
    op.add_column("organizations", sa.Column("city", sa.String(length=100), nullable=True))
    op.add_column("organizations", sa.Column("state", sa.String(length=2), nullable=True))
    op.create_unique_constraint("organizations_document_key", "organizations", ["document"])
    for table, name, condition in CHECKS:
        op.create_check_constraint(name, table, condition)
    op.add_column(
        "sites",
        sa.Column("vision_planned", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.add_column("sites", sa.Column("postal_code", sa.String(length=8), nullable=True))
    op.add_column("sites", sa.Column("street", sa.String(length=200), nullable=True))
    op.add_column("sites", sa.Column("street_number", sa.String(length=20), nullable=True))
    op.add_column("sites", sa.Column("complement", sa.String(length=100), nullable=True))
    op.add_column("sites", sa.Column("district", sa.String(length=100), nullable=True))
    op.add_column("sites", sa.Column("city", sa.String(length=100), nullable=True))
    op.add_column("sites", sa.Column("state", sa.String(length=2), nullable=True))


def downgrade() -> None:
    op.drop_column("sites", "state")
    op.drop_column("sites", "city")
    op.drop_column("sites", "district")
    op.drop_column("sites", "complement")
    op.drop_column("sites", "street_number")
    op.drop_column("sites", "street")
    op.drop_column("sites", "postal_code")
    # WARNING: constraint name is None; this directive will fail as
    # rendered.  Add a name, or use a naming convention; see
    # https://alembic.sqlalchemy.org/en/latest/naming.html
    op.drop_column("sites", "vision_planned")
    for table, name, _ in CHECKS:
        op.drop_constraint(name, table, type_="check")
    op.drop_constraint("organizations_document_key", "organizations", type_="unique")
    op.drop_column("organizations", "state")
    op.drop_column("organizations", "city")
    op.drop_column("organizations", "district")
    op.drop_column("organizations", "complement")
    op.drop_column("organizations", "street_number")
    op.drop_column("organizations", "street")
    op.drop_column("organizations", "postal_code")
    op.drop_column("organizations", "updated_at")
    op.drop_column("organizations", "notes")
    op.drop_column("organizations", "contact_phone")
    op.drop_column("organizations", "contact_email")
    op.drop_column("organizations", "contact_name")
    op.drop_column("organizations", "phone")
    op.drop_column("organizations", "email")
    op.drop_column("organizations", "state_registration")
    op.drop_column("organizations", "legal_name")
    op.drop_column("organizations", "document")
    op.drop_column("organizations", "person_type")
    op.drop_column("equipment", "asset_tag")
    op.drop_column("contracts", "adjustment_index")
    op.drop_column("contracts", "payment_method")
    op.drop_column("contracts", "billing_day")
    op.drop_column("contracts", "auto_renew")
    op.drop_column("contracts", "term_months")
    op.drop_column("contracts", "signed_on")
