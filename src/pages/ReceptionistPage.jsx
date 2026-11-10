import { jsx, jsxs } from "react/jsx-runtime";
import { ArrowRight, AudioLines, Check, CircleHelp, Save, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useBusiness } from "../business/BusinessContext";
import { Button, Card, EmptyState, ErrorState, Field, LoadingState, PageHeader, StatusBadge } from "../components/ui";
import { ApiError, api, userFacingErrorMessage } from "../lib/api";
const timezones = [
  "UTC",
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "America/Toronto",
  "Europe/London",
  "Europe/Paris",
  "Asia/Dubai",
  "Asia/Karachi",
  "Asia/Kolkata",
  "Asia/Singapore",
  "Australia/Sydney"
];
function ReceptionistPage() {
  const { activeBusiness } = useBusiness();
  const [configuration, setConfiguration] = useState(null);
  const [notConfigured, setNotConfigured] = useState(false);
  const [assistantName, setAssistantName] = useState("");
  const [greeting, setGreeting] = useState("");
  const [timezone, setTimezone] = useState(Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC");
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  useEffect(() => {
    let active = true;
    setError("");
    setNotice("");
    setConfiguration(null);
    setNotConfigured(false);
    if (!activeBusiness) {
      setLoading(false);
      return () => {
        active = false;
      };
    }
    setLoading(true);
    void api.receptionist(activeBusiness.id).then((result) => {
      if (!active) return;
      setConfiguration(result);
      setAssistantName(result.assistant_name);
      setGreeting(result.greeting_message);
      setTimezone(result.business_timezone);
    }).catch((cause) => {
      if (!active) return;
      if (cause instanceof ApiError && cause.status === 404) {
        setNotConfigured(true);
        setAssistantName("Avery");
        setGreeting(`Thank you for calling ${activeBusiness.name}. How can I help you today?`);
      } else {
        setError(userFacingErrorMessage(cause, "Could not load receptionist configuration."));
      }
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => {
      active = false;
    };
  }, [activeBusiness]);
  const save = async (event) => {
    event.preventDefault();
    if (!activeBusiness) return;
    setError("");
    setNotice("");
    setBusy(true);
    try {
      const payload = {
        assistant_name: assistantName.trim(),
        greeting_message: greeting.trim(),
        business_timezone: timezone
      };
      const saved = configuration ? await api.updateReceptionist(activeBusiness.id, payload) : await api.createReceptionist(activeBusiness.id, payload);
      setConfiguration(saved);
      setNotConfigured(false);
      setNotice("Receptionist settings saved.");
    } catch (cause) {
      setError(userFacingErrorMessage(cause, "Could not save receptionist configuration."));
    } finally {
      setBusy(false);
    }
  };
  const toggleEnabled = async () => {
    if (!activeBusiness || !configuration) return;
    setError("");
    setNotice("");
    setBusy(true);
    try {
      const saved = await api.updateReceptionist(activeBusiness.id, {
        is_enabled: !configuration.is_enabled
      });
      setConfiguration(saved);
      setNotice(saved.is_enabled ? "Receptionist enabled." : "Receptionist disabled.");
    } catch (cause) {
      setError(userFacingErrorMessage(cause, "Could not update receptionist status."));
    } finally {
      setBusy(false);
    }
  };
  if (!activeBusiness) {
    return /* @__PURE__ */ jsxs("div", { className: "page-stack", children: [
      /* @__PURE__ */ jsx(PageHeader, { title: "AI receptionist", description: "Configure how your virtual front desk welcomes callers." }),
      /* @__PURE__ */ jsx(Card, { children: /* @__PURE__ */ jsx(EmptyState, { title: "Create a business first", description: "A receptionist belongs to a business workspace.", action: /* @__PURE__ */ jsxs(Link, { className: "button button-primary", to: "/businesses", children: [
        "Go to businesses ",
        /* @__PURE__ */ jsx(ArrowRight, { size: 15 })
      ] }) }) })
    ] });
  }
  return /* @__PURE__ */ jsxs("div", { className: "page-stack", children: [
    /* @__PURE__ */ jsx(
      PageHeader,
      {
        eyebrow: activeBusiness.name,
        title: "AI receptionist",
        description: "Set the voice, greeting, and local timezone for your virtual front desk.",
        action: configuration && /* @__PURE__ */ jsx(StatusBadge, { status: configuration.is_enabled ? "active" : "disabled" })
      }
    ),
    /* @__PURE__ */ jsxs("div", { className: "setup-progress", children: [
      /* @__PURE__ */ jsxs("div", { className: "setup-progress-step complete", children: [
        /* @__PURE__ */ jsx("span", { children: /* @__PURE__ */ jsx(Check, { size: 14 }) }),
        /* @__PURE__ */ jsxs("div", { children: [
          /* @__PURE__ */ jsx("strong", { children: "Business" }),
          /* @__PURE__ */ jsx("small", { children: "Workspace created" })
        ] })
      ] }),
      /* @__PURE__ */ jsx("div", { className: "setup-progress-line" }),
      /* @__PURE__ */ jsxs("div", { className: `setup-progress-step ${configuration ? "complete" : "current"}`, children: [
        /* @__PURE__ */ jsx("span", { children: configuration ? /* @__PURE__ */ jsx(Check, { size: 14 }) : "2" }),
        /* @__PURE__ */ jsxs("div", { children: [
          /* @__PURE__ */ jsx("strong", { children: "Receptionist" }),
          /* @__PURE__ */ jsx("small", { children: "Greeting & timezone" })
        ] })
      ] }),
      /* @__PURE__ */ jsx("div", { className: "setup-progress-line" }),
      /* @__PURE__ */ jsxs("div", { className: `setup-progress-step ${configuration ? "current" : ""}`, children: [
        /* @__PURE__ */ jsx("span", { children: "3" }),
        /* @__PURE__ */ jsxs("div", { children: [
          /* @__PURE__ */ jsx("strong", { children: "Vapi connection" }),
          /* @__PURE__ */ jsx("small", { children: "Assistant & number" })
        ] })
      ] }),
      /* @__PURE__ */ jsxs(Link, { to: "/onboarding", className: "setup-progress-link", children: [
        "Configure Vapi ",
        /* @__PURE__ */ jsx(ArrowRight, { size: 14 })
      ] })
    ] }),
    error && /* @__PURE__ */ jsx(ErrorState, { message: error }),
    notice && /* @__PURE__ */ jsxs("div", { className: "success-banner", children: [
      /* @__PURE__ */ jsx(Check, { size: 16 }),
      " ",
      notice
    ] }),
    loading ? /* @__PURE__ */ jsx(Card, { children: /* @__PURE__ */ jsx(LoadingState, { label: "Loading receptionist settings" }) }) : notConfigured || configuration ? /* @__PURE__ */ jsxs("div", { className: "receptionist-layout", children: [
      /* @__PURE__ */ jsxs(Card, { className: "receptionist-editor", children: [
        /* @__PURE__ */ jsxs("div", { className: "card-heading", children: [
          /* @__PURE__ */ jsxs("div", { children: [
            /* @__PURE__ */ jsx("h2", { children: "General settings" }),
            /* @__PURE__ */ jsxs("p", { children: [
              "These details are stored for ",
              activeBusiness.name,
              "."
            ] })
          ] }),
          /* @__PURE__ */ jsx("span", { className: "section-icon", children: /* @__PURE__ */ jsx(AudioLines, { size: 17 }) })
        ] }),
        /* @__PURE__ */ jsxs("form", { className: "settings-form", onSubmit: (event) => void save(event), children: [
          /* @__PURE__ */ jsx(Field, { label: "Receptionist name", id: "assistant-name", hint: "This name identifies your assistant in the workspace.", children: /* @__PURE__ */ jsx("input", { id: "assistant-name", value: assistantName, onChange: (event) => setAssistantName(event.target.value), required: true, minLength: 1, maxLength: 120 }) }),
          /* @__PURE__ */ jsxs(Field, { label: "Greeting", id: "greeting", hint: "The opening greeting saved for this receptionist.", children: [
            /* @__PURE__ */ jsx("textarea", { id: "greeting", rows: 4, value: greeting, onChange: (event) => setGreeting(event.target.value), required: true, minLength: 1, maxLength: 2e3 }),
            /* @__PURE__ */ jsxs("span", { className: "textarea-count", children: [
              greeting.length,
              "/2000"
            ] })
          ] }),
          /* @__PURE__ */ jsx(Field, { label: "Business timezone", id: "business-timezone", hint: "Used as the receptionist\u2019s business timezone.", children: /* @__PURE__ */ jsxs("select", { id: "business-timezone", value: timezone, onChange: (event) => setTimezone(event.target.value), children: [
            !timezones.includes(timezone) && /* @__PURE__ */ jsx("option", { value: timezone, children: timezone }),
            timezones.map((value) => /* @__PURE__ */ jsx("option", { value, children: value.replaceAll("_", " ") }, value))
          ] }) }),
          /* @__PURE__ */ jsxs("div", { className: "form-actions", children: [
            configuration && /* @__PURE__ */ jsx(Button, { type: "button", variant: "secondary", onClick: toggleEnabled, disabled: busy, children: configuration.is_enabled ? "Disable receptionist" : "Enable receptionist" }),
            /* @__PURE__ */ jsxs(Button, { type: "submit", disabled: busy || !assistantName.trim() || !greeting.trim(), children: [
              /* @__PURE__ */ jsx(Save, { size: 15 }),
              busy ? "Saving\u2026" : configuration ? "Save changes" : "Save receptionist"
            ] })
          ] })
        ] })
      ] }),
      /* @__PURE__ */ jsxs("div", { className: "receptionist-side", children: [
        /* @__PURE__ */ jsxs(Card, { className: "setup-aside-card", children: [
          /* @__PURE__ */ jsx("div", { className: "setup-aside-icon", children: /* @__PURE__ */ jsx(ShieldCheck, { size: 19 }) }),
          /* @__PURE__ */ jsx("h3", { children: "Good to know" }),
          /* @__PURE__ */ jsx("p", { children: "This backend currently stores the assistant name, greeting, timezone, and enabled state. Voice, services, FAQs, hours, and appointment actions are not configured here." })
        ] }),
        /* @__PURE__ */ jsxs(Card, { className: "setup-aside-card vapi-next-card", children: [
          /* @__PURE__ */ jsx("span", { className: "eyebrow", children: "Next step" }),
          /* @__PURE__ */ jsx("h3", { children: "Connect your Vapi assistant" }),
          /* @__PURE__ */ jsx("p", { children: "Map an existing assistant and optional phone number ID to this business." }),
          /* @__PURE__ */ jsxs(Link, { to: "/onboarding", className: "text-link", children: [
            "Open integrations ",
            /* @__PURE__ */ jsx(ArrowRight, { size: 14 })
          ] })
        ] }),
        /* @__PURE__ */ jsxs("div", { className: "privacy-note", children: [
          /* @__PURE__ */ jsx(CircleHelp, { size: 15 }),
          " No API keys or webhook secrets are requested or stored in this interface."
        ] })
      ] })
    ] }) : null
  ] });
}
export {
  ReceptionistPage
};
