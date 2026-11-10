"""Add business onboarding and managed receptionist provisioning.

Revision ID: 0007_managed_onboarding
Revises: 0006_user_token_version
"""

import sqlalchemy as sa
from alembic import op

revision = "0007_managed_onboarding"
down_revision = "0006_user_token_version"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for column in (
        sa.Column("industry", sa.String(length=120), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("website", sa.String(length=2048), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("business_hours", sa.Text(), nullable=True),
        sa.Column("contact_phone", sa.String(length=64), nullable=True),
        sa.Column("contact_email", sa.String(length=320), nullable=True),
        sa.Column(
            "country_code",
            sa.String(length=2),
            server_default="US",
            nullable=False,
        ),
    ):
        op.add_column("businesses", column)

    op.add_column(
        "receptionist_configurations",
        sa.Column("requirements_text", sa.Text(), nullable=True),
    )
    op.add_column(
        "receptionist_configurations",
        sa.Column("fallback_instructions", sa.Text(), nullable=True),
    )
    op.add_column(
        "receptionist_configurations",
        sa.Column(
            "selected_services",
            sa.JSON(),
            server_default='["call_answering"]',
            nullable=False,
        ),
    )

    op.create_table(
        "receptionist_provisionings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="draft", nullable=False),
        sa.Column("assistant_id", sa.String(length=255), nullable=True),
        sa.Column("phone_number_id", sa.String(length=255), nullable=True),
        sa.Column("phone_number", sa.String(length=32), nullable=True),
        sa.Column("twilio_phone_sid", sa.String(length=64), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("safe_error_code", sa.String(length=64), nullable=True),
        sa.Column("consented_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("consented_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'setup_in_progress', 'ready', 'active', 'failed')",
            name="ck_receptionist_provisionings_status",
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_receptionist_provisionings_attempts"),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["consented_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("assistant_id", name="uq_receptionist_provisionings_assistant"),
        sa.UniqueConstraint("business_id", name="uq_receptionist_provisionings_business"),
        sa.UniqueConstraint("phone_number", name="uq_receptionist_provisionings_phone_number"),
        sa.UniqueConstraint("phone_number_id", name="uq_receptionist_provisionings_phone_id"),
        sa.UniqueConstraint("twilio_phone_sid", name="uq_receptionist_provisionings_twilio_sid"),
    )
    op.create_index(
        "ix_receptionist_provisionings_status",
        "receptionist_provisionings",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_receptionist_provisionings_status",
        table_name="receptionist_provisionings",
    )
    op.drop_table("receptionist_provisionings")
    op.drop_column("receptionist_configurations", "selected_services")
    op.drop_column("receptionist_configurations", "fallback_instructions")
    op.drop_column("receptionist_configurations", "requirements_text")
    for column in (
        "country_code",
        "contact_email",
        "contact_phone",
        "business_hours",
        "address",
        "website",
        "description",
        "industry",
    ):
        op.drop_column("businesses", column)
