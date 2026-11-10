import { ArrowUpRight, Check, Clock3, Phone, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, userFacingErrorMessage } from "../../lib/api";

export function PlanCatalog({ compact = false, user }) {
  const [plans, setPlans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    api.billingPlans()
      .then((result) => {
        if (active) setPlans(result);
      })
      .catch((cause) => {
        if (!active) return;
        setPlans([]);
        setError(userFacingErrorMessage(cause, "We couldn’t load pricing plans right now."));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [attempt]);

  if (loading) {
    return <div className="marketing-plan-state" role="status"><span className="marketing-loader" />Loading available plans…</div>;
  }

  if (error) {
    return (
      <div className="marketing-plan-state marketing-plan-error" role="alert">
        <p>Plan information is temporarily unavailable.</p>
        <button type="button" className="marketing-retry" onClick={() => setAttempt((value) => value + 1)}>
          <RefreshCw size={14} /> Try again
        </button>
      </div>
    );
  }

  if (plans.length === 0) {
    return (
      <div className="marketing-plan-state">
        <strong>Plans are being prepared.</strong>
        <p>There are no published plans yet. Check back soon or create an account to explore the product.</p>
      </div>
    );
  }

  const visiblePlans = compact ? plans.slice(0, 3) : plans;

  return (
    <div className={`marketing-plan-grid ${compact ? "marketing-plan-grid-compact" : ""}`}>
      {visiblePlans.map((plan) => (
        <article className="marketing-plan-card" key={plan.id}>
          <div className="marketing-plan-topline">
            <span className="marketing-plan-label">Published plan</span>
            <span className="marketing-plan-check"><Check size={14} /></span>
          </div>
          <h3>{plan.name}</h3>
          {plan.description && <p className="marketing-plan-description">{plan.description}</p>}
          <div className="marketing-plan-price">
            <strong>{formatMoney(plan.monthly_price, plan.currency)}</strong>
            <span>/ month</span>
          </div>
          <div className="marketing-plan-details">
            <div><Clock3 size={16} /><span><strong>{Number(plan.included_minutes).toLocaleString()}</strong> included minutes</span></div>
            <div><Phone size={16} /><span>Up to <strong>{Number(plan.max_phone_numbers).toLocaleString()}</strong> {Number(plan.max_phone_numbers) === 1 ? "phone number" : "phone numbers"}</span></div>
          </div>
          <ul className="marketing-plan-includes" aria-label="Included product capabilities">
            <li><Check size={13} /> Inbound AI call answering</li>
            <li><Check size={13} /> Business-specific receptionist guidance</li>
            <li><Check size={13} /> Call history and usage tracking</li>
          </ul>
          <Link
            className="marketing-button marketing-button-outline"
            to={user ? "/dashboard" : "/register"}
          >
            {user ? "Open dashboard" : "Create an account"} <ArrowUpRight size={16} />
          </Link>
        </article>
      ))}
      {!compact && (
        <section className="marketing-plan-comparison" aria-labelledby="plan-comparison-title">
          <h3 id="plan-comparison-title">Compare published plans</h3>
          <div className="marketing-plan-comparison-wrap">
            <table aria-labelledby="plan-comparison-title">
              <thead>
                <tr>
                  <th scope="col">Plan detail</th>
                  {visiblePlans.map((plan) => <th scope="col" key={plan.id}>{plan.name}</th>)}
                </tr>
              </thead>
              <tbody>
                <tr>
                  <th scope="row">Monthly price</th>
                  {visiblePlans.map((plan) => <td key={plan.id}>{formatMoney(plan.monthly_price, plan.currency)}</td>)}
                </tr>
                <tr>
                  <th scope="row">Included minutes</th>
                  {visiblePlans.map((plan) => <td key={plan.id}>{Number(plan.included_minutes).toLocaleString()}</td>)}
                </tr>
                <tr>
                  <th scope="row">Maximum phone numbers</th>
                  {visiblePlans.map((plan) => <td key={plan.id}>{Number(plan.max_phone_numbers).toLocaleString()}</td>)}
                </tr>
                {[
                  "Inbound AI call answering",
                  "Business-specific receptionist guidance",
                  "Call history and usage tracking",
                ].map((feature) => (
                  <tr key={feature}>
                    <th scope="row">{feature}</th>
                    {visiblePlans.map((plan) => <td key={plan.id}><span className="marketing-feature-available"><Check size={14} /> Available</span></td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p>Product capabilities are shared across the current plans; configured minute and phone-number limits vary by plan.</p>
        </section>
      )}
    </div>
  );
}

function formatMoney(value, currency) {
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(Number(value));
  } catch {
    return `${currency} ${Number(value).toFixed(2)}`;
  }
}
