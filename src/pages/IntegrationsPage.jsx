import { Fragment, jsx, jsxs } from "react/jsx-runtime";
import { Activity, Check, CircleHelp, Copy, ExternalLink, Link2, Phone, Save, Shield } from "lucide-react";
import { useEffect, useState } from "react";
import { useBusiness } from "../business/BusinessContext";
import { Button, Card, EmptyState, ErrorState, Field, LoadingState, PageHeader, StatusBadge } from "../components/ui";
import { ApiError, api, apiBaseUrl, userFacingErrorMessage } from "../lib/api";
function IntegrationsPage() {
  const { activeBusiness } = useBusiness();
  const [configuration, setConfiguration] = useState(null);
  const [notConfigured, setNotConfigured] = useState(false);
  const [assistantId, setAssistantId] = useState("");
  const [phoneNumberId, setPhoneNumberId] = useState("");
  const [isEnabled, setIsEnabled] = useState(true);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const webhookUrl = `${apiBaseUrl()}/integrations/vapi/webhook`;
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
    void api.vapi(activeBusiness.id).then((result) => {
      if (!active) return;
      setConfiguration(result);
      setAssistantId(result.assistant_id);
      setPhoneNumberId(result.phone_number_id ?? "");
      setIsEnabled(result.is_enabled);
    }).catch((cause) => {
      if (!active) return;
      if (cause instanceof ApiError && cause.status === 404) {
        setNotConfigured(true);
      } else {
        setError(userFacingErrorMessage(cause, "Could not load Vapi configuration."));
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
      const saved = configuration ? await api.updateVapi(activeBusiness.id, {
        assistant_id: assistantId.trim(),
        phone_number_id: phoneNumberId.trim() || null,
        is_enabled: isEnabled
      }) : await api.createVapi(activeBusiness.id, {
        assistant_id: assistantId.trim(),
        phone_number_id: phoneNumberId.trim() || null
      });
      setConfiguration(saved);
      setNotConfigured(false);
      setNotice("Vapi configuration saved.");
    } catch (cause) {
      setError(userFacingErrorMessage(cause, "Could not save Vapi configuration."));
    } finally {
      setBusy(false);
    }
  };
  const copyWebhook = async () => {
    try {
      await navigator.clipboard.writeText(webhookUrl);
      setNotice("Webhook URL copied.");
      setError("");
    } catch {
      setError("Could not copy the webhook URL. Select and copy it manually.");
    }
  };
  if (!activeBusiness) {
    return /* @__PURE__ */ jsxs("div", { className: "page-stack", children: [
      /* @__PURE__ */ jsx(PageHeader, { title: "Integrations", description: "Connect Vapi to your receptionist." }),
      /* @__PURE__ */ jsx(Card, { children: /* @__PURE__ */ jsx(EmptyState, { title: "Create a business first", description: "Integrations are configured per business workspace." }) })
    ] });
  }
  return /* @__PURE__ */ jsxs("div", { className: "page-stack", children: [
    /* @__PURE__ */ jsx(
      PageHeader,
      {
        eyebrow: activeBusiness.name,
        title: "Integrations",
        description: "Connect your existing Vapi assistant and phone number to this workspace."
      }
    ),
    error && /* @__PURE__ */ jsx(ErrorState, { message: error }),
    notice && /* @__PURE__ */ jsxs("div", { className: "success-banner", children: [
      /* @__PURE__ */ jsx(Check, { size: 16 }),
      " ",
      notice
    ] }),
    loading ? /* @__PURE__ */ jsx(Card, { children: /* @__PURE__ */ jsx(LoadingState, { label: "Loading integrations" }) }) : /* @__PURE__ */ jsxs(Fragment, { children: [
      /* @__PURE__ */ jsxs(Card, { className: "integration-card", children: [
        /* @__PURE__ */ jsxs("div", { className: "integration-card-head", children: [
          /* @__PURE__ */ jsx("span", { className: "integration-logo", children: "V" }),
          /* @__PURE__ */ jsxs("div", { className: "integration-title", children: [
            /* @__PURE__ */ jsxs("div", { className: "integration-name-line", children: [
              /* @__PURE__ */ jsx("h2", { children: "Vapi" }),
              configuration && /* @__PURE__ */ jsx(StatusBadge, { status: configuration.is_enabled ? "active" : "disabled" })
            ] }),
            /* @__PURE__ */ jsx("p", { children: "AI voice infrastructure" })
          ] }),
          !notConfigured && configuration && /* @__PURE__ */ jsxs("span", { className: "connected-label", children: [
            /* @__PURE__ */ jsx("span", {}),
            "Configured"
          ] })
        ] }),
        /* @__PURE__ */ jsx("div", { className: "integration-divider" }),
        /* @__PURE__ */ jsxs("div", { className: "integration-description", children: [
          /* @__PURE__ */ jsxs("div", { children: [
            /* @__PURE__ */ jsx("h3", { children: "Assistant mapping" }),
            /* @__PURE__ */ jsx("p", { children: "Link an assistant and optional phone number ID. This app does not provision numbers or create assistants." })
          ] }),
          configuration && /* @__PURE__ */ jsxs("label", { className: "toggle-label", children: [
            /* @__PURE__ */ jsx("span", { children: isEnabled ? "Enabled" : "Disabled" }),
            /* @__PURE__ */ jsx("input", { type: "checkbox", checked: isEnabled, onChange: (event) => setIsEnabled(event.target.checked), "aria-label": "Enable Vapi integration" }),
            /* @__PURE__ */ jsx("span", { className: "toggle-track" })
          ] })
        ] }),
        /* @__PURE__ */ jsxs("form", { className: "integration-form", onSubmit: (event) => void save(event), children: [
          /* @__PURE__ */ jsx(Field, { label: "Vapi assistant ID", id: "assistant-id", hint: "The ID of an existing assistant in your Vapi account.", children: /* @__PURE__ */ jsx("input", { id: "assistant-id", value: assistantId, onChange: (event) => setAssistantId(event.target.value), required: true, minLength: 1, maxLength: 255, placeholder: "e.g. assistant_\u2026" }) }),
          /* @__PURE__ */ jsx(Field, { label: "Phone number ID", id: "phone-number-id", hint: "Optional. Map a phone number already configured in Vapi.", children: /* @__PURE__ */ jsx("input", { id: "phone-number-id", value: phoneNumberId, onChange: (event) => setPhoneNumberId(event.target.value), maxLength: 255, placeholder: "e.g. number_\u2026" }) }),
          /* @__PURE__ */ jsx("div", { className: "form-actions", children: /* @__PURE__ */ jsxs(Button, { type: "submit", disabled: busy || !assistantId.trim(), children: [
            /* @__PURE__ */ jsx(Save, { size: 15 }),
            busy ? "Saving\u2026" : configuration ? "Save mapping" : "Connect Vapi"
          ] }) })
        ] })
      ] }),
      /* @__PURE__ */ jsxs("div", { className: "integration-lower-grid", children: [
        /* @__PURE__ */ jsxs(Card, { className: "webhook-card", children: [
          /* @__PURE__ */ jsxs("div", { className: "card-heading", children: [
            /* @__PURE__ */ jsxs("div", { children: [
              /* @__PURE__ */ jsx("h2", { children: "Webhook endpoint" }),
              /* @__PURE__ */ jsx("p", { children: "Set this URL in your Vapi Server URL configuration." })
            ] }),
            /* @__PURE__ */ jsx("span", { className: "section-icon", children: /* @__PURE__ */ jsx(Link2, { size: 17 }) })
          ] }),
          /* @__PURE__ */ jsxs("label", { className: "field", children: [
            /* @__PURE__ */ jsx("span", { children: "Webhook URL" }),
            /* @__PURE__ */ jsxs("span", { className: "copy-input", children: [
              /* @__PURE__ */ jsx("input", { readOnly: true, value: webhookUrl, "aria-label": "Vapi webhook URL" }),
              /* @__PURE__ */ jsx(Button, { type: "button", variant: "secondary", size: "sm", onClick: () => void copyWebhook(), "aria-label": "Copy webhook URL", children: /* @__PURE__ */ jsx(Copy, { size: 15 }) })
            ] })
          ] }),
          /* @__PURE__ */ jsxs("div", { className: "webhook-note", children: [
            /* @__PURE__ */ jsx(Shield, { size: 16 }),
            /* @__PURE__ */ jsx("span", { children: "Webhook authentication is managed by the backend. Do not enter API keys or secrets here." })
          ] }),
          /* @__PURE__ */ jsxs("a", { className: "docs-link", href: "https://docs.vapi.ai/server-url/server-authentication", target: "_blank", rel: "noreferrer", children: [
            "Vapi authentication setup ",
            /* @__PURE__ */ jsx(ExternalLink, { size: 14 })
          ] })
        ] }),
        /* @__PURE__ */ jsxs(Card, { className: "integration-state-card", children: [
          /* @__PURE__ */ jsx("span", { className: "integration-state-icon", children: /* @__PURE__ */ jsx(Activity, { size: 18 }) }),
          /* @__PURE__ */ jsx("h3", { children: configuration ? "Configuration saved" : "Connection not verified" }),
          /* @__PURE__ */ jsx("p", { children: configuration ? "Assistant and phone number identifiers are mapped. The backend does not currently verify the Vapi API connection." : "Save the assistant mapping to configure this workspace. The backend currently has no connection-test operation." }),
          /* @__PURE__ */ jsxs("div", { className: "integration-fact", children: [
            /* @__PURE__ */ jsxs("span", { children: [
              /* @__PURE__ */ jsx(Phone, { size: 14 }),
              " Phone provisioning"
            ] }),
            /* @__PURE__ */ jsx("strong", { children: "Not available" })
          ] }),
          /* @__PURE__ */ jsxs("div", { className: "integration-fact", children: [
            /* @__PURE__ */ jsxs("span", { children: [
              /* @__PURE__ */ jsx(CircleHelp, { size: 14 }),
              " API status check"
            ] }),
            /* @__PURE__ */ jsx("strong", { children: "Not available" })
          ] })
        ] })
      ] }),
      /* @__PURE__ */ jsxs("div", { className: "integration-footer-note", children: [
        /* @__PURE__ */ jsx(CircleHelp, { size: 15 }),
        " Attach a Vapi Custom Credential with an Authorization Bearer prefix to the effective Server URL configuration. The backend expects the matching VAPI_WEBHOOK_SECRET."
      ] })
    ] })
  ] });
}
export {
  IntegrationsPage
};
