from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

SUBSCRIPTION_STATUSES = (
    "trialing",
    "active",
    "past_due",
    "suspended",
    "cancelled",
    "incomplete",
)


class BillingPlan(Base):
    __tablename__ = "billing_plans"
    __table_args__ = (
        CheckConstraint("monthly_price >= 0", name="ck_billing_plans_price"),
        CheckConstraint("included_minutes >= 0", name="ck_billing_plans_minutes"),
        CheckConstraint("max_phone_numbers >= 1", name="ck_billing_plans_phone_numbers"),
        CheckConstraint(
            "length(currency) = 3 AND currency = upper(currency)",
            name="ck_billing_plans_currency",
        ),
        UniqueConstraint("name", name="uq_billing_plans_name"),
        Index("ix_billing_plans_active_name", "is_active", "name"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    monthly_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    provider_price_id: Mapped[str | None] = mapped_column(String(255))
    included_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    max_phone_numbers: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        nullable=False, default=True, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class BillingCustomer(Base):
    __tablename__ = "billing_customers"
    __table_args__ = (
        UniqueConstraint(
            "business_id", "provider", name="uq_billing_customers_business_provider"
        ),
        UniqueConstraint(
            "provider", "provider_customer_id", name="uq_billing_customers_provider_id"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    business_id: Mapped[UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="RESTRICT"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_customer_id: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class BillingSubscription(Base):
    __tablename__ = "billing_subscriptions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('trialing', 'active', 'past_due', 'suspended', "
            "'cancelled', 'incomplete')",
            name="ck_billing_subscriptions_status",
        ),
        CheckConstraint(
            "provider_status IN ('trialing', 'active', 'past_due', 'cancelled', 'incomplete')",
            name="ck_billing_subscriptions_provider_status",
        ),
        CheckConstraint(
            "current_period_end IS NULL OR current_period_start IS NULL "
            "OR current_period_end > current_period_start",
            name="ck_billing_subscriptions_period",
        ),
        UniqueConstraint(
            "id", "business_id", name="uq_billing_subscriptions_id_business"
        ),
        UniqueConstraint(
            "provider", "provider_subscription_id",
            name="uq_billing_subscriptions_provider_id",
        ),
        Index(
            "uq_billing_subscriptions_current_business",
            "business_id",
            unique=True,
            postgresql_where=text(
                "status IN ('trialing', 'active', 'past_due', 'suspended', 'incomplete')"
            ),
            sqlite_where=text(
                "status IN ('trialing', 'active', 'past_due', 'suspended', 'incomplete')"
            ),
        ),
        Index("ix_billing_subscriptions_status_period", "status", "current_period_end"),
        Index("ix_billing_subscriptions_business", "business_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    business_id: Mapped[UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="RESTRICT"), nullable=False
    )
    plan_id: Mapped[UUID] = mapped_column(
        ForeignKey("billing_plans.id", ondelete="RESTRICT"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_customer_id: Mapped[str | None] = mapped_column(String(255))
    provider_subscription_id: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="incomplete", server_default="incomplete"
    )
    provider_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="incomplete", server_default="incomplete"
    )
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trial_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_at_period_end: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default=text("false")
    )
    suspended_by_admin: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default=text("false")
    )
    last_provider_event_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class BillingSubscriptionPeriod(Base):
    __tablename__ = "billing_subscription_periods"
    __table_args__ = (
        CheckConstraint(
            "period_end > period_start", name="ck_billing_subscription_period_range"
        ),
        CheckConstraint(
            "monthly_price_snapshot >= 0",
            name="ck_billing_subscription_period_price",
        ),
        CheckConstraint(
            "included_minutes_snapshot >= 0",
            name="ck_billing_subscription_period_minutes",
        ),
        UniqueConstraint(
            "subscription_id",
            "period_start",
            "period_end",
            name="uq_billing_subscription_period_range",
        ),
        UniqueConstraint(
            "id", "business_id", name="uq_billing_subscription_period_id_business"
        ),
        ForeignKeyConstraint(
            ["subscription_id", "business_id"],
            ["billing_subscriptions.id", "billing_subscriptions.business_id"],
            name="fk_billing_subscription_period_business",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_billing_subscription_period_lookup",
            "subscription_id",
            "period_start",
            "period_end",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    business_id: Mapped[UUID] = mapped_column(nullable=False)
    subscription_id: Mapped[UUID] = mapped_column(nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    monthly_price_snapshot: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency_snapshot: Mapped[str] = mapped_column(String(3), nullable=False)
    included_minutes_snapshot: Mapped[int] = mapped_column(Integer, nullable=False)
    max_phone_numbers_snapshot: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class BillingMinuteGrant(Base):
    __tablename__ = "billing_minute_grants"
    __table_args__ = (
        CheckConstraint("minutes > 0", name="ck_billing_minute_grants_minutes"),
        ForeignKeyConstraint(
            ["subscription_id", "business_id"],
            ["billing_subscriptions.id", "billing_subscriptions.business_id"],
            name="fk_billing_minute_grants_subscription_business",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["billing_period_id", "business_id"],
            ["billing_subscription_periods.id", "billing_subscription_periods.business_id"],
            name="fk_billing_minute_grants_period_business",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["admin_user_id"], ["users.id"], name="fk_billing_minute_grants_admin"
        ),
        Index(
            "ix_billing_minute_grants_period",
            "billing_period_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    business_id: Mapped[UUID] = mapped_column(nullable=False)
    subscription_id: Mapped[UUID] = mapped_column(nullable=False)
    billing_period_id: Mapped[UUID] = mapped_column(nullable=False)
    admin_user_id: Mapped[UUID] = mapped_column(nullable=False)
    minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class BillingUsage(Base):
    __tablename__ = "billing_usage"
    __table_args__ = (
        ForeignKeyConstraint(
            ["call_id", "business_id"],
            ["vapi_calls.id", "vapi_calls.business_id"],
            name="fk_billing_usage_call_business",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["subscription_id", "business_id"],
            ["billing_subscriptions.id", "billing_subscriptions.business_id"],
            name="fk_billing_usage_subscription_business",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["billing_period_id", "business_id"],
            ["billing_subscription_periods.id", "billing_subscription_periods.business_id"],
            name="fk_billing_usage_period_business",
            ondelete="RESTRICT",
        ),
        CheckConstraint("billable_seconds > 0", name="ck_billing_usage_seconds"),
        CheckConstraint("quantity > 0", name="ck_billing_usage_quantity"),
        CheckConstraint(
            "billing_period_end > billing_period_start",
            name="ck_billing_usage_period",
        ),
        UniqueConstraint("call_id", "usage_type", name="uq_billing_usage_call_meter"),
        Index("ix_billing_usage_business_period", "business_id", "billing_period_start"),
        Index("ix_billing_usage_subscription_period", "subscription_id", "billing_period_start"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    business_id: Mapped[UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="RESTRICT"), nullable=False
    )
    subscription_id: Mapped[UUID | None] = mapped_column(nullable=True)
    billing_period_id: Mapped[UUID | None] = mapped_column(nullable=True)
    call_id: Mapped[UUID] = mapped_column(nullable=False)
    usage_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="call_seconds", server_default="call_seconds"
    )
    billable_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    billing_period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    billing_period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class BillingInvoice(Base):
    __tablename__ = "billing_invoices"
    __table_args__ = (
        UniqueConstraint(
            "provider", "provider_invoice_id", name="uq_billing_invoices_provider_id"
        ),
        CheckConstraint("amount >= 0", name="ck_billing_invoices_amount"),
        CheckConstraint(
            "status IN ('draft', 'open', 'paid', 'void', 'uncollectible')",
            name="ck_billing_invoices_status",
        ),
        Index("ix_billing_invoices_business_created", "business_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    business_id: Mapped[UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="RESTRICT"), nullable=False
    )
    subscription_id: Mapped[UUID] = mapped_column(
        ForeignKey("billing_subscriptions.id", ondelete="RESTRICT"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_invoice_id: Mapped[str | None] = mapped_column(String(255))
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    due_date: Mapped[date | None] = mapped_column(Date)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payment_reference: Mapped[str | None] = mapped_column(String(255))
    failure_details: Mapped[str | None] = mapped_column(String(500))
    hosted_invoice_url: Mapped[str | None] = mapped_column(String(2048))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class BillingPayment(Base):
    __tablename__ = "billing_payments"
    __table_args__ = (
        UniqueConstraint(
            "provider", "provider_payment_id", name="uq_billing_payments_provider_id"
        ),
        CheckConstraint("amount >= 0", name="ck_billing_payments_amount"),
        CheckConstraint(
            "status IN ('pending', 'succeeded', 'failed', 'refunded')",
            name="ck_billing_payments_status",
        ),
        Index("ix_billing_payments_business_created", "business_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    business_id: Mapped[UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="RESTRICT"), nullable=False
    )
    subscription_id: Mapped[UUID] = mapped_column(
        ForeignKey("billing_subscriptions.id", ondelete="RESTRICT"), nullable=False
    )
    invoice_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("billing_invoices.id", ondelete="RESTRICT")
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_payment_id: Mapped[str | None] = mapped_column(String(255))
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    payment_reference: Mapped[str | None] = mapped_column(String(255))
    failure_details: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class BillingProviderEvent(Base):
    __tablename__ = "billing_provider_events"
    __table_args__ = (
        UniqueConstraint("provider", "provider_event_id", name="uq_billing_provider_event"),
        CheckConstraint(
            "processing_status IN ('processed', 'ignored')",
            name="ck_billing_provider_events_status",
        ),
        Index("ix_billing_provider_events_created", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="processed"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class BillingAuditLog(Base):
    __tablename__ = "billing_audit_logs"
    __table_args__ = (
        Index("ix_billing_audit_logs_business_created", "business_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    admin_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    business_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("businesses.id", ondelete="RESTRICT")
    )
    subscription_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("billing_subscriptions.id", ondelete="RESTRICT")
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    details: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
