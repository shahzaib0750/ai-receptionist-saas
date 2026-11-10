"""Add persistent Vapi calls and lifecycle events.

Revision ID: 0004_vapi_call_events
Revises: 0003_vapi_configuration
"""
import sqlalchemy as sa
from alembic import op

revision = "0004_vapi_call_events"
down_revision = "0003_vapi_configuration"
branch_labels = None
depends_on = None

CALL_STATUSES = "'scheduled', 'queued', 'ringing', 'in-progress', 'forwarding', 'ended'"


def upgrade() -> None:
    op.create_table(
        "vapi_calls",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("vapi_call_id", sa.String(length=255), nullable=False),
        sa.Column("assistant_id", sa.String(length=255), nullable=False),
        sa.Column("phone_number_id", sa.String(length=255), nullable=True),
        sa.Column("direction", sa.String(length=8), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
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
        sa.CheckConstraint(
            f"status IN ({CALL_STATUSES})",
            name="ck_vapi_calls_status",
        ),
        sa.CheckConstraint(
            "direction IS NULL OR direction IN ('inbound', 'outbound')",
            name="ck_vapi_calls_direction",
        ),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vapi_call_id", name="uq_vapi_calls_vapi_call_id"),
    )
    op.create_index(
        "ix_vapi_calls_business_created",
        "vapi_calls",
        ["business_id", "created_at"],
    )

    op.create_table(
        "vapi_call_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("call_record_id", sa.Uuid(), nullable=True),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("vapi_call_id", sa.String(length=255), nullable=False),
        sa.Column("assistant_id", sa.String(length=255), nullable=False),
        sa.Column("phone_number_id", sa.String(length=255), nullable=True),
        sa.Column("direction", sa.String(length=8), nullable=True),
        sa.Column(
            "event_type",
            sa.String(length=32),
            server_default="status-update",
            nullable=False,
        ),
        sa.Column("event_status", sa.String(length=20), nullable=False),
        sa.Column("provider_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "processing_status",
            sa.String(length=16),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "processing_attempt_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("outcome", sa.String(length=16), nullable=True),
        sa.Column("safe_error_code", sa.String(length=64), nullable=True),
        sa.CheckConstraint(
            "event_type = 'status-update'",
            name="ck_vapi_call_events_type",
        ),
        sa.CheckConstraint(
            f"event_status IN ({CALL_STATUSES})",
            name="ck_vapi_call_events_status",
        ),
        sa.CheckConstraint(
            "direction IS NULL OR direction IN ('inbound', 'outbound')",
            name="ck_vapi_call_events_direction",
        ),
        sa.CheckConstraint(
            "processing_status IN ('pending', 'processed', 'failed')",
            name="ck_vapi_call_events_processing_status",
        ),
        sa.CheckConstraint(
            "outcome IS NULL OR outcome IN ('applied', 'stale')",
            name="ck_vapi_call_events_outcome",
        ),
        sa.ForeignKeyConstraint(
            ["call_record_id"],
            ["vapi_calls.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "business_id",
            "vapi_call_id",
            "event_type",
            "event_status",
            name="uq_vapi_call_events_lifecycle_stage",
        ),
    )
    op.create_index(
        "ix_vapi_call_events_pending_received",
        "vapi_call_events",
        ["processing_status", "received_at"],
    )
    op.create_index(
        "ix_vapi_call_events_vapi_call_id",
        "vapi_call_events",
        ["vapi_call_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_vapi_call_events_vapi_call_id", table_name="vapi_call_events")
    op.drop_index("ix_vapi_call_events_pending_received", table_name="vapi_call_events")
    op.drop_table("vapi_call_events")
    op.drop_index("ix_vapi_calls_business_created", table_name="vapi_calls")
    op.drop_table("vapi_calls")
