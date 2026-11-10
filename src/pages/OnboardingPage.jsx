import { useEffect, useState } from "react";
import { ArrowRight, AudioLines, Check, LoaderCircle, Phone } from "lucide-react";
import { Link } from "react-router-dom";
import { useBusiness } from "../business/BusinessContext";
import { Button, Card, EmptyState, ErrorState, Field, LoadingState, PageHeader, StatusBadge } from "../components/ui";
import { api, userFacingErrorMessage } from "../lib/api";

const initialForm = (business) => ({
  name: business?.name ?? "",
  assistant_name: business?.name ? `${business.name} Receptionist` : "",
  greeting_message: business?.name
    ? `Thank you for calling ${business.name}. How can I help you today?`
    : "",
  industry: "",
  description: "",
  website: "",
  address: "",
  business_hours: "",
  contact_phone: "",
  contact_email: "",
  country_code: "US",
  requirements_text: "",
  fallback_instructions: "If you cannot answer, say so plainly and do not invent an answer.",
  selected_services: ["call_answering"],
  business_timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
});

function OnboardingPage() {
  const { activeBusiness } = useBusiness();
  const [form, setForm] = useState(() => initialForm(activeBusiness));
  const [setup, setSetup] = useState(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [phoneConsent, setPhoneConsent] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    let active = true;
    setError("");
    setNotice("");
    setSetup(null);
    setPhoneConsent(false);
    if (!activeBusiness) {
      setForm(initialForm(null));
      setLoading(false);
      return () => {
        active = false;
      };
    }

    setLoading(true);
    void api.onboarding(activeBusiness.id).then((result) => {
      if (!active) return;
      setSetup(result);
      setPhoneConsent(Boolean(result.phone_number_consent_given));
      if (result.status === "failed") {
        setError(result.error_message || "Setup failed. Retry or contact support.");
      }
      setForm({
        ...initialForm(activeBusiness),
        ...result,
        assistant_name: result.assistant_name || `${result.name} Receptionist`,
        greeting_message: result.greeting_message
          || `Thank you for calling ${result.name}. How can I help you today?`,
        country_code: result.country_code || "US",
        selected_services: result.selected_services?.length
          ? result.selected_services
          : ["call_answering"],
      });
    }).catch((cause) => {
      if (active) setError(userFacingErrorMessage(cause, "Could not load onboarding."));
    }).finally(() => {
      if (active) setLoading(false);
    });

    return () => {
      active = false;
    };
  }, [activeBusiness]);

  const update = (field) => (event) => {
    setForm((current) => ({ ...current, [field]: event.target.value }));
  };

  const save = async () => {
    if (!activeBusiness) return null;
    const saved = await api.saveOnboarding(activeBusiness.id, {
      ...form,
      contact_email: form.contact_email.trim() || null,
      website: form.website.trim() || null,
      industry: form.industry.trim() || null,
      description: form.description.trim() || null,
      address: form.address.trim() || null,
      business_hours: form.business_hours.trim() || null,
      contact_phone: form.contact_phone.trim() || null,
      assistant_name: form.assistant_name.trim() || null,
      greeting_message: form.greeting_message.trim() || null,
      requirements_text: form.requirements_text.trim() || null,
      fallback_instructions: form.fallback_instructions.trim() || null,
    });
    setSetup(saved);
    setForm((current) => ({ ...current, ...saved }));
    return saved;
  };

  const saveDraft = async (event) => {
    event.preventDefault();
    setError("");
    setNotice("");
    setBusy(true);
    try {
      await save();
      setNotice("Your business details were saved.");
    } catch (cause) {
      setError(userFacingErrorMessage(cause, "Could not save your onboarding."));
    } finally {
      setBusy(false);
    }
  };

  const provision = async () => {
    if (!activeBusiness) return;
    setError("");
    setNotice("");
    setBusy(true);
    try {
      await save();
      const result = await api.provisionReceptionist(activeBusiness.id, phoneConsent);
      setSetup(result);
      if (result.status === "failed") {
        setError(result.error_message || "Setup failed. Retry or contact support.");
      } else {
        setNotice("Your receptionist and phone number are configured. Review the setup, then activate it.");
      }
    } catch (cause) {
      setError(userFacingErrorMessage(cause, "Could not start receptionist setup."));
    } finally {
      setBusy(false);
    }
  };

  const activate = async () => {
    if (!activeBusiness) return;
    setError("");
    setNotice("");
    setBusy(true);
    try {
      const result = await api.activateReceptionist(activeBusiness.id);
      setSetup(result);
      setNotice("Your AI receptionist is active and ready to answer calls.");
    } catch (cause) {
      setError(userFacingErrorMessage(cause, "Could not activate the receptionist."));
    } finally {
      setBusy(false);
    }
  };

  if (!activeBusiness) {
    return (
      <div className="page-stack">
        <PageHeader title="Business onboarding" description="Create a business workspace before setting up a receptionist." />
        <Card>
          <EmptyState
            title="Create a business first"
            description="Each business has its own receptionist, phone number, and call history."
            action={<Link className="button button-primary" to="/businesses">Go to businesses <ArrowRight size={15} /></Link>}
          />
        </Card>
      </div>
    );
  }

  if (loading) {
    return <Card><LoadingState label="Loading business setup" /></Card>;
  }

  const statusLabel = setup?.status === "setup_in_progress" ? "Setup in progress" : setup?.status;

  return (
    <div className="page-stack onboarding-page">
      <PageHeader
        eyebrow={activeBusiness.name}
        title="Set up your AI receptionist"
        description="Tell us about your business and what callers need. We handle the voice and phone setup."
        action={setup?.status && <StatusBadge status={statusLabel} />}
      />
      {error && <ErrorState message={error} />}
      {notice && <div className="success-banner"><Check size={16} /> {notice}</div>}

      <form className="onboarding-form" onSubmit={(event) => void saveDraft(event)}>
        <Card className="onboarding-section">
          <div className="onboarding-step-heading">
            <span className="onboarding-step-number">1</span>
            <div>
              <h2>About your business</h2>
              <p>Share the details callers are most likely to ask about. You can leave optional information for later.</p>
            </div>
          </div>
          <div className="onboarding-grid">
            <Field label="Business name" id="onboarding-name">
              <input id="onboarding-name" value={form.name} onChange={update("name")} maxLength={200} required />
            </Field>
            <Field label="Industry or category" id="onboarding-industry">
              <input id="onboarding-industry" value={form.industry || ""} onChange={update("industry")} maxLength={120} placeholder="e.g. Dental clinic" />
            </Field>
            <Field label="Business description" id="onboarding-description">
              <textarea id="onboarding-description" value={form.description || ""} onChange={update("description")} maxLength={4000} placeholder="What do you offer?" />
            </Field>
            <Field label="Country for your business number" id="onboarding-country" hint="A local voice-enabled number will be requested from the platform phone provider. Country availability and regulations apply.">
              <input id="onboarding-country" value={form.country_code} onChange={(event) => setForm((current) => ({ ...current, country_code: event.target.value.toUpperCase() }))} minLength={2} maxLength={2} pattern="[A-Za-z]{2}" required />
            </Field>
          </div>
          <details className="onboarding-optional">
            <summary>Optional details</summary>
            <div className="onboarding-grid">
              <Field label="Receptionist name" id="onboarding-assistant-name">
                <input id="onboarding-assistant-name" value={form.assistant_name} onChange={update("assistant_name")} maxLength={120} />
              </Field>
              <Field label="Opening greeting" id="onboarding-greeting">
                <textarea id="onboarding-greeting" value={form.greeting_message} onChange={update("greeting_message")} maxLength={2000} />
              </Field>
              <Field label="Website" id="onboarding-website">
                <input id="onboarding-website" type="url" value={form.website || ""} onChange={update("website")} maxLength={2048} placeholder="https://" />
              </Field>
              <Field label="Business address" id="onboarding-address">
                <input id="onboarding-address" value={form.address || ""} onChange={update("address")} maxLength={1000} />
              </Field>
              <Field label="Business hours" id="onboarding-hours" hint="Example: Monday–Friday, 9am–5pm">
                <input id="onboarding-hours" value={form.business_hours || ""} onChange={update("business_hours")} maxLength={2000} />
              </Field>
              <Field label="Contact phone" id="onboarding-phone">
                <input id="onboarding-phone" type="tel" value={form.contact_phone || ""} onChange={update("contact_phone")} maxLength={64} />
              </Field>
              <Field label="Contact email" id="onboarding-email">
                <input id="onboarding-email" type="email" value={form.contact_email || ""} onChange={update("contact_email")} maxLength={320} />
              </Field>
              <Field label="Business timezone" id="onboarding-timezone">
                <input id="onboarding-timezone" value={form.business_timezone} onChange={update("business_timezone")} maxLength={64} required />
              </Field>
            </div>
          </details>
        </Card>

        <Card className="onboarding-section">
          <div className="onboarding-step-heading">
            <span className="onboarding-step-number">2</span>
            <div>
              <h2>Tell us what callers need</h2>
              <p>In your own words, describe why you need a receptionist, what callers ask, and what should happen when it cannot help.</p>
            </div>
          </div>
          <Field label="Your receptionist brief" id="onboarding-requirements" hint="This becomes part of the receptionist's business-specific instructions. Do not include private customer information.">
            <textarea
              id="onboarding-requirements"
              value={form.requirements_text || ""}
              onChange={update("requirements_text")}
              maxLength={5000}
              rows={6}
              placeholder="For example: We miss calls after hours. Callers ask about our services and opening times. If you are unsure, explain that the team will follow up."
            />
          </Field>
          <Field label="If it cannot answer, what should it do?" id="onboarding-fallback">
            <textarea id="onboarding-fallback" value={form.fallback_instructions || ""} onChange={update("fallback_instructions")} maxLength={2000} rows={3} />
          </Field>
          <div className="service-selection">
            <div className="service-card service-card-selected">
              <span className="service-icon"><Phone size={18} /></span>
              <span>
                <strong>AI call answering</strong>
                <small>Answer inbound calls and respond using the business details you provide.</small>
              </span>
              <span className="service-supported"><Check size={14} /> Available</span>
            </div>
            <p className="field-hint">Appointment booking, call transfer, and CRM lead capture are not currently supported and are not offered as active services.</p>
          </div>
        </Card>

        {setup?.phone_number && (
          <Card className="provisioning-result">
            <div className="provisioning-result-icon"><AudioLines size={19} /></div>
            <div>
              <h2>{setup.status === "active" ? "Receptionist is active" : "Your phone number is assigned"}</h2>
              <p>{setup.phone_number}</p>
            </div>
            <StatusBadge status={statusLabel} />
          </Card>
        )}

        <div className="onboarding-actions">
          <div className="onboarding-consent">
            <label>
              <input
                type="checkbox"
                checked={phoneConsent}
                onChange={(event) => setPhoneConsent(event.target.checked)}
              />
              <span>I authorize the platform to provision a business phone number. Carrier availability and charges apply.</span>
            </label>
            <small>Vapi and carrier setup are managed by the platform. Regional regulatory requirements may affect setup time.</small>
          </div>
          <div className="form-actions">
            <Button type="submit" variant="secondary" disabled={busy}>{busy ? "Saving…" : "Save for later"}</Button>
            {setup?.status === "ready" ? (
              <Button type="button" onClick={() => void activate()} disabled={busy}>
                {busy ? "Activating…" : "Activate receptionist"}
              </Button>
            ) : (
              <Button type="button" onClick={() => void provision()} disabled={busy || setup?.status === "active" || !phoneConsent}>
                {busy ? <><LoaderCircle size={15} className="spin" /> Setting up…</> : setup?.status === "failed" || setup?.status === "setup_in_progress" ? "Retry or check setup" : setup?.status === "active" ? "Active" : "Save and set up"}
              </Button>
            )}
          </div>
        </div>
      </form>
    </div>
  );
}

export { OnboardingPage };
