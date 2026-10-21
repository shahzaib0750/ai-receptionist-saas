from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class VapiConfiguration(Base):
    __tablename__ = "vapi_configurations"
    __table_args__ = (
        UniqueConstraint("business_id", name="uq_vapi_configurations_business_id"),
        UniqueConstraint(
            "assistant_id",
            name="uq_vapi_configurations_assistant_id",
        ),
        Index(
            "ix_vapi_configurations_phone_number_id",
            "phone_number_id",
            unique=True,
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    business_id: Mapped[UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    assistant_id: Mapped[str] = mapped_column(String(255), nullable=False)
    phone_number_id: Mapped[str | None] = mapped_column(String(255))
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
