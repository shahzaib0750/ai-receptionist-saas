from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ReceptionistConfiguration(Base):
    __tablename__ = "receptionist_configurations"
    __table_args__ = (
        UniqueConstraint(
            "business_id",
            name="uq_receptionist_configurations_business_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    business_id: Mapped[UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    assistant_name: Mapped[str] = mapped_column(String(120), nullable=False)
    greeting_message: Mapped[str] = mapped_column(String(2000), nullable=False)
    business_timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    requirements_text: Mapped[str | None] = mapped_column(Text)
    fallback_instructions: Mapped[str | None] = mapped_column(Text)
    selected_services: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=lambda: ["call_answering"],
        server_default='["call_answering"]',
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
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
