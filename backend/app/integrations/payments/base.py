from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.core.config import Settings


class PaymentProviderError(Exception):
    pass


class PaymentProviderNotConfigured(PaymentProviderError):
    pass


@dataclass(frozen=True)
class CheckoutSession:
    provider_session_id: str
    redirect_url: str
    provider_customer_id: str


class PaymentProvider(Protocol):
    name: str

    def create_customer(self, business_id: UUID, email: str) -> str: ...

    def create_subscription(
        self,
        customer_id: str,
        provider_plan_id: str,
        business_id: UUID,
    ) -> str: ...

    def cancel_subscription(
        self,
        provider_subscription_id: str,
        *,
        at_period_end: bool,
    ) -> None: ...

    def change_plan(
        self,
        provider_subscription_id: str,
        provider_plan_id: str,
    ) -> None: ...

    def create_checkout_session(
        self,
        customer_id: str | None,
        provider_plan_id: str,
        business_id: UUID,
        success_url: str,
        cancel_url: str,
    ) -> CheckoutSession: ...

    def create_portal_session(self, customer_id: str, return_url: str) -> str: ...

    def retrieve_invoice(self, provider_invoice_id: str) -> dict[str, object]: ...


def get_payment_provider(settings: Settings) -> PaymentProvider:
    raise PaymentProviderNotConfigured(
        "No payment provider adapter is configured; payment actions are disabled"
    )
