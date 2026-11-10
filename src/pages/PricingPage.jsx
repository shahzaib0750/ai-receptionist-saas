import { ArrowRight, BadgeCheck, Clock3, Phone, ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";
import { MarketingLayout } from "../components/marketing/MarketingLayout";
import { PlanCatalog } from "../components/marketing/PlanCatalog";

export function PricingPage({ user }) {
  return (
    <MarketingLayout user={user} activePage="pricing">
      <section className="pricing-hero">
        <div className="marketing-container">
          <div className="marketing-eyebrow"><span className="marketing-eyebrow-dot" /> Pricing from the live catalog</div>
          <h1>Simple plans.<br /><span>Clear limits.</span></h1>
          <p>Compare the current plans published for Relay. Prices and included allowances are loaded directly from the billing catalog—not estimates.</p>
          <a className="pricing-scroll-link" href="#available-plans">Explore available plans <ArrowRight size={15} /></a>
        </div>
        <div className="pricing-hero-orb pricing-orb-one" />
        <div className="pricing-hero-orb pricing-orb-two" />
      </section>

      <section className="marketing-section pricing-catalog-section" id="available-plans">
        <div className="marketing-container">
          <div className="marketing-section-heading pricing-section-heading">
            <span className="marketing-kicker">Published plans</span>
            <h2>Choose what fits<br /><span>your business today.</span></h2>
            <p>Every listed value reflects the latest plan configuration available to visitors.</p>
          </div>
          <PlanCatalog user={user} />
          <div className="pricing-live-note">
            <span><ShieldCheck size={17} /></span>
            <p><strong>Transparent plan details.</strong> The catalog shows configured monthly prices, minute allowances, and phone-number limits. Current onboarding supports one managed number per business, even if a plan displays a higher limit.</p>
          </div>
          <div className="pricing-provider-notice">
            <span><BadgeCheck size={17} /></span>
            <p><strong>Payment provider status:</strong> live checkout, subscription changes, and payment processing are not currently available. Creating an account does not start a subscription or charge a payment method.</p>
          </div>
        </div>
      </section>

      <section className="marketing-section pricing-how-section">
        <div className="marketing-container pricing-how-grid">
          <div>
            <span className="marketing-kicker">What your plan covers</span>
            <h2>Know your allowance.<br /><span>Keep answering.</span></h2>
            <p>Finalized Vapi call duration is recorded as seconds. Usage is summed for the billing period, then rounded up once to a whole-minute total.</p>
          </div>
          <div className="pricing-usage-card">
            <div className="pricing-usage-icon"><Clock3 size={19} /></div>
            <div><strong>Minute allowance</strong><span>Based on the plan shown above</span></div>
            <ArrowRight size={16} />
          </div>
          <div className="pricing-usage-card">
            <div className="pricing-usage-icon"><Phone size={19} /></div>
            <div><strong>Phone number limit</strong><span>As configured for each plan</span></div>
            <ArrowRight size={16} />
          </div>
          <div className="pricing-usage-footnote">Inbound answering remains available even if recorded usage exceeds the included allowance. Overage billing is not implemented.</div>
        </div>
      </section>

      <section className="pricing-bottom-cta">
        <div className="marketing-container pricing-bottom-cta-inner">
          <div><span className="marketing-kicker">Ready to explore?</span><h2>Start with your business.</h2><p>Create an account to set up a workspace and explore the product. No payment is taken during signup.</p></div>
          <Link className="marketing-button" to={user ? "/dashboard" : "/register"}>
            {user ? "Open dashboard" : "Get started"} <ArrowRight size={16} />
          </Link>
        </div>
      </section>
    </MarketingLayout>
  );
}
