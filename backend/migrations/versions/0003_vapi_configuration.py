"""Add business-scoped Vapi configuration.

Revision ID: 0003_vapi_configuration
Revises: 0002_receptionist_configuration
"""
import sqlalchemy as sa
from alembic import op

revision = "0003_vapi_configuration"
down_revision = "0002_receptionist_configuration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vapi_configurations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("assistant_id", sa.String(length=255), nullable=False),
        sa.Column("phone_number_id", sa.String(length=255), nullable=True),
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "business_id",
            name="uq_vapi_configurations_business_id",
        ),
        sa.UniqueConstraint(
            "assistant_id",
            name="uq_vapi_configurations_assistant_id",
        ),
    )
    op.create_index(
        "ix_vapi_configurations_phone_number_id",
        "vapi_configurations",
        ["phone_number_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_vapi_configurations_phone_number_id",
        table_name="vapi_configurations",
    )
    op.drop_table("vapi_configurations")
