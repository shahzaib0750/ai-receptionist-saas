"""Add configurable subscription billing and usage ledger.

Revision ID: 0009_billing_foundation
Revises: 0008_vapi_event_retry_schedule
"""

import sqlalchemy as sa
from alembic import op

revision = "0009_billing_foundation"
down_revision = "0008_vapi_event_retry_schedule"
branch_labels = None
depends_on = None

_CURRENT_SUBSCRIPTION = (
    "status IN ('trialing', 'active', 'past_due', 'suspended', 'incomplete')"
)


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_vapi_calls_id_business",
        "vapi_calls",
        ["id", "business_id"],
    )
    op.create_table(
        "billing_plans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("monthly_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("provider_price_id", sa.String(length=255), nullable=True),
        sa.Column("included_minutes", sa.Integer(), nullable=False),
        sa.Column("max_phone_numbers", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("monthly_price >= 0", name="ck_billing_plans_price"),
        sa.CheckConstraint("included_minutes >= 0", name="ck_billing_plans_minutes"),
        sa.CheckConstraint("max_phone_numbers >= 1", name="ck_billing_plans_phone_numbers"),
        sa.CheckConstraint(
            "length(currency) = 3 AND currency = upper(currency)",
            name="ck_billing_plans_currency",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_billing_plans_name"),
    )
    op.create_index(
        "ix_billing_plans_active_name", "billing_plans", ["is_active", "name"]
    )

    op.create_table(
        "billing_customers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_customer_id", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "business_id", "provider", name="uq_billing_customers_business_provider"
        ),
        sa.UniqueConstraint(
            "provider", "provider_customer_id", name="uq_billing_customers_provider_id"
        ),
    )

    op.create_table(
        "billing_subscriptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_customer_id", sa.String(length=255), nullable=True),
        sa.Column("provider_subscription_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="incomplete", nullable=False),
        sa.Column("provider_status", sa.String(length=16), server_default="incomplete", nullable=False),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trial_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("suspended_by_admin", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("last_provider_event_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('trialing', 'active', 'past_due', 'suspended', 'cancelled', 'incomplete')",
            name="ck_billing_subscriptions_status",
        ),
        sa.CheckConstraint(
            "provider_status IN ('trialing', 'active', 'past_due', 'cancelled', 'incomplete')",
            name="ck_billing_subscriptions_provider_status",
        ),
        sa.CheckConstraint(
            "current_period_end IS NULL OR current_period_start IS NULL "
            "OR current_period_end > current_period_start",
            name="ck_billing_subscriptions_period",
        ),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["plan_id"], ["billing_plans.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "business_id", name="uq_billing_subscriptions_id_business"),
        sa.UniqueConstraint(
            "provider", "provider_subscription_id",
            name="uq_billing_subscriptions_provider_id",
        ),
    )
    op.create_index(
        "uq_billing_subscriptions_current_business",
        "billing_subscriptions",
        ["business_id"],
        unique=True,
        postgresql_where=sa.text(_CURRENT_SUBSCRIPTION),
        sqlite_where=sa.text(_CURRENT_SUBSCRIPTION),
    )
    op.create_index(
        "ix_billing_subscriptions_status_period",
        "billing_subscriptions",
        ["status", "current_period_end"],
    )
    op.create_index(
        "ix_billing_subscriptions_business",
        "billing_subscriptions",
        ["business_id", "created_at"],
    )

    op.create_table(
        "billing_subscription_periods",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("subscription_id", sa.Uuid(), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("monthly_price_snapshot", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency_snapshot", sa.String(length=3), nullable=False),
        sa.Column("included_minutes_snapshot", sa.Integer(), nullable=False),
        sa.Column("max_phone_numbers_snapshot", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("period_end > period_start", name="ck_billing_subscription_period_range"),
        sa.CheckConstraint(
            "monthly_price_snapshot >= 0",
            name="ck_billing_subscription_period_price",
        ),
        sa.CheckConstraint(
            "included_minutes_snapshot >= 0",
            name="ck_billing_subscription_period_minutes",
        ),
        sa.ForeignKeyConstraint(
            ["subscription_id", "business_id"],
            ["billing_subscriptions.id", "billing_subscriptions.business_id"],
            name="fk_billing_subscription_period_business",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "subscription_id", "period_start", "period_end",
            name="uq_billing_subscription_period_range",
        ),
        sa.UniqueConstraint(
            "id", "business_id",
            name="uq_billing_subscription_period_id_business",
        ),
    )
    op.create_index(
        "ix_billing_subscription_period_lookup",
        "billing_subscription_periods",
        ["subscription_id", "period_start", "period_end"],
    )

    op.create_table(
        "billing_minute_grants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("subscription_id", sa.Uuid(), nullable=False),
        sa.Column("billing_period_id", sa.Uuid(), nullable=False),
        sa.Column("admin_user_id", sa.Uuid(), nullable=False),
        sa.Column("minutes", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("minutes > 0", name="ck_billing_minute_grants_minutes"),
        sa.ForeignKeyConstraint(
            ["subscription_id", "business_id"],
            ["billing_subscriptions.id", "billing_subscriptions.business_id"],
            name="fk_billing_minute_grants_subscription_business",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["billing_period_id", "business_id"],
            ["billing_subscription_periods.id", "billing_subscription_periods.business_id"],
            name="fk_billing_minute_grants_period_business",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["admin_user_id"],
            ["users.id"],
            name="fk_billing_minute_grants_admin",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_billing_minute_grants_period",
        "billing_minute_grants",
        ["billing_period_id", "created_at"],
    )

    op.create_table(
        "billing_usage",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("subscription_id", sa.Uuid(), nullable=True),
        sa.Column("billing_period_id", sa.Uuid(), nullable=True),
        sa.Column("call_id", sa.Uuid(), nullable=False),
        sa.Column("usage_type", sa.String(length=32), server_default="call_seconds", nullable=False),
        sa.Column("billable_seconds", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("billing_period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("billing_period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("billable_seconds > 0", name="ck_billing_usage_seconds"),
        sa.CheckConstraint("quantity > 0", name="ck_billing_usage_quantity"),
        sa.CheckConstraint(
            "billing_period_end > billing_period_start",
            name="ck_billing_usage_period",
        ),
        sa.ForeignKeyConstraint(
            ["business_id"], ["businesses.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["call_id", "business_id"],
            ["vapi_calls.id", "vapi_calls.business_id"],
            name="fk_billing_usage_call_business",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["subscription_id", "business_id"],
            ["billing_subscriptions.id", "billing_subscriptions.business_id"],
            name="fk_billing_usage_subscription_business",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["billing_period_id", "business_id"],
            ["billing_subscription_periods.id", "billing_subscription_periods.business_id"],
            name="fk_billing_usage_period_business",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("call_id", "usage_type", name="uq_billing_usage_call_meter"),
    )
    op.create_index(
        "ix_billing_usage_business_period",
        "billing_usage",
        ["business_id", "billing_period_start"],
    )
    op.create_index(
        "ix_billing_usage_subscription_period",
        "billing_usage",
        ["subscription_id", "billing_period_start"],
    )

    op.create_table(
        "billing_invoices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("subscription_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_invoice_id", sa.String(length=255), nullable=True),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payment_reference", sa.String(length=255), nullable=True),
        sa.Column("failure_details", sa.String(length=500), nullable=True),
        sa.Column("hosted_invoice_url", sa.String(length=2048), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("amount >= 0", name="ck_billing_invoices_amount"),
        sa.CheckConstraint(
            "status IN ('draft', 'open', 'paid', 'void', 'uncollectible')",
            name="ck_billing_invoices_status",
        ),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["subscription_id"], ["billing_subscriptions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider", "provider_invoice_id", name="uq_billing_invoices_provider_id"
        ),
    )
    op.create_index(
        "ix_billing_invoices_business_created",
        "billing_invoices",
        ["business_id", "created_at"],
    )

    op.create_table(
        "billing_payments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("subscription_id", sa.Uuid(), nullable=False),
        sa.Column("invoice_id", sa.Uuid(), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_payment_id", sa.String(length=255), nullable=True),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("payment_reference", sa.String(length=255), nullable=True),
        sa.Column("failure_details", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("amount >= 0", name="ck_billing_payments_amount"),
        sa.CheckConstraint(
            "status IN ('pending', 'succeeded', 'failed', 'refunded')",
            name="ck_billing_payments_status",
        ),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["subscription_id"], ["billing_subscriptions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["invoice_id"], ["billing_invoices.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider", "provider_payment_id", name="uq_billing_payments_provider_id"
        ),
    )
    op.create_index(
        "ix_billing_payments_business_created",
        "billing_payments",
        ["business_id", "created_at"],
    )

    op.create_table(
        "billing_provider_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_event_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("provider_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "processing_status IN ('processed', 'ignored')",
            name="ck_billing_provider_events_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider", "provider_event_id", name="uq_billing_provider_event"
        ),
    )
    op.create_index(
        "ix_billing_provider_events_created",
        "billing_provider_events",
        ["created_at"],
    )

    op.create_table(
        "billing_audit_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("admin_user_id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=True),
        sa.Column("subscription_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("details", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["admin_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["subscription_id"], ["billing_subscriptions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_billing_audit_logs_business_created",
        "billing_audit_logs",
        ["business_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_billing_audit_logs_business_created", table_name="billing_audit_logs")
    op.drop_table("billing_audit_logs")
    op.drop_index("ix_billing_provider_events_created", table_name="billing_provider_events")
    op.drop_table("billing_provider_events")
    op.drop_index("ix_billing_payments_business_created", table_name="billing_payments")
    op.drop_table("billing_payments")
    op.drop_index("ix_billing_invoices_business_created", table_name="billing_invoices")
    op.drop_table("billing_invoices")
    op.drop_index("ix_billing_usage_subscription_period", table_name="billing_usage")
    op.drop_index("ix_billing_usage_business_period", table_name="billing_usage")
    op.drop_table("billing_usage")
    op.drop_index(
        "ix_billing_minute_grants_period",
        table_name="billing_minute_grants",
    )
    op.drop_table("billing_minute_grants")
    op.drop_index(
        "ix_billing_subscription_period_lookup",
        table_name="billing_subscription_periods",
    )
    op.drop_table("billing_subscription_periods")
    op.drop_index("ix_billing_subscriptions_business", table_name="billing_subscriptions")
    op.drop_index("ix_billing_subscriptions_status_period", table_name="billing_subscriptions")
    op.drop_index("uq_billing_subscriptions_current_business", table_name="billing_subscriptions")
    op.drop_table("billing_subscriptions")
    op.drop_index("ix_billing_plans_active_name", table_name="billing_plans")
    op.drop_table("billing_customers")
    op.drop_table("billing_plans")
    op.drop_constraint(
        "uq_vapi_calls_id_business", "vapi_calls", type_="unique"
    )
