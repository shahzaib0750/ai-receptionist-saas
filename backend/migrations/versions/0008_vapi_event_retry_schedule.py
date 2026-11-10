"""Persist retry eligibility for Vapi call-event recovery.

Revision ID: 0008_vapi_event_retry_schedule
Revises: 0007_managed_onboarding
"""

import sqlalchemy as sa
from alembic import op

revision = "0008_vapi_event_retry_schedule"
down_revision = "0007_managed_onboarding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "vapi_call_events",
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.drop_index(
        "ix_vapi_call_events_pending_received",
        table_name="vapi_call_events",
    )
    op.create_index(
        "ix_vapi_call_events_pending_retry",
        "vapi_call_events",
        ["processing_status", "next_attempt_at", "received_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_vapi_call_events_pending_retry",
        table_name="vapi_call_events",
    )
    op.create_index(
        "ix_vapi_call_events_pending_received",
        "vapi_call_events",
        ["processing_status", "received_at"],
    )
    op.drop_column("vapi_call_events", "next_attempt_at")
