import { Fragment, jsx, jsxs } from "react/jsx-runtime";
import {
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  AudioLines,
  Building2,
  Clock3,
  Phone,
  Plus
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { useBusiness } from "../business/BusinessContext";
import { Button, Card, EmptyState, ErrorState, LoadingState, PageHeader, StatusBadge } from "../components/ui";
import { ApiError, api, userFacingErrorMessage } from "../lib/api";
import { formatDate, formatDuration } from "../lib/callFormatting";
function DashboardPage() {
  const { user } = useAuth();
  const { businesses, activeBusiness, refreshBusinesses } = useBusiness();
  const navigate = useNavigate();
  const [calls, setCalls] = useState([]);
  const [callTotal, setCallTotal] = useState(null);
  const [receptionist, setReceptionist] = useState(null);
  const [setup, setSetup] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [callsForbidden, setCallsForbidden] = useState(false);
  useEffect(() => {
    let active = true;
    if (!activeBusiness) {
      setCalls([]);
      setCallTotal(null);
      setReceptionist(null);
      setSetup(null);
      setLoading(false);
      return () => {
        active = false;
      };
    }
    setLoading(true);
    setError(null);
    const businessId = activeBusiness.id;
    void Promise.allSettled([
      api.calls(businessId, { limit: 6 }),
      api.receptionist(businessId),
      api.onboarding(businessId)
    ]).then(([callsResult, receptionResult, vapiResult]) => {
      if (!active) return;
      if (callsResult.status === "fulfilled") {
        setCalls(callsResult.value.items);
        setCallTotal(callsResult.value.total);
        setCallsForbidden(false);
      } else {
        setCalls([]);
        setCallTotal(null);
        const restricted = callsResult.reason instanceof ApiError && callsResult.reason.status === 403;
        setCallsForbidden(restricted);
      }
      setReceptionist(receptionResult.status === "fulfilled" ? receptionResult.value : null);
      setSetup(vapiResult.status === "fulfilled" ? vapiResult.value : null);
      const failures = [];
      if (callsResult.status === "rejected" && !(callsResult.reason instanceof ApiError && callsResult.reason.status === 403)) {
        failures.push(userFacingErrorMessage(callsResult.reason, "Call history is unavailable."));
      }
      if (receptionResult.status === "rejected") {
        failures.push(userFacingErrorMessage(receptionResult.reason, "Receptionist settings are unavailable."));
      }
      if (vapiResult.status === "rejected") {
        failures.push(userFacingErrorMessage(vapiResult.reason, "Setup status is unavailable."));
      }
      if (failures.length > 0) setError(failures.join(" "));
      setLoading(false);
    });
    return () => {
      active = false;
    };
  }, [activeBusiness]);
  const duration = calls.reduce((sum, call) => sum + (call.duration_seconds ?? 0), 0);
  const ended = calls.filter((call) => call.status === "ended").length;
  const ready = setup?.status === "ready" || setup?.status === "active";
  const statusText = setup?.status === "active"
    ? "Active — answering inbound calls"
    : setup?.status === "ready"
      ? "Ready to activate"
      : setup?.status === "setup_in_progress"
        ? "Setup in progress"
        : setup?.status === "failed"
          ? "Setup failed — retry available"
          : "Setup needs attention";
  const firstName = user?.full_name.split(/\s+/)[0] ?? "there";
  return /* @__PURE__ */ jsxs("div", { className: "page-stack", children: [
    /* @__PURE__ */ jsx(
      PageHeader,
      {
        eyebrow: "Workspace overview",
        title: `Good ${getGreeting()}, ${firstName}`,
        description: "A clear picture of what\u2019s happening with your receptionist.",
        action: /* @__PURE__ */ jsxs(Button, { onClick: () => navigate(businesses.length ? "/onboarding" : "/businesses"), children: [
          /* @__PURE__ */ jsx(Plus, { size: 16 }),
          businesses.length ? "Set up receptionist" : "Add a business"
        ] })
      }
    ),
    businesses.length === 0 ? /* @__PURE__ */ jsxs(Card, { className: "welcome-card", children: [
      /* @__PURE__ */ jsxs("div", { className: "welcome-copy", children: [
        /* @__PURE__ */ jsxs("span", { className: "welcome-kicker", children: [
          /* @__PURE__ */ jsx(AudioLines, { size: 15 }),
          " Let\u2019s get started"
        ] }),
        /* @__PURE__ */ jsx("h2", { children: "Your first hello starts here." }),
        /* @__PURE__ */ jsx("p", { children: "Create a business workspace, tell us how you help callers, and we\u2019ll configure the receptionist and phone setup." }),
        /* @__PURE__ */ jsxs(Button, { onClick: () => navigate("/businesses"), children: [
          "Create your business ",
          /* @__PURE__ */ jsx(ArrowRight, { size: 16 })
        ] })
      ] }),
      /* @__PURE__ */ jsxs("div", { className: "welcome-graphic", children: [
        /* @__PURE__ */ jsx("div", { className: "welcome-circle", children: /* @__PURE__ */ jsx(Phone, { size: 29 }) }),
        /* @__PURE__ */ jsx("span", { className: "welcome-line line-one" }),
        /* @__PURE__ */ jsx("span", { className: "welcome-line line-two" })
      ] })
    ] }) : /* @__PURE__ */ jsxs(Fragment, { children: [
      error && !callsForbidden && /* @__PURE__ */ jsx(ErrorState, { message: error, onRetry: () => void refreshBusinesses() }),
      /* @__PURE__ */ jsxs("div", { className: "dashboard-status-strip", children: [
        /* @__PURE__ */ jsxs("div", { className: `assistant-status ${ready ? "assistant-ready" : ""}`, children: [
          /* @__PURE__ */ jsx("span", { className: "assistant-status-dot" }),
          /* @__PURE__ */ jsxs("div", { children: [
            /* @__PURE__ */ jsx("strong", { children: receptionist?.assistant_name ?? "Receptionist setup" }),
            /* @__PURE__ */ jsx("span", { children: statusText })
          ] })
        ] }),
        /* @__PURE__ */ jsxs("div", { className: "setup-checks", children: [
          /* @__PURE__ */ jsxs("span", { className: receptionist && setup?.requirements_text ? "setup-check complete" : "setup-check", children: [
            /* @__PURE__ */ jsx("span", { className: "check-mark", children: receptionist && setup?.requirements_text ? "\u2713" : "1" }),
            " Business details"
          ] }),
          /* @__PURE__ */ jsx("span", { className: "setup-connector" }),
          /* @__PURE__ */ jsxs("span", { className: setup?.phone_number ? "setup-check complete" : "setup-check", children: [
            /* @__PURE__ */ jsx("span", { className: "check-mark", children: setup?.phone_number ? "\u2713" : "2" }),
            " Phone number"
          ] })
        ] }),
        !ready && /* @__PURE__ */ jsxs(Link, { to: "/onboarding", className: "text-link", children: [
          "Continue setup ",
          /* @__PURE__ */ jsx(ArrowRight, { size: 14 })
        ] })
      ] }),
      /* @__PURE__ */ jsxs("div", { className: "section-heading-row", children: [
        /* @__PURE__ */ jsxs("div", { children: [
          /* @__PURE__ */ jsx("h2", { className: "section-title", children: "Call activity" }),
          /* @__PURE__ */ jsx("p", { className: "section-subtitle", children: "A snapshot of your most recent calls" })
        ] }),
        /* @__PURE__ */ jsxs("span", { className: "period-label", children: [
          /* @__PURE__ */ jsx(Clock3, { size: 14 }),
          " Recent activity"
        ] })
      ] }),
      /* @__PURE__ */ jsxs("div", { className: "metric-grid", children: [
        /* @__PURE__ */ jsx(
          MetricCard,
          {
            label: "Total calls",
            value: loading ? "\u2014" : callTotal === null ? "\u2014" : callTotal.toLocaleString(),
            footnote: "All recorded calls",
            icon: /* @__PURE__ */ jsx(Phone, { size: 17 }),
            trendIcon: /* @__PURE__ */ jsx(ArrowUpRight, { size: 14 })
          }
        ),
        /* @__PURE__ */ jsx(
          MetricCard,
          {
            label: "Ended calls",
            value: loading || callsForbidden ? "\u2014" : String(ended),
            footnote: callsForbidden ? "Access restricted" : "In the latest 6 calls",
            icon: /* @__PURE__ */ jsx(AudioLines, { size: 17 }),
            trendIcon: /* @__PURE__ */ jsx(ArrowUpRight, { size: 14 })
          }
        ),
        /* @__PURE__ */ jsx(
          MetricCard,
          {
            label: "Call minutes",
            value: loading || callsForbidden ? "\u2014" : duration ? (duration / 60).toFixed(1) : "0",
            footnote: callsForbidden ? "Access restricted" : "In the latest 6 calls",
            icon: /* @__PURE__ */ jsx(Clock3, { size: 17 }),
            trendIcon: /* @__PURE__ */ jsx(ArrowDownRight, { size: 14 })
          }
        ),
        /* @__PURE__ */ jsx(
          MetricCard,
          {
            label: "Business",
            value: activeBusiness?.name ?? "\u2014",
            footnote: `${businesses.length} ${businesses.length === 1 ? "workspace" : "workspaces"}`,
            icon: /* @__PURE__ */ jsx(Building2, { size: 17 }),
            compact: true
          }
        )
      ] }),
      /* @__PURE__ */ jsxs(Card, { className: "calls-card", children: [
        /* @__PURE__ */ jsxs("div", { className: "card-heading", children: [
          /* @__PURE__ */ jsxs("div", { children: [
            /* @__PURE__ */ jsx("h2", { children: "Recent calls" }),
            /* @__PURE__ */ jsxs("p", { children: [
              "Latest activity for ",
              activeBusiness?.name
            ] })
          ] }),
          /* @__PURE__ */ jsxs(Link, { to: "/calls", className: "text-link", children: [
            "View call history ",
            /* @__PURE__ */ jsx(ArrowRight, { size: 14 })
          ] })
        ] }),
        loading ? /* @__PURE__ */ jsx(LoadingState, { label: "Loading recent calls" }) : callsForbidden ? /* @__PURE__ */ jsx(
          EmptyState,
          {
            title: "Call data is restricted",
            description: "Only business owners and admins can view call history."
          }
        ) : calls.length === 0 ? /* @__PURE__ */ jsx(
          EmptyState,
          {
            title: "No calls recorded yet",
            description: "After your receptionist is active and starts answering calls, they\u2019ll show up here.",
            action: /* @__PURE__ */ jsx(Button, { variant: "secondary", onClick: () => navigate("/onboarding"), children: "Review setup" })
          }
        ) : /* @__PURE__ */ jsx(CallRows, { calls: calls.slice(0, 5) })
      ] })
    ] }),
    /* @__PURE__ */ jsxs("div", { className: "dashboard-footer-note", children: [
      /* @__PURE__ */ jsx("span", { className: "footer-note-icon", children: /* @__PURE__ */ jsx(Clock3, { size: 14 }) }),
      "Metrics reflect the latest data returned by your API. Usage limits and billing are not configured."
    ] })
  ] });
}
function getGreeting() {
  const hour = (/* @__PURE__ */ new Date()).getHours();
  return hour < 12 ? "morning" : hour < 18 ? "afternoon" : "evening";
}
function MetricCard({
  label,
  value,
  footnote,
  icon,
  trendIcon,
  compact = false
}) {
  return /* @__PURE__ */ jsxs(Card, { className: "metric-card", children: [
    /* @__PURE__ */ jsxs("div", { className: "metric-top", children: [
      /* @__PURE__ */ jsx("span", { className: "metric-label", children: label }),
      /* @__PURE__ */ jsx("span", { className: "metric-icon", children: icon })
    ] }),
    /* @__PURE__ */ jsx("div", { className: `metric-value ${compact ? "metric-value-compact" : ""}`, children: value }),
    /* @__PURE__ */ jsxs("div", { className: "metric-footnote", children: [
      trendIcon && /* @__PURE__ */ jsx("span", { className: "metric-trend", children: trendIcon }),
      footnote
    ] })
  ] });
}
function CallRows({ calls }) {
  return /* @__PURE__ */ jsx("div", { className: "table-scroll", children: /* @__PURE__ */ jsxs("table", { className: "data-table", children: [
    /* @__PURE__ */ jsx("thead", { children: /* @__PURE__ */ jsxs("tr", { children: [
      /* @__PURE__ */ jsx("th", { children: "Caller" }),
      /* @__PURE__ */ jsx("th", { children: "Direction" }),
      /* @__PURE__ */ jsx("th", { children: "Status" }),
      /* @__PURE__ */ jsx("th", { children: "Duration" }),
      /* @__PURE__ */ jsx("th", { children: "Date" })
    ] }) }),
    /* @__PURE__ */ jsx("tbody", { children: calls.map((call) => /* @__PURE__ */ jsxs("tr", { children: [
      /* @__PURE__ */ jsx("td", { children: /* @__PURE__ */ jsxs("span", { className: "caller-cell", children: [
        /* @__PURE__ */ jsx("span", { className: "caller-avatar", children: call.caller_number?.slice(-2) ?? "\u2014" }),
        /* @__PURE__ */ jsxs("span", { children: [
          /* @__PURE__ */ jsx("strong", { children: call.caller_number ?? "Unknown caller" }),
          /* @__PURE__ */ jsx("small", { children: call.vapi_call_id })
        ] })
      ] }) }),
      /* @__PURE__ */ jsx("td", { className: "capitalize", children: call.direction ?? "\u2014" }),
      /* @__PURE__ */ jsx("td", { children: /* @__PURE__ */ jsx(StatusBadge, { status: call.status }) }),
      /* @__PURE__ */ jsx("td", { children: formatDuration(call.duration_seconds) }),
      /* @__PURE__ */ jsx("td", { children: formatDate(call.started_at ?? call.created_at) })
    ] }, call.id)) })
  ] }) });
}
export {
  DashboardPage
};
