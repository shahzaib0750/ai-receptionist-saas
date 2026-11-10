from __future__ import annotations

import argparse
from collections.abc import Sequence
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal, engine
from app.models.billing import BillingPlan

INITIAL_PLANS = (
    {
        "name": "Starter",
        "description": "For businesses getting started with AI call answering.",
        "monthly_price": Decimal("29.00"),
        "currency": "USD",
        "included_minutes": 300,
        "max_phone_numbers": 1,
        "provider_price_id": None,
        "is_active": True,
    },
    {
        "name": "Growth",
        "description": "For businesses handling more customer calls.",
        "monthly_price": Decimal("79.00"),
        "currency": "USD",
        "included_minutes": 1000,
        "max_phone_numbers": 3,
        "provider_price_id": None,
        "is_active": True,
    },
    {
        "name": "Business",
        "description": "For businesses with higher call volumes.",
        "monthly_price": Decimal("149.00"),
        "currency": "USD",
        "included_minutes": 2500,
        "max_phone_numbers": 10,
        "provider_price_id": None,
        "is_active": True,
    },
)


def seed_missing_billing_plans(session: Session) -> list[str]:
    dialect_name = session.get_bind().dialect.name
    if dialect_name == "postgresql":
        insert_plan = postgresql_insert(BillingPlan)
    elif dialect_name == "sqlite":
        insert_plan = sqlite_insert(BillingPlan)
    else:
        raise RuntimeError(f"Unsupported database dialect for plan seeding: {dialect_name}")

    statement = insert_plan.values([{"id": uuid4(), **plan} for plan in INITIAL_PLANS])
    if dialect_name == "postgresql":
        statement = statement.on_conflict_do_nothing(
            constraint="uq_billing_plans_name"
        )
    else:
        statement = statement.on_conflict_do_nothing(
            index_elements=[BillingPlan.name]
        )
    inserted = session.scalars(statement.returning(BillingPlan.name)).all()
    return list(inserted)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Insert the initial billing plans without changing existing plans."
    )
    parser.add_argument(
        "--confirm-database",
        required=True,
        help="Must exactly match both configured DB_NAME and PostgreSQL current_database().",
    )
    args = parser.parse_args(argv)
    configured_database = get_settings().DB_NAME
    if args.confirm_database != configured_database:
        parser.error("--confirm-database must match the configured DB_NAME")

    with engine.connect() as connection:
        actual_database = connection.scalar(text("SELECT current_database()"))
    if actual_database != args.confirm_database:
        parser.error("Connected database does not match --confirm-database")

    with SessionLocal.begin() as session:
        inserted = seed_missing_billing_plans(session)

    print(f"Inserted {len(inserted)} plan(s); existing plans were left unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
