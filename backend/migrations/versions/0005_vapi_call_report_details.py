"""Persist Vapi end-of-call report details.

Revision ID: 0005_vapi_call_report_details
Revises: 0004_vapi_call_events
"""

import sqlalchemy as sa
from alembic import op

revision = "0005_vapi_call_report_details"
down_revision = "0004_vapi_call_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table_name in ("vapi_calls", "vapi_call_events"):
        op.add_column(
            table_name,
            sa.Column("caller_number", sa.String(length=64), nullable=True),
        )
        op.add_column(
            table_name,
            sa.Column("recipient_number", sa.String(length=64), nullable=True),
        )
        op.add_column(
            table_name,
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.add_column(
            table_name,
            sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.add_column(
            table_name,
            sa.Column("duration_seconds", sa.Integer(), nullable=True),
        )
        op.add_column(
            table_name,
            sa.Column("transcript", sa.Text(), nullable=True),
        )
        op.add_column(
            table_name,
            sa.Column("recording_url", sa.String(length=2048), nullable=True),
        )
        op.add_column(
            table_name,
            sa.Column("ended_reason", sa.String(length=128), nullable=True),
        )
        op.create_check_constraint(
            f"ck_{table_name}_duration",
            table_name,
            "duration_seconds IS NULL OR duration_seconds >= 0",
        )

    op.drop_constraint("ck_vapi_call_events_type", "vapi_call_events", type_="check")
    op.create_check_constraint(
        "ck_vapi_call_events_type",
        "vapi_call_events",
        "event_type IN ('status-update', 'end-of-call-report')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_vapi_call_events_type", "vapi_call_events", type_="check")
    op.create_check_constraint(
        "ck_vapi_call_events_type",
        "vapi_call_events",
        "event_type = 'status-update'",
    )
    for table_name in ("vapi_call_events", "vapi_calls"):
        op.drop_constraint(
            f"ck_{table_name}_duration",
            table_name,
            type_="check",
        )
        op.drop_column(table_name, "ended_reason")
        op.drop_column(table_name, "recording_url")
        op.drop_column(table_name, "transcript")
        op.drop_column(table_name, "duration_seconds")
        op.drop_column(table_name, "ended_at")
        op.drop_column(table_name, "started_at")
        op.drop_column(table_name, "recipient_number")
        op.drop_column(table_name, "caller_number")
