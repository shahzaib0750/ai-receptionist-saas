import { Plus, RefreshCw, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Button, Card, ErrorState, Field, LoadingState, PageHeader, StatusBadge } from "../components/ui";
import { api, userFacingErrorMessage } from "../lib/api";

const emptyPlan = {
  name: "",
  description: "",
  monthly_price: "",
  currency: "USD",
  included_minutes: "",
  max_phone_numbers: "1",
  provider_price_id: "",
  is_active: true,
};

export function AdminBillingPage() {
  const [overview, setOverview] = useState(null);
  const [plans, setPlans] = useState([]);
  const [subscriptions, setSubscriptions] = useState([]);
  const [payments, setPayments] = useState([]);
  const [form, setForm] = useState(emptyPlan);
  const [editingPlanId, setEditingPlanId] = useState(null);
  const [editForm, setEditForm] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    const results = await Promise.allSettled([
      api.adminBillingOverview(),
      api.adminBillingPlans(),
      api.adminBillingSubscriptions(),
      api.adminBillingPayments(),
    ]);
    setOverview(results[0].status === "fulfilled" ? results[0].value : null);
    setPlans(results[1].status === "fulfilled" ? results[1].value : []);
    setSubscriptions(results[2].status === "fulfilled" ? results[2].value : []);
    setPayments(results[3].status === "fulfilled" ? results[3].value : []);
    const failure = results.find((result) => result.status === "rejected");
    if (failure) setError(userFacingErrorMessage(failure.reason, "Admin billing data could not be loaded."));
    setLoading(false);
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const submitPlan = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await api.createBillingPlan({
        ...form,
        monthly_price: Number(form.monthly_price),
        included_minutes: Number(form.included_minutes),
        max_phone_numbers: Number(form.max_phone_numbers),
        provider_price_id: form.provider_price_id || null,
      });
      setForm(emptyPlan);
      setNotice("Plan created.");
      await refresh();
    } catch (cause) {
      setError(userFacingErrorMessage(cause, "Could not create the plan."));
    } finally {
      setBusy(false);
    }
  };

  const updatePlan = async (plan, payload) => {
    setBusy(true);
    setError("");
    try {
      await api.updateBillingPlan(plan.id, payload);
      setEditingPlanId(null);
      setEditForm(null);
      setNotice(`${plan.name} updated.`);
      await refresh();
    } catch (cause) {
      setError(userFacingErrorMessage(cause, "Could not update the plan."));
    } finally {
      setBusy(false);
    }
  };

  const changeSubscription = async (subscription, action) => {
    setBusy(true);
    setError("");
    try {
      await action(subscription.id);
      setNotice(`Subscription for ${subscription.business_name} updated.`);
      await refresh();
    } catch (cause) {
      setError(userFacingErrorMessage(cause, "Could not update the subscription."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Platform"
        title="Billing administration"
        description="Manage configurable plans, monitor subscriptions, and review provider-confirmed payments."
        action={<Button variant="secondary" disabled={loading} onClick={() => void refresh()}><RefreshCw size={15} /> Refresh</Button>}
      />
      {error && <ErrorState message={error} onRetry={() => void refresh()} />}
      {notice && <div className="success-banner"><ShieldCheck size={15} />{notice}</div>}
      {loading ? <LoadingState label="Loading billing administration" /> : (
        <>
          {overview && (
            <div className="billing-metrics">
              <BillingMetric label="Active subscriptions" value={overview.active_subscriptions} />
              <BillingMetric label="Past due" value={overview.past_due_subscriptions} />
              <BillingMetric
                label="Monthly recurring revenue"
                value={Object.entries(overview.monthly_recurring_revenue_by_currency || {}).map(([currency, amount]) => formatMoney(amount, currency)).join(" · ") || "—"}
              />
              <BillingMetric label="Recorded usage" value={`${overview.total_usage_seconds.toLocaleString()} sec`} />
            </div>
          )}

          <Card>
            <div className="card-heading"><div><h2>Plans</h2><p>Pricing and allowances are stored in the database; no default price is hardcoded.</p></div></div>
            <div className="billing-plan-grid">
              {plans.map((plan) => (
                <article className="billing-plan" key={plan.id}>
                  <div className="billing-plan-heading">
                    <div><h3>{plan.name}</h3><span>{formatMoney(plan.monthly_price, plan.currency)} / month</span></div>
                    <StatusBadge status={plan.is_active ? "active" : "disabled"} />
                  </div>
                  <p>{plan.description || "No description"}</p>
                  <ul><li>{plan.included_minutes.toLocaleString()} minutes</li><li>{plan.max_phone_numbers} phone numbers</li></ul>
                  {editingPlanId === plan.id && editForm ? (
                    <form
                      className="billing-admin-form"
                      onSubmit={(event) => {
                        event.preventDefault();
                        void updatePlan(plan, {
                          ...editForm,
                          monthly_price: Number(editForm.monthly_price),
                          included_minutes: Number(editForm.included_minutes),
                          max_phone_numbers: Number(editForm.max_phone_numbers),
                          provider_price_id: editForm.provider_price_id || null,
                        });
                      }}
                    >
                      <div className="billing-admin-fields">
                        <Field id={`edit-plan-name-${plan.id}`} label="Plan name"><input id={`edit-plan-name-${plan.id}`} required maxLength={80} value={editForm.name} onChange={(event) => setEditForm({ ...editForm, name: event.target.value })} /></Field>
                        <Field id={`edit-plan-price-${plan.id}`} label="Monthly price"><input id={`edit-plan-price-${plan.id}`} type="number" min="0" step="0.01" required value={editForm.monthly_price} onChange={(event) => setEditForm({ ...editForm, monthly_price: event.target.value })} /></Field>
                        <Field id={`edit-plan-currency-${plan.id}`} label="Currency"><input id={`edit-plan-currency-${plan.id}`} required minLength={3} maxLength={3} pattern="[A-Z]{3}" value={editForm.currency} onChange={(event) => setEditForm({ ...editForm, currency: event.target.value.toUpperCase() })} /></Field>
                        <Field id={`edit-plan-minutes-${plan.id}`} label="Included minutes"><input id={`edit-plan-minutes-${plan.id}`} type="number" min="0" required value={editForm.included_minutes} onChange={(event) => setEditForm({ ...editForm, included_minutes: event.target.value })} /></Field>
                        <Field id={`edit-plan-phones-${plan.id}`} label="Phone number limit"><input id={`edit-plan-phones-${plan.id}`} type="number" min="1" required value={editForm.max_phone_numbers} onChange={(event) => setEditForm({ ...editForm, max_phone_numbers: event.target.value })} /></Field>
                        <Field id={`edit-plan-provider-price-${plan.id}`} label="Provider price ID"><input id={`edit-plan-provider-price-${plan.id}`} maxLength={255} value={editForm.provider_price_id} onChange={(event) => setEditForm({ ...editForm, provider_price_id: event.target.value })} /></Field>
                      </div>
                      <Field id={`edit-plan-description-${plan.id}`} label="Description"><textarea id={`edit-plan-description-${plan.id}`} maxLength={2000} value={editForm.description} onChange={(event) => setEditForm({ ...editForm, description: event.target.value })} /></Field>
                      <div className="billing-admin-actions">
                        <Button type="submit" size="sm" disabled={busy}>Save changes</Button>
                        <Button type="button" size="sm" variant="ghost" disabled={busy} onClick={() => { setEditingPlanId(null); setEditForm(null); }}>Cancel</Button>
                      </div>
                    </form>
                  ) : (
                    <Button
                      variant="secondary"
                      disabled={busy}
                      onClick={() => {
                        setEditingPlanId(plan.id);
                        setEditForm({
                          name: plan.name,
                          description: plan.description || "",
                          monthly_price: String(plan.monthly_price),
                          currency: plan.currency,
                          included_minutes: String(plan.included_minutes),
                          max_phone_numbers: String(plan.max_phone_numbers),
                          provider_price_id: plan.provider_price_id || "",
                        });
                      }}
                    >
                      Edit plan
                    </Button>
                  )}
                  <Button
                    variant="secondary"
                    disabled={busy}
                    onClick={() => void updatePlan(plan, { is_active: !plan.is_active })}
                  >
                    {plan.is_active ? "Deactivate plan" : "Activate plan"}
                  </Button>
                </article>
              ))}
            </div>
            <form className="billing-admin-form" onSubmit={(event) => void submitPlan(event)}>
              <h3>Create a plan</h3>
              <div className="billing-admin-fields">
                <Field id="plan-name" label="Plan name"><input id="plan-name" required maxLength={80} value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></Field>
                <Field id="plan-price" label="Monthly price"><input id="plan-price" type="number" min="0" step="0.01" required value={form.monthly_price} onChange={(event) => setForm({ ...form, monthly_price: event.target.value })} /></Field>
                <Field id="plan-currency" label="Currency"><input id="plan-currency" required minLength={3} maxLength={3} pattern="[A-Z]{3}" value={form.currency} onChange={(event) => setForm({ ...form, currency: event.target.value.toUpperCase() })} /></Field>
                <Field id="plan-minutes" label="Included minutes"><input id="plan-minutes" type="number" min="0" required value={form.included_minutes} onChange={(event) => setForm({ ...form, included_minutes: event.target.value })} /></Field>
                <Field id="plan-phones" label="Phone number limit"><input id="plan-phones" type="number" min="1" required value={form.max_phone_numbers} onChange={(event) => setForm({ ...form, max_phone_numbers: event.target.value })} /></Field>
                <Field id="plan-provider-price" label="Provider price ID" hint="Optional until a real payment adapter is configured."><input id="plan-provider-price" maxLength={255} value={form.provider_price_id} onChange={(event) => setForm({ ...form, provider_price_id: event.target.value })} /></Field>
              </div>
              <Field id="plan-description" label="Description"><textarea id="plan-description" maxLength={2000} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></Field>
              <Button type="submit" disabled={busy}><Plus size={15} />Create plan</Button>
            </form>
          </Card>

          <Card>
            <div className="card-heading"><div><h2>Subscriptions</h2><p>Provider status and administrative entitlement controls.</p></div></div>
            {subscriptions.length === 0 ? <p className="billing-empty">No subscriptions recorded.</p> : (
              <div className="table-scroll"><table className="data-table">
                <thead><tr><th>Business</th><th>Plan</th><th>Status</th><th>Period end</th><th>Actions</th></tr></thead>
                <tbody>{subscriptions.map((subscription) => (
                  <tr key={subscription.id}>
                    <td>{subscription.business_name}</td>
                    <td>{subscription.plan_name}</td>
                    <td><StatusBadge status={subscription.status} /></td>
                    <td>{subscription.current_period_end ? formatDate(subscription.current_period_end) : "—"}</td>
                    <td className="billing-admin-actions">
                      {subscription.status !== "suspended" ? (
                        <Button size="sm" variant="ghost" disabled={busy} onClick={() => void changeSubscription(subscription, api.suspendBillingSubscription)}>Suspend</Button>
                      ) : (
                        <Button size="sm" variant="secondary" disabled={busy} onClick={() => void changeSubscription(subscription, api.reactivateBillingSubscription)}>Reactivate</Button>
                      )}
                      <GrantMinutesForm
                        disabled={busy}
                        onGrant={(minutes, reason) => void changeSubscription(
                          subscription,
                          (id) => api.grantBillingMinutes(id, minutes, reason)
                        )}
                      />
                    </td>
                  </tr>
                ))}</tbody>
              </table></div>
            )}
          </Card>

          <Card>
            <div className="card-heading"><div><h2>Recent payments</h2><p>Payment records are written only from signed provider events.</p></div></div>
            {payments.length === 0 ? <p className="billing-empty">No payment records yet.</p> : (
              <div className="table-scroll"><table className="data-table">
                <thead><tr><th>Amount</th><th>Status</th><th>Reference</th><th>Date</th></tr></thead>
                <tbody>{payments.map((payment) => (
                  <tr key={payment.id}><td>{formatMoney(payment.amount, payment.currency)}</td><td><StatusBadge status={payment.status} /></td><td>{payment.payment_reference || "—"}</td><td>{formatDate(payment.created_at)}</td></tr>
                ))}</tbody>
              </table></div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}

function GrantMinutesForm({ disabled, onGrant }) {
  const [minutes, setMinutes] = useState("");
  const [reason, setReason] = useState("");
  return (
    <form className="billing-grant-form" onSubmit={(event) => {
      event.preventDefault();
      onGrant(Number(minutes), reason);
      setMinutes("");
      setReason("");
    }}>
      <input aria-label="Additional minutes" type="number" min="1" required value={minutes} onChange={(event) => setMinutes(event.target.value)} />
      <input aria-label="Grant reason" placeholder="Reason" minLength="3" required value={reason} onChange={(event) => setReason(event.target.value)} />
      <Button size="sm" variant="ghost" disabled={disabled}>Grant</Button>
    </form>
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
