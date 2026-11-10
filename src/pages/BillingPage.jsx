import { ArrowUpRight, CreditCard, ExternalLink, ReceiptText } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Button, Card, EmptyState, ErrorState, LoadingState, PageHeader, StatusBadge } from "../components/ui";
import { useBusiness } from "../business/BusinessContext";
import { api, userFacingErrorMessage } from "../lib/api";

export function BillingPage() {
  const { activeBusiness } = useBusiness();
  const [plans, setPlans] = useState([]);
  const [subscription, setSubscription] = useState(null);
  const [usage, setUsage] = useState(null);
  const [invoices, setInvoices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const refresh = useCallback(async () => {
    if (!activeBusiness) {
      setPlans([]);
      setSubscription(null);
      setUsage(null);
      setInvoices([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    const results = await Promise.allSettled([
      api.billingPlans(),
      api.billingSubscription(activeBusiness.id),
      api.billingUsage(activeBusiness.id),
      api.billingInvoices(activeBusiness.id),
    ]);
    setPlans(results[0].status === "fulfilled" ? results[0].value : []);
    setSubscription(results[1].status === "fulfilled" ? results[1].value : null);
    setUsage(results[2].status === "fulfilled" ? results[2].value : null);
    setInvoices(results[3].status === "fulfilled" ? results[3].value : []);
    const failure = results.find((result) => result.status === "rejected");
    if (failure) {
      setError(userFacingErrorMessage(failure.reason, "Billing data could not be loaded."));
    }
    setLoading(false);
  }, [activeBusiness]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const runAction = async (action, successMessage) => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
      setNotice(successMessage);
      await refresh();
    } catch (cause) {
      setError(userFacingErrorMessage(cause, "The billing action could not be completed."));
    } finally {
      setBusy(false);
    }
  };

  const choosePlan = (plan) => {
    if (!activeBusiness) return;
    const hasCurrentSubscription = subscription && subscription.status !== "cancelled";
    const action = hasCurrentSubscription
      ? () => api.changeBillingPlan(activeBusiness.id, plan.id)
      : () => api.createBillingCheckout(activeBusiness.id, plan.id)
        .then(({ checkout_url }) => {
          window.location.assign(checkout_url);
        });
    void runAction(action, hasCurrentSubscription ? "Plan change requested." : "Opening secure checkout.");
  };

  const hasCurrentSubscription = subscription && subscription.status !== "cancelled";
  const canChangePlan = ["active", "trialing"].includes(subscription?.status);
  const canCancelSubscription = ["active", "trialing", "past_due", "suspended"].includes(subscription?.status);
  const usagePercent = Math.min(100, Math.max(0, usage?.usage_percent ?? 0));
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Workspace"
        title="Billing & usage"
        description={activeBusiness ? `Subscription and call usage for ${activeBusiness.name}.` : "Select a business workspace to view its billing."}
        action={subscription && (
          <Button
            variant="secondary"
            disabled={busy}
            onClick={() => void runAction(
              () => api.billingPortal(activeBusiness.id).then(({ checkout_url }) => window.location.assign(checkout_url)),
              "Opening billing portal."
            )}
          >
            <ExternalLink size={15} /> Manage payment method
          </Button>
        )}
      />
      {error && <ErrorState message={error} onRetry={() => void refresh()} />}
      {notice && <div className="success-banner">{notice}</div>}
      {!activeBusiness ? (
        <EmptyState title="No business selected" description="Choose a workspace to see subscription and usage details." />
      ) : loading ? (
        <LoadingState label="Loading billing details" />
      ) : (
        <>
          <Card className="billing-summary-card">
            <div className="billing-summary-heading">
              <div>
                <span className="eyebrow">Current subscription</span>
                <h2>{hasCurrentSubscription ? subscription.plan.name : "No active plan"}</h2>
                <p>{subscription?.status === "cancelled"
                  ? `Your ${subscription.plan.name} subscription has ended.`
                  : subscription?.plan?.description || "Choose a configurable plan to get started."}</p>
              </div>
              {subscription && <StatusBadge status={subscription.status} />}
            </div>
            <div className="billing-metrics">
              <BillingMetric label="Monthly price" value={subscription ? formatMoney(subscription.plan.monthly_price, subscription.plan.currency) : "—"} />
              <BillingMetric label="Minutes included" value={usage ? usage.included_minutes.toLocaleString() : "—"} />
              <BillingMetric label="Minutes used" value={usage ? usage.used_minutes.toLocaleString() : "—"} />
              <BillingMetric label="Remaining" value={usage ? usage.remaining_minutes.toLocaleString() : "—"} />
              <BillingMetric label="Next billing date" value={subscription?.current_period_end ? formatDate(subscription.current_period_end) : "—"} />
            </div>
            {usage && (
              <div className="billing-usage-meter">
                <div className="billing-usage-label">
                  <span>{usage.used_seconds.toLocaleString()} billable seconds</span>
                  <span>{usagePercent.toFixed(0)}%</span>
                </div>
                <progress max="100" value={usagePercent} aria-label="Included call-minute usage" />
                <small>Seconds are aggregated for the billing period, then rounded up once to whole minutes.</small>
              </div>
            )}
            {subscription?.cancel_at_period_end && (
              <p className="billing-inline-notice">Cancellation is scheduled for the end of this billing period.</p>
            )}
            {canCancelSubscription && !subscription.cancel_at_period_end && (
              <Button
                variant="ghost"
                disabled={busy}
                onClick={() => {
                  if (window.confirm("Cancel this subscription at the end of the current billing period?")) {
                    void runAction(
                      () => api.cancelBillingSubscription(activeBusiness.id),
                      "Cancellation requested; service remains available through the current period."
                    );
                  }
                }}
              >
                Cancel subscription
              </Button>
            )}
          </Card>

          <Card>
            <div className="card-heading">
              <div>
                <h2>Available plans</h2>
                <p>Prices and allowances are managed by the platform administrator.</p>
              </div>
            </div>
            {plans.length === 0 ? (
              <EmptyState title="No plans are available" description="Contact the platform administrator for billing plan setup." />
            ) : (
              <div className="billing-plan-grid">
                {plans.map((plan) => (
                  <article className={`billing-plan ${hasCurrentSubscription && subscription.plan_id === plan.id ? "billing-plan-current" : ""}`} key={plan.id}>
                    <div className="billing-plan-heading">
                      <div><h3>{plan.name}</h3><span>{formatMoney(plan.monthly_price, plan.currency)} / month</span></div>
                      {hasCurrentSubscription && subscription.plan_id === plan.id && <StatusBadge status={subscription.status} />}
                    </div>
                    <p>{plan.description || "Flexible call-answering service for your business."}</p>
                    <ul>
                      <li>{plan.included_minutes.toLocaleString()} included minutes</li>
                      <li>Up to {plan.max_phone_numbers} phone numbers</li>
                    </ul>
                    <Button
                      variant={hasCurrentSubscription && subscription.plan_id === plan.id ? "secondary" : "primary"}
                      disabled={busy || (hasCurrentSubscription && (
                        subscription.plan_id === plan.id || !canChangePlan
                      ))}
                      onClick={() => choosePlan(plan)}
                    >
                      {hasCurrentSubscription && subscription.plan_id === plan.id
                        ? "Current plan"
                        : hasCurrentSubscription && !canChangePlan
                          ? "Plan unavailable"
                          : hasCurrentSubscription
                            ? "Change plan"
                            : "Choose plan"}
                      {(!hasCurrentSubscription || (canChangePlan && subscription.plan_id !== plan.id)) && <ArrowUpRight size={15} />}
                    </Button>
                  </article>
                ))}
              </div>
            )}
          </Card>

          <Card>
            <div className="card-heading">
              <div>
                <h2>Billing history</h2>
                <p>Invoices and payment status from the configured provider.</p>
              </div>
              <ReceiptText size={18} />
            </div>
            {invoices.length === 0 ? (
              <EmptyState title="No invoices yet" description="Invoices appear here after the payment provider confirms them." />
            ) : (
              <div className="table-scroll">
                <table className="data-table">
                  <thead><tr><th>Invoice</th><th>Amount</th><th>Status</th><th>Due</th><th>Paid</th><th /></tr></thead>
                  <tbody>
                    {invoices.map((invoice) => (
                      <tr key={invoice.id}>
                        <td>{formatDate(invoice.created_at)}</td>
                        <td>{formatMoney(invoice.amount, invoice.currency)}</td>
                        <td><StatusBadge status={invoice.status} /></td>
                        <td>{invoice.due_date ? formatDate(invoice.due_date) : "—"}</td>
                        <td>{invoice.paid_at ? formatDate(invoice.paid_at) : "—"}</td>
                        <td>{invoice.hosted_invoice_url && <a className="text-link" href={invoice.hosted_invoice_url} target="_blank" rel="noreferrer">View <ExternalLink size={13} /></a>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
          <p className="billing-provider-note"><CreditCard size={14} /> Secure checkout and payment management are disabled until a real payment-provider adapter is configured. No payment is simulated.</p>
        </>
      )}
    </div>
  );
}

function BillingMetric({ label, value }) {
  return <div className="billing-metric"><span>{label}</span><strong>{value}</strong></div>;
}

function formatMoney(value, currency) {
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(Number(value));
  } catch {
    return `${currency} ${Number(value).toFixed(2)}`;
  }
}

function formatDate(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(date);
}
