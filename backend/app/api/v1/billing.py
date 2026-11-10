import json
import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_current_user,
    require_business_permission,
    require_platform_billing_admin,
)
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.integrations.payments.base import (
    PaymentProviderError,
    PaymentProviderNotConfigured,
    get_payment_provider,
)
from app.models.billing import (
    BillingCustomer,
    BillingInvoice,
    BillingPayment,
    BillingPlan,
    BillingSubscription,
    BillingUsage,
)
from app.models.business import Business
from app.models.user import User
from app.schemas.billing import (
    BillingInvoiceRead,
    BillingPaymentRead,
    BillingPlanCreate,
    BillingPlanRead,
    BillingPlanUpdate,
    BillingProviderEventPayload,
    BillingSubscriptionRead,
    BillingUsageRead,
    CheckoutRequest,
    CheckoutSessionRead,
    MinuteGrantRequest,
    PublicBillingPlanRead,
)
from app.services.billing import (
    InvalidBillingProviderEvent,
    add_admin_audit,
    current_subscription,
    grant_period_minutes,
    latest_subscription,
    process_provider_event,
    usage_summary,
    verify_provider_signature,
)
from app.services.business_authorization import BusinessPermission

logger = logging.getLogger(__name__)
router = APIRouter(tags=["billing"])
MAX_PAYMENT_WEBHOOK_BODY_BYTES = 64 * 1024
_ACTIVE_PROVIDER_STATUSES = {"active", "trialing"}


def _subscription_read(db: Session, subscription: BillingSubscription) -> dict[str, Any]:
    plan = db.get(BillingPlan, subscription.plan_id)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Subscription plan is unavailable",
        )
    return {
        "id": subscription.id,
        "business_id": subscription.business_id,
        "plan_id": subscription.plan_id,
        "provider": subscription.provider,
        "status": subscription.status,
        "current_period_start": subscription.current_period_start,
        "current_period_end": subscription.current_period_end,
        "trial_end": subscription.trial_end,
        "cancel_at_period_end": subscription.cancel_at_period_end,
        "created_at": subscription.created_at,
        "plan": plan,
    }


def _payment_provider(settings: Settings):
    try:
        return get_payment_provider(settings)
    except PaymentProviderNotConfigured as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment provider integration is not configured",
        ) from error


@router.get("/billing/plans", response_model=list[PublicBillingPlanRead])
def list_billing_plans(
    db: Annotated[Session, Depends(get_db)],
) -> list[BillingPlan]:
    return list(
        db.scalars(
            select(BillingPlan)
            .where(BillingPlan.is_active.is_(True))
            .order_by(BillingPlan.monthly_price, BillingPlan.name)
        ).all()
    )


@router.get(
    "/businesses/{business_id}/billing/subscription",
    response_model=BillingSubscriptionRead | None,
)
def get_business_subscription(
    business: Annotated[
        Business,
        Depends(require_business_permission(BusinessPermission.READ)),
    ],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any] | None:
    subscription = latest_subscription(db, business.id)
    return _subscription_read(db, subscription) if subscription else None


@router.get(
    "/businesses/{business_id}/billing/usage",
    response_model=BillingUsageRead,
)
def get_business_usage(
    business: Annotated[
        Business,
        Depends(require_business_permission(BusinessPermission.READ)),
    ],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    return usage_summary(db, business.id)


@router.get(
    "/businesses/{business_id}/billing/invoices",
    response_model=list[BillingInvoiceRead],
)
def list_business_invoices(
    business: Annotated[
        Business,
        Depends(require_business_permission(BusinessPermission.READ)),
    ],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[BillingInvoice]:
    return list(
        db.scalars(
            select(BillingInvoice)
            .where(BillingInvoice.business_id == business.id)
            .order_by(BillingInvoice.created_at.desc(), BillingInvoice.id)
            .limit(limit)
        ).all()
    )


@router.post(
    "/businesses/{business_id}/billing/checkout",
    response_model=CheckoutSessionRead,
)
def create_checkout_session(
    payload: CheckoutRequest,
    business: Annotated[
        Business,
        Depends(
            require_business_permission(BusinessPermission.MANAGE_SETTINGS)
        ),
    ],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    plan = db.scalar(
        select(BillingPlan).where(
            BillingPlan.id == payload.plan_id,
            BillingPlan.is_active.is_(True),
        )
    )
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Billing plan not found",
        )
    existing_subscription = latest_subscription(db, business.id)
    if existing_subscription is not None and existing_subscription.status != "cancelled":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This business already has a current subscription",
        )
    if not plan.provider_price_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This plan is not configured with a payment provider price",
        )

    customer = db.scalar(
        select(BillingCustomer).where(
            BillingCustomer.business_id == business.id,
            BillingCustomer.provider == (settings.PAYMENT_PROVIDER or ""),
        )
    )
    provider = _payment_provider(settings)
    provider_customer_id = customer.provider_customer_id if customer else None
    db.rollback()
    try:
        if provider_customer_id is None:
            provider_customer_id = provider.create_customer(business.id, current_user.email)
            with db.begin():
                db.add(
                    BillingCustomer(
                        business_id=business.id,
                        provider=provider.name,
                        provider_customer_id=provider_customer_id,
                    )
                )
        checkout = provider.create_checkout_session(
            customer_id=provider_customer_id,
            provider_plan_id=plan.provider_price_id,
            business_id=business.id,
            success_url=f"{settings.FRONTEND_ORIGIN}/billing?checkout=success",
            cancel_url=f"{settings.FRONTEND_ORIGIN}/billing?checkout=cancelled",
        )
    except PaymentProviderError as error:
        db.rollback()
        logger.error(
            "Billing checkout provider operation failed",
            extra={"provider": settings.PAYMENT_PROVIDER, "error_type": type(error).__name__},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Checkout is temporarily unavailable",
        ) from None
    except IntegrityError:
        db.rollback()
        customer = db.scalar(
            select(BillingCustomer).where(
                BillingCustomer.business_id == business.id,
                BillingCustomer.provider == provider.name,
            )
        )
        if customer is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Checkout is temporarily unavailable",
            ) from None
        db.rollback()
        checkout = provider.create_checkout_session(
            customer_id=customer.provider_customer_id,
            provider_plan_id=plan.provider_price_id,
            business_id=business.id,
            success_url=f"{settings.FRONTEND_ORIGIN}/billing?checkout=success",
            cancel_url=f"{settings.FRONTEND_ORIGIN}/billing?checkout=cancelled",
        )
    return {"checkout_url": _provider_redirect_url(checkout.redirect_url)}


def _provider_redirect_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment provider returned an invalid redirect",
        ) from error
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment provider returned an invalid redirect",
        )
    return value


@router.post("/businesses/{business_id}/billing/cancel", status_code=204)
def cancel_business_subscription(
    business: Annotated[
        Business,
        Depends(require_business_permission(BusinessPermission.MANAGE_SETTINGS)),
    ],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    subscription = latest_subscription(db, business.id)
    if (
        subscription is None
        or subscription.status == "cancelled"
        or subscription.provider_subscription_id is None
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active subscription not found",
        )
    provider_id = subscription.provider_subscription_id
    subscription_id = subscription.id
    provider = _payment_provider(settings)
    db.rollback()
    try:
        provider.cancel_subscription(provider_id, at_period_end=True)
    except PaymentProviderError as error:
        logger.error(
            "Billing cancellation provider operation failed",
            extra={"provider": settings.PAYMENT_PROVIDER, "error_type": type(error).__name__},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Subscription cancellation is temporarily unavailable",
        ) from None
    subscription = db.get(BillingSubscription, subscription_id)
    if subscription is not None:
        subscription.cancel_at_period_end = True
        db.commit()


@router.post(
    "/businesses/{business_id}/billing/change-plan",
    response_model=BillingSubscriptionRead,
)
def change_business_plan(
    payload: CheckoutRequest,
    business: Annotated[
        Business,
        Depends(require_business_permission(BusinessPermission.MANAGE_SETTINGS)),
    ],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    subscription = current_subscription(db, business.id)
    new_plan = db.scalar(
        select(BillingPlan).where(
            BillingPlan.id == payload.plan_id,
            BillingPlan.is_active.is_(True),
        )
    )
    if subscription is None or new_plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription or plan not found",
        )
    if not new_plan.provider_price_id or not subscription.provider_subscription_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The plan or subscription is not configured with the provider",
        )
    provider_subscription_id = subscription.provider_subscription_id
    subscription_id = subscription.id
    provider = _payment_provider(settings)
    db.rollback()
    try:
        provider.change_plan(provider_subscription_id, new_plan.provider_price_id)
    except PaymentProviderError as error:
        logger.error(
            "Billing plan change provider operation failed",
            extra={"provider": settings.PAYMENT_PROVIDER, "error_type": type(error).__name__},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Plan change is temporarily unavailable",
        ) from None
    subscription = db.get(BillingSubscription, subscription_id)
    if subscription is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Subscription changed while the plan was being updated",
        )
    return _subscription_read(db, subscription)


@router.post(
    "/businesses/{business_id}/billing/portal",
    response_model=CheckoutSessionRead,
)
def create_billing_portal_session(
    business: Annotated[
        Business,
        Depends(require_business_permission(BusinessPermission.MANAGE_SETTINGS)),
    ],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    customer = db.scalar(
        select(BillingCustomer).where(
            BillingCustomer.business_id == business.id,
            BillingCustomer.provider == (settings.PAYMENT_PROVIDER or ""),
        )
    )
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment customer not found",
        )
    customer_id = customer.provider_customer_id
    provider = _payment_provider(settings)
    db.rollback()
    try:
        portal_url = provider.create_portal_session(
            customer_id,
            f"{settings.FRONTEND_ORIGIN}/billing",
        )
    except PaymentProviderError as error:
        logger.error(
            "Billing portal provider operation failed",
            extra={"provider": settings.PAYMENT_PROVIDER, "error_type": type(error).__name__},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Billing portal is temporarily unavailable",
        ) from None
    return {"checkout_url": _provider_redirect_url(portal_url)}


async def _read_payment_webhook_body(request: Request) -> bytes:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        if not content_length.isascii() or not content_length.isdecimal():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid payment webhook payload",
            )
        if int(content_length) > MAX_PAYMENT_WEBHOOK_BODY_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="Payment webhook payload is too large",
            )
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_PAYMENT_WEBHOOK_BODY_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="Payment webhook payload is too large",
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/billing/webhooks/{provider}")
async def receive_billing_webhook(
    provider: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    signature: Annotated[str | None, Header(alias="Provider-Signature")] = None,
) -> dict[str, str]:
    if (
        settings.PAYMENT_PROVIDER is None
        or provider != settings.PAYMENT_PROVIDER
        or settings.PAYMENT_WEBHOOK_SECRET is None
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment webhook is not configured",
        )
    body = await _read_payment_webhook_body(request)
    verify_provider_signature(
        body,
        signature,
        settings.PAYMENT_WEBHOOK_SECRET.get_secret_value(),
    )
    try:
        parsed = json.loads(body, parse_float=Decimal)
        event = BillingProviderEventPayload.model_validate(parsed)
    except (json.JSONDecodeError, UnicodeDecodeError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payment webhook payload",
        ) from None

    try:
        created_at = (
            datetime.fromtimestamp(event.created, tz=UTC)
            if event.created is not None
            else None
        )
    except (OverflowError, OSError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payment webhook event",
        ) from None
    try:
        processed = process_provider_event(
            db,
            provider,
            event.id,
            event.type,
            created_at,
            event.data,
        )
    except InvalidBillingProviderEvent:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payment webhook event",
        ) from None
    except SQLAlchemyError as error:
        db.rollback()
        logger.error(
            "Billing webhook database operation failed",
            extra={"provider": provider, "error_type": type(error).__name__},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment webhook processing temporarily unavailable",
        ) from None
    return {"status": "processed" if processed else "duplicate"}


admin_router = APIRouter(
    prefix="/admin/billing",
    tags=["billing administration"],
    dependencies=[Depends(require_platform_billing_admin)],
)


@admin_router.get("/overview")
def get_billing_overview(db: Annotated[Session, Depends(get_db)]) -> dict[str, Any]:
    active_count = db.scalar(
        select(func.count(BillingSubscription.id)).where(
            BillingSubscription.status.in_(("active", "trialing"))
        )
    ) or 0
    past_due_count = db.scalar(
        select(func.count(BillingSubscription.id)).where(
            BillingSubscription.status == "past_due"
        )
    ) or 0
    mrr_by_currency = db.execute(
        select(BillingPlan.currency, func.sum(BillingPlan.monthly_price))
        .join(BillingSubscription, BillingSubscription.plan_id == BillingPlan.id)
        .where(BillingSubscription.status.in_(("active", "trialing")))
        .group_by(BillingPlan.currency)
    ).all()
    usage_seconds = db.scalar(
        select(func.coalesce(func.sum(BillingUsage.billable_seconds), 0))
    ) or 0
    payments = list(
        db.scalars(
            select(BillingPayment)
            .order_by(BillingPayment.created_at.desc())
            .limit(10)
        ).all()
    )
    return {
        "active_subscriptions": active_count,
        "past_due_subscriptions": past_due_count,
        "monthly_recurring_revenue_by_currency": {
            currency: amount for currency, amount in mrr_by_currency
        },
        "total_usage_seconds": int(usage_seconds),
        "recent_payments": [
            BillingPaymentRead.model_validate(payment) for payment in payments
        ],
    }


@admin_router.get("/subscriptions")
def admin_list_subscriptions(
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
) -> list[dict[str, Any]]:
    rows = db.execute(
        select(BillingSubscription, Business.name, BillingPlan.name)
        .join(Business, Business.id == BillingSubscription.business_id)
        .join(BillingPlan, BillingPlan.id == BillingSubscription.plan_id)
        .order_by(BillingSubscription.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [
        {
            "id": subscription.id,
            "business_id": subscription.business_id,
            "business_name": business_name,
            "plan_id": subscription.plan_id,
            "plan_name": plan_name,
            "provider": subscription.provider,
            "status": subscription.status,
            "provider_status": subscription.provider_status,
            "current_period_start": subscription.current_period_start,
            "current_period_end": subscription.current_period_end,
            "cancel_at_period_end": subscription.cancel_at_period_end,
        }
        for subscription, business_name, plan_name in rows
    ]


@admin_router.get("/plans", response_model=list[BillingPlanRead])
def admin_list_plans(
    db: Annotated[Session, Depends(get_db)],
) -> list[BillingPlan]:
    return list(db.scalars(select(BillingPlan).order_by(BillingPlan.name)).all())


@admin_router.get("/usage")
def admin_list_usage(
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[dict[str, Any]]:
    rows = db.execute(
        select(
            BillingUsage.business_id,
            Business.name,
            func.sum(BillingUsage.billable_seconds),
            func.max(BillingUsage.created_at),
        )
        .join(Business, Business.id == BillingUsage.business_id)
        .group_by(BillingUsage.business_id, Business.name)
        .order_by(func.max(BillingUsage.created_at).desc())
        .limit(limit)
    ).all()
    return [
        {
            "business_id": business_id,
            "business_name": business_name,
            "used_seconds": int(used_seconds or 0),
            "used_minutes": (int(used_seconds or 0) + 59) // 60,
            "last_usage_at": last_usage_at,
        }
        for business_id, business_name, used_seconds, last_usage_at in rows
    ]


@admin_router.get("/payments", response_model=list[BillingPaymentRead])
def admin_list_payments(
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
) -> list[BillingPayment]:
    return list(
        db.scalars(
            select(BillingPayment)
            .order_by(BillingPayment.created_at.desc())
            .limit(limit)
            .offset(offset)
        ).all()
    )


@admin_router.post("/plans", response_model=BillingPlanRead, status_code=201)
def admin_create_plan(
    payload: BillingPlanCreate,
    admin: Annotated[User, Depends(require_platform_billing_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> BillingPlan:
    plan = BillingPlan(**payload.model_dump())
    db.add(plan)
    try:
        db.flush()
        add_admin_audit(
            db,
            admin_user_id=admin.id,
            action="plan.created",
            details=f"plan_id={plan.id}",
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A billing plan with this name already exists",
        ) from None
    db.refresh(plan)
    return plan


@admin_router.patch("/plans/{plan_id}", response_model=BillingPlanRead)
def admin_update_plan(
    plan_id: UUID,
    payload: BillingPlanUpdate,
    admin: Annotated[User, Depends(require_platform_billing_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> BillingPlan:
    plan = db.get(BillingPlan, plan_id)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Billing plan not found",
        )
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(plan, field, value)
    try:
        add_admin_audit(
            db,
            admin_user_id=admin.id,
            action="plan.updated",
            details=f"plan_id={plan.id}; fields={','.join(payload.model_fields_set)}",
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A billing plan with this name already exists",
        ) from None
    db.refresh(plan)
    return plan


@admin_router.post("/subscriptions/{subscription_id}/adjust-minutes", status_code=201)
def admin_adjust_subscription_minutes(
    subscription_id: UUID,
    payload: MinuteGrantRequest,
    admin: Annotated[User, Depends(require_platform_billing_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    subscription = db.scalar(
        select(BillingSubscription)
        .where(BillingSubscription.id == subscription_id)
        .with_for_update()
    )
    if subscription is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )
    grant = grant_period_minutes(
        db,
        subscription=subscription,
        admin_user_id=admin.id,
        minutes=payload.minutes,
        reason=payload.reason,
    )
    db.commit()
    return {
        "id": grant.id,
        "subscription_id": grant.subscription_id,
        "minutes": grant.minutes,
        "reason": grant.reason,
        "billing_period_id": grant.billing_period_id,
        "created_at": grant.created_at,
    }


@admin_router.post("/subscriptions/{subscription_id}/suspend")
def admin_suspend_subscription(
    subscription_id: UUID,
    admin: Annotated[User, Depends(require_platform_billing_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    subscription = db.scalar(
        select(BillingSubscription)
        .where(BillingSubscription.id == subscription_id)
        .with_for_update()
    )
    if subscription is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )
    subscription.suspended_by_admin = True
    subscription.status = "suspended"
    add_admin_audit(
        db,
        admin_user_id=admin.id,
        action="subscription.suspended",
        business_id=subscription.business_id,
        subscription_id=subscription.id,
    )
    db.commit()
    return {"status": "suspended"}


@admin_router.post("/subscriptions/{subscription_id}/reactivate")
def admin_reactivate_subscription(
    subscription_id: UUID,
    admin: Annotated[User, Depends(require_platform_billing_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    subscription = db.scalar(
        select(BillingSubscription)
        .where(BillingSubscription.id == subscription_id)
        .with_for_update()
    )
    if subscription is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )
    if (
        subscription.provider_status not in _ACTIVE_PROVIDER_STATUSES
        or subscription.current_period_end is None
        or subscription.current_period_end <= datetime.now(UTC)
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The provider subscription is not eligible for reactivation",
        )
    subscription.suspended_by_admin = False
    subscription.status = subscription.provider_status
    add_admin_audit(
        db,
        admin_user_id=admin.id,
        action="subscription.reactivated",
        business_id=subscription.business_id,
        subscription_id=subscription.id,
    )
    db.commit()
    return {"status": subscription.status}


router.include_router(admin_router)
