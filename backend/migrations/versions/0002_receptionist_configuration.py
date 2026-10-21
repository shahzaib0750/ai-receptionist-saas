"""Add per-business receptionist configuration.

Revision ID: 0002_receptionist_configuration
Revises: 0001_initial
"""
import sqlalchemy as sa
from alembic import op

revision = "0002_receptionist_configuration"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "receptionist_configurations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("assistant_name", sa.String(length=120), nullable=False),
        sa.Column("greeting_message", sa.String(length=2000), nullable=False),
        sa.Column("business_timezone", sa.String(length=64), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "business_id",
            name="uq_receptionist_configurations_business_id",
        ),
    )


def downgrade() -> None:
    op.drop_table("receptionist_configurations")
