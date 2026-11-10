from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

VAPI_CALL_STATUSES = (
    "scheduled",
    "queued",
    "ringing",
    "in-progress",
    "forwarding",
    "ended",
)


class VapiCall(Base):
    __tablename__ = "vapi_calls"
    __table_args__ = (
        UniqueConstraint("vapi_call_id", name="uq_vapi_calls_vapi_call_id"),
        UniqueConstraint("id", "business_id", name="uq_vapi_calls_id_business"),
        CheckConstraint(
            "status IN ('scheduled', 'queued', 'ringing', 'in-progress', "
            "'forwarding', 'ended')",
            name="ck_vapi_calls_status",
        ),
        CheckConstraint(
            "direction IS NULL OR direction IN ('inbound', 'outbound')",
            name="ck_vapi_calls_direction",
        ),
        CheckConstraint(
            "duration_seconds IS NULL OR duration_seconds >= 0",
            name="ck_vapi_calls_duration",
        ),
        Index("ix_vapi_calls_business_created", "business_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    business_id: Mapped[UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    vapi_call_id: Mapped[str] = mapped_column(String(255), nullable=False)
    assistant_id: Mapped[str] = mapped_column(String(255), nullable=False)
    phone_number_id: Mapped[str | None] = mapped_column(String(255))
    direction: Mapped[str | None] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    caller_number: Mapped[str | None] = mapped_column(String(64))
    recipient_number: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int | None] = mapped_column()
    transcript: Mapped[str | None] = mapped_column(Text)
    recording_url: Mapped[str | None] = mapped_column(String(2048))
    ended_reason: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class VapiCallEvent(Base):
    """Inbox receipts deduplicate lifecycle events without provider event IDs.

    The business/call/type/status key covers status updates and one final report.
    """

    __tablename__ = "vapi_call_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('status-update', 'end-of-call-report')",
            name="ck_vapi_call_events_type",
        ),
        CheckConstraint(
            "event_status IN ('scheduled', 'queued', 'ringing', 'in-progress', "
            "'forwarding', 'ended')",
            name="ck_vapi_call_events_status",
        ),
        CheckConstraint(
            "direction IS NULL OR direction IN ('inbound', 'outbound')",
            name="ck_vapi_call_events_direction",
        ),
        CheckConstraint(
            "duration_seconds IS NULL OR duration_seconds >= 0",
            name="ck_vapi_call_events_duration",
        ),
        CheckConstraint(
            "processing_status IN ('pending', 'processed', 'failed')",
            name="ck_vapi_call_events_processing_status",
        ),
        CheckConstraint(
            "outcome IS NULL OR outcome IN ('applied', 'stale')",
            name="ck_vapi_call_events_outcome",
        ),
        UniqueConstraint(
            "business_id",
            "vapi_call_id",
            "event_type",
            "event_status",
            name="uq_vapi_call_events_lifecycle_stage",
        ),
        Index(
            "ix_vapi_call_events_pending_retry",
            "processing_status",
            "next_attempt_at",
            "received_at",
        ),
        Index("ix_vapi_call_events_vapi_call_id", "vapi_call_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    call_record_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("vapi_calls.id", ondelete="CASCADE"),
        nullable=True,
    )
    business_id: Mapped[UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    vapi_call_id: Mapped[str] = mapped_column(String(255), nullable=False)
    assistant_id: Mapped[str] = mapped_column(String(255), nullable=False)
    phone_number_id: Mapped[str | None] = mapped_column(String(255))
    event_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="status-update",
        server_default="status-update",
    )
    event_status: Mapped[str] = mapped_column(String(20), nullable=False)
    direction: Mapped[str | None] = mapped_column(String(8))
    provider_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    caller_number: Mapped[str | None] = mapped_column(String(64))
    recipient_number: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int | None] = mapped_column()
    transcript: Mapped[str | None] = mapped_column(Text)
    recording_url: Mapped[str | None] = mapped_column(String(2048))
    ended_reason: Mapped[str | None] = mapped_column(String(128))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    processing_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="pending",
        server_default="pending",
    )
    processing_attempt_count: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
        server_default="0",
    )
    outcome: Mapped[str | None] = mapped_column(String(16))
    safe_error_code: Mapped[str | None] = mapped_column(String(64))
