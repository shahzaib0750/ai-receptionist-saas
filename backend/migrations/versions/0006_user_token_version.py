"""Support immediate access-token revocation after password changes.

Revision ID: 0006_user_token_version
Revises: 0005_vapi_call_report_details
"""

import sqlalchemy as sa
from alembic import op

revision = "0006_user_token_version"
down_revision = "0005_vapi_call_report_details"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("users", "token_version")
