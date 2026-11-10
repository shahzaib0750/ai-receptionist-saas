import {
  ArrowDown,
  ArrowRight,
  AudioLines,
  BarChart3,
  Building2,
  CalendarClock,
  Check,
  ChevronDown,
  CircleCheck,
  Clock3,
  Headphones,
  MessageCircle,
  Phone,
  PhoneCall,
  Settings2,
  Sparkles,
  UsersRound,
} from "lucide-react";
import { Link } from "react-router-dom";
import { MarketingLayout } from "../components/marketing/MarketingLayout";
import { PlanCatalog } from "../components/marketing/PlanCatalog";

const activeFeatures = [
  {
    icon: Clock3,
    title: "Always-on call answering",
    description: "An AI receptionist is configured to answer inbound calls whenever your business is set up and active.",
  },
  {
    icon: AudioLines,
    title: "Natural voice conversations",
    description: "A voice assistant greets callers and responds using the business guidance you provide.",
  },
  {
    icon: Settings2,
    title: "Your business, your guidance",
    description: "Add business details and fallback instructions to shape how the receptionist handles common questions.",
  },
  {
    icon: PhoneCall,
    title: "Managed phone setup",
    description: "Set up an assistant and a local voice number through the guided onboarding flow.",
  },
  {
    icon: Phone,
    title: "Call history at a glance",
    description: "Review recorded calls and their available summaries from your private business workspace.",
  },
  {
    icon: BarChart3,
    title: "Usage you can track",
    description: "See finalized call minutes against the allowance configured for your subscription.",
  },
];

const comingSoonFeatures = [
  "Appointment scheduling",
  "Live call transfers",
  "Structured lead capture",
  "Multiple independent agents per business",
];

const useCases = [
  {
    icon: CircleCheck,
    name: "Healthcare & clinics",
    text: "Give callers a consistent first response to general questions, guided by the information your team provides.",
    note: "No patient-record or appointment-system integration.",
  },
  {
    icon: Building2,
    name: "Real estate",
    text: "Make sure inbound inquiries receive a prompt greeting, even when your team is with a client.",
    note: "No property search or lead-management integration.",
  },
  {
    icon: Settings2,
    name: "Home services",
    text: "Share the basics about your services and preferred caller guidance in your receptionist setup.",
    note: "No dispatch, quoting, or job-booking workflow.",
  },
  {
    icon: CalendarClock,
    name: "Salons & appointment-led teams",
    text: "Answer common inbound questions with the business details you configure.",
    note: "The receptionist does not book or change appointments.",
  },
  {
    icon: UsersRound,
    name: "Small & growing businesses",
    text: "Keep call answering and call history in one business workspace as your team grows.",
    note: "One managed receptionist setup per business today.",
  },
];

const steps = [
  {
    number: "01",
    title: "Customers call your business",
    description: "Provision a local voice number for the business through guided setup.",
    icon: Phone,
  },
  {
    number: "02",
    title: "Your AI receptionist answers",
    description: "Once activated, the voice assistant handles inbound calls with a natural greeting.",
    icon: AudioLines,
  },
  {
    number: "03",
    title: "It follows your business guidance",
    description: "Give it the context and fallback instructions it needs to respond consistently.",
    icon: MessageCircle,
  },
  {
    number: "04",
    title: "You review activity",
    description: "Use your dashboard to check call history, setup status, and metered usage.",
    icon: BarChart3,
  },
];

const faq = [
  {
    question: "How does the AI receptionist work?",
    answer: "You provide business details and receptionist guidance, then the platform configures a Vapi voice assistant and phone number. After you activate it, inbound calls are answered by that assistant.",
  },
  {
    question: "How is the phone number configured?",
    answer: "Guided onboarding provisions a local voice-enabled number and connects it to the assistant. Number availability, provider funding, and regional requirements apply. The number is not activated until you choose to activate the receptionist.",
  },
  {
    question: "Can it book appointments or transfer calls?",
    answer: "Not currently. Appointment booking, live call transfers, and CRM lead capture are not enabled in the product. The receptionist is configured for inbound answering and business-question guidance.",
  },
  {
    question: "Can I customize what it says?",
    answer: "You can provide your business details, a receptionist brief, and fallback guidance during setup. Voice and model choices are currently controlled by the platform configuration.",
  },
  {
    question: "What do included minutes mean?",
    answer: "Published billing plans show their configured monthly minute allowance. The platform records finalized call duration in seconds and rounds the period total up once to whole minutes. Inbound answering remains enabled if usage exceeds the allowance.",
  },
  {
    question: "Are subscriptions and payments available?",
    answer: "The product can display configured plans and track subscription-related records, but a live payment provider is not connected yet. Checkout, cancellation, and plan changes are unavailable until an actual provider integration is configured.",
  },
];

export function HomePage({ user }) {
  return (
    <MarketingLayout user={user}>
      <section className="marketing-hero">
        <div className="marketing-container marketing-hero-grid">
          <div className="marketing-hero-copy">
            <div className="marketing-eyebrow"><span className="marketing-eyebrow-dot" /> A more thoughtful way to answer</div>
            <h1>Your AI Receptionist.<br /><span>Always Ready.</span><br />Always Answering.</h1>
            <p className="marketing-hero-description">
              Give every caller a thoughtful, consistent first response—while your team focuses on the work in front of them.
            </p>
            <div className="marketing-hero-actions">
              <Link className="marketing-button" to={user ? "/dashboard" : "/register"}>
                {user ? "Go to dashboard" : "Get started"} <ArrowRight size={17} />
              </Link>
              <a className="marketing-button marketing-button-text" href="#pricing">
                Explore pricing <ArrowDown size={16} />
              </a>
            </div>
            <div className="marketing-hero-proof">
              <span><Check size={14} /> Guided phone setup</span>
              <span><Check size={14} /> Business-specific instructions</span>
            </div>
          </div>

          <div className="marketing-hero-visual" aria-label="Illustration of the Relay call dashboard">
            <div className="marketing-visual-orbit orbit-one" />
            <div className="marketing-visual-orbit orbit-two" />
            <div className="marketing-dashboard">
              <div className="marketing-dashboard-head">
                <div className="marketing-mini-brand"><span><Headphones size={14} /></span> relay</div>
                <span className="marketing-dashboard-period">Workspace overview <ChevronDown size={13} /></span>
              </div>
              <div className="marketing-dashboard-title">
                <div><small>MONDAY, YOUR WAY</small><h2>Good morning.</h2></div>
                <span className="marketing-dashboard-avatar">R</span>
              </div>
              <div className="marketing-call-status">
                <span className="marketing-call-status-icon"><PhoneCall size={17} /></span>
                <span><strong>Receptionist status</strong><small><i /> Ready for inbound calls</small></span>
                <span className="marketing-status-pill">Active</span>
              </div>
              <div className="marketing-dashboard-metrics">
                <div><span>Recent calls</span><strong><Phone size={16} /> Call history</strong><small>Available in your workspace</small></div>
                <div><span>Call usage</span><strong><Clock3 size={16} /> Usage tracking</strong><small>Based on finalized call reports</small></div>
              </div>
              <div className="marketing-live-card">
                <div className="marketing-live-card-head"><span><span className="marketing-live-dot" /> VOICE RECEPTIONIST</span><span>Illustration</span></div>
                <div className="marketing-voice-graphic">
                  <span className="marketing-voice-avatar"><AudioLines size={25} /></span>
                  <div className="marketing-waveform" aria-hidden="true">
                    {[12, 21, 31, 18, 38, 24, 14, 33, 22, 39, 19, 30, 12, 25, 16, 34, 20].map((height, index) => (
                      <i key={index} style={{ "--wave-height": `${height}px`, "--wave-delay": `${index * 35}ms` }} />
                    ))}
                  </div>
                  <span className="marketing-voice-spark"><Sparkles size={16} /></span>
                </div>
                <p>Business guidance, ready when callers need it.</p>
              </div>
              <div className="marketing-dashboard-foot"><span><span className="marketing-foot-check"><Check size={10} /></span> Your workspace, at a glance</span><span>RELAY</span></div>
            </div>
            <div className="marketing-float-note float-note-top"><span><AudioLines size={15} /></span><div><strong>Natural conversations</strong><small>Guided by your business</small></div></div>
            <div className="marketing-float-note float-note-bottom"><span><Clock3 size={15} /></span><div><strong>Always on</strong><small>Inbound call answering</small></div></div>
          </div>
        </div>
        <a className="marketing-scroll-cue" href="#how-it-works"><span /> See how it works</a>
      </section>

      <section className="marketing-section marketing-process-section" id="how-it-works">
        <div className="marketing-container">
          <div className="marketing-section-heading">
            <span className="marketing-kicker">Simple by design</span>
            <h2>A better first hello,<br /><span>from the first ring.</span></h2>
            <p>Set up your business once. Then give callers a clear, consistent place to start.</p>
          </div>
          <div className="marketing-steps">
            {steps.map(({ number, title, description, icon: Icon }) => (
              <article className="marketing-step" key={number}>
                <div className="marketing-step-top"><span>{number}</span><Icon size={20} /></div>
                <h3>{title}</h3>
                <p>{description}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="marketing-section marketing-feature-section" id="features">
        <div className="marketing-container">
          <div className="marketing-section-heading marketing-section-heading-row">
            <div><span className="marketing-kicker">Made for the calls that matter</span><h2>Thoughtful tools.<br /><span>Honest capabilities.</span></h2></div>
            <p>Built around reliable inbound answering, with your business context and call activity close at hand.</p>
          </div>
          <div className="marketing-feature-grid">
            {activeFeatures.map(({ icon: Icon, title, description }) => (
              <article className="marketing-feature-card" key={title}>
                <span className="marketing-feature-icon"><Icon size={19} /></span>
                <h3>{title}</h3>
                <p>{description}</p>
              </article>
            ))}
          </div>
          <div className="marketing-not-yet">
            <span className="marketing-not-yet-icon"><CalendarClock size={18} /></span>
            <div><strong>Not enabled yet</strong><p>{comingSoonFeatures.join(", ")} are not currently available.</p></div>
          </div>
        </div>
      </section>

      <section className="marketing-section marketing-usecase-section">
        <div className="marketing-container">
          <div className="marketing-section-heading">
            <span className="marketing-kicker">For teams that pick up the phone</span>
            <h2>One warmer welcome.<br /><span>Many kinds of business.</span></h2>
            <p>Use your own business details to guide how the receptionist responds to everyday inbound questions.</p>
          </div>
          <div className="marketing-usecase-grid">
            {useCases.map(({ icon: Icon, name, text, note }) => (
              <article className="marketing-usecase-card" key={name}>
                <Icon size={19} />
                <h3>{name}</h3>
                <p>{text}</p>
                <small>{note}</small>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="marketing-section marketing-pricing-section" id="pricing">
        <div className="marketing-container">
          <div className="marketing-section-heading marketing-section-heading-row">
            <div><span className="marketing-kicker">Clear, configured pricing</span><h2>The right plan for<br /><span>your call volume.</span></h2></div>
            <p>Plan names, prices, minute allowances, and phone limits come directly from the published billing catalog.</p>
          </div>
          <PlanCatalog compact user={user} />
          <div className="marketing-pricing-footnote"><i /> Plans are displayed as configured. Current onboarding supports one managed number per business; live checkout is not available.</div>
          <div className="marketing-pricing-link"><Link to="/pricing">See all plan details <ArrowRight size={15} /></Link></div>
        </div>
      </section>

      <section className="marketing-section marketing-faq-section" id="faq">
        <div className="marketing-container marketing-faq-layout">
          <div className="marketing-section-heading">
            <span className="marketing-kicker">Good questions</span>
            <h2>Before the<br /><span>first hello.</span></h2>
            <p>Here’s what Relay does today—and what it doesn’t.</p>
          </div>
          <div className="marketing-faq-list">
            {faq.map(({ question, answer }) => (
              <details key={question}>
                <summary>{question}<span><ChevronDown size={17} /></span></summary>
                <p>{answer}</p>
              </details>
            ))}
          </div>
        </div>
      </section>

      <section className="marketing-final-cta">
        <div className="marketing-container marketing-final-cta-inner">
          <div className="marketing-cta-decoration"><span /><span /><span /></div>
          <span className="marketing-kicker">Make every ring count</span>
          <h2>Never Miss Another<br />Business Call.</h2>
          <p>Start with a business workspace and see how a more thoughtful first response can fit your team.</p>
          <Link className="marketing-button marketing-button-light" to={user ? "/dashboard" : "/register"}>
            {user ? "Open your dashboard" : "Get started today"} <ArrowRight size={16} />
          </Link>
        </div>
      </section>
    </MarketingLayout>
  );
}
