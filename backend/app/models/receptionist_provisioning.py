from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ReceptionistProvisioning(Base):
    __tablename__ = "receptionist_provisionings"
    __table_args__ = (
        UniqueConstraint("business_id", name="uq_receptionist_provisionings_business"),
        UniqueConstraint("assistant_id", name="uq_receptionist_provisionings_assistant"),
        UniqueConstraint("phone_number_id", name="uq_receptionist_provisionings_phone_id"),
        UniqueConstraint("phone_number", name="uq_receptionist_provisionings_phone_number"),
        UniqueConstraint("twilio_phone_sid", name="uq_receptionist_provisionings_twilio_sid"),
        CheckConstraint(
            "status IN ('draft', 'setup_in_progress', 'ready', 'active', 'failed')",
            name="ck_receptionist_provisionings_status",
        ),
        CheckConstraint("attempts >= 0", name="ck_receptionist_provisionings_attempts"),
        Index("ix_receptionist_provisionings_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    business_id: Mapped[UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="draft", server_default="draft"
    )
    assistant_id: Mapped[str | None] = mapped_column(String(255))
    phone_number_id: Mapped[str | None] = mapped_column(String(255))
    phone_number: Mapped[str | None] = mapped_column(String(32))
    twilio_phone_sid: Mapped[str | None] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    safe_error_code: Mapped[str | None] = mapped_column(String(64))
    consented_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    consented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
