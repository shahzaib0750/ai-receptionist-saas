import { Fragment, jsx, jsxs } from "react/jsx-runtime";
import { ArrowDown, ArrowRight, ArrowUp, CalendarDays, ChevronDown, Phone, Search, X } from "lucide-react";
import { useEffect, useState } from "react";
import { useBusiness } from "../business/BusinessContext";
import { Button, Card, EmptyState, ErrorState, LoadingState, PageHeader, StatusBadge } from "../components/ui";
import { ApiError, api, userFacingErrorMessage } from "../lib/api";
import { formatDate, formatDuration } from "../lib/callFormatting";
const STATUSES = ["scheduled", "queued", "ringing", "in-progress", "forwarding", "ended"];
const PAGE_SIZE = 25;
function CallsPage() {
  const { activeBusiness } = useBusiness();
  const [page, setPage] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [forbidden, setForbidden] = useState(false);
  const [status, setStatus] = useState("");
  const [callerInput, setCallerInput] = useState("");
  const [caller, setCaller] = useState("");
  const [afterInput, setAfterInput] = useState("");
  const [beforeInput, setBeforeInput] = useState("");
  const [createdAfter, setCreatedAfter] = useState("");
  const [createdBefore, setCreatedBefore] = useState("");
  const [offset, setOffset] = useState(0);
  const [selectedId, setSelectedId] = useState(null);
  const [details, setDetails] = useState(null);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [detailsError, setDetailsError] = useState("");
  const [sortOrder, setSortOrder] = useState("desc");
  useEffect(() => {
    let active = true;
    if (!activeBusiness) {
      setPage(null);
      setLoading(false);
      return () => {
        active = false;
      };
    }
    setLoading(true);
    setError("");
    setForbidden(false);
    void api.calls(activeBusiness.id, {
      limit: PAGE_SIZE,
      offset,
      status,
      caller,
      created_after: createdAfter || void 0,
      created_before: createdBefore || void 0,
      sort_by: "created_at",
      sort_order: sortOrder
    }).then((result) => {
      if (active) setPage(result);
    }).catch((cause) => {
      if (active) {
        setForbidden(cause instanceof ApiError && cause.status === 403);
        setError(userFacingErrorMessage(cause, "Could not load calls."));
      }
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => {
      active = false;
    };
  }, [activeBusiness, status, caller, createdAfter, createdBefore, offset, sortOrder]);
  useEffect(() => {
    let active = true;
    setDetails(null);
    setDetailsError("");
    if (!activeBusiness || !selectedId) {
      setDetailsLoading(false);
      return () => {
        active = false;
      };
    }
    setDetailsLoading(true);
    void api.call(activeBusiness.id, selectedId).then((result) => {
      if (active) setDetails(result);
    }).catch((cause) => {
      if (active) {
        setDetailsError(userFacingErrorMessage(cause, "Could not load call details."));
      }
    }).finally(() => {
      if (active) setDetailsLoading(false);
    });
    return () => {
      active = false;
    };
  }, [activeBusiness, selectedId]);
  const applyFilters = (event) => {
    event.preventDefault();
    if (afterInput && beforeInput && afterInput > beforeInput) {
      setError("The end date must be on or after the start date.");
      return;
    }
    setError("");
    setOffset(0);
    setCaller(callerInput.trim());
    setCreatedAfter(afterInput ? (/* @__PURE__ */ new Date(`${afterInput}T00:00:00Z`)).toISOString() : "");
    setCreatedBefore(beforeInput ? (/* @__PURE__ */ new Date(`${beforeInput}T23:59:59.999Z`)).toISOString() : "");
  };
  const clearFilters = () => {
    setStatus("");
    setCallerInput("");
    setCaller("");
    setAfterInput("");
    setBeforeInput("");
    setCreatedAfter("");
    setCreatedBefore("");
    setOffset(0);
  };
  const sortByDate = () => {
    setOffset(0);
    setSortOrder((order) => order === "desc" ? "asc" : "desc");
  };
  const rows = page?.items ?? [];
  const from = (page?.total ?? 0) === 0 ? 0 : offset + 1;
  const to = Math.min(offset + rows.length, page?.total ?? 0);
  return /* @__PURE__ */ jsxs("div", { className: "page-stack", children: [
    /* @__PURE__ */ jsx(
      PageHeader,
      {
        eyebrow: activeBusiness?.name ?? "Workspace",
        title: "Call history",
        description: "Review calls received by your Vapi assistant."
      }
    ),
    error && !forbidden && /* @__PURE__ */ jsx(ErrorState, { message: error }),
    /* @__PURE__ */ jsxs(Card, { className: "call-history-card", children: [
      /* @__PURE__ */ jsxs("form", { className: "call-filters", onSubmit: applyFilters, children: [
        /* @__PURE__ */ jsxs("label", { className: "search-field", children: [
          /* @__PURE__ */ jsx(Search, { size: 16, "aria-hidden": "true" }),
          /* @__PURE__ */ jsx("span", { className: "sr-only", children: "Search caller number" }),
          /* @__PURE__ */ jsx(
            "input",
            {
              value: callerInput,
              onChange: (event) => setCallerInput(event.target.value),
              placeholder: "Search caller number",
              maxLength: 64
            }
          )
        ] }),
        /* @__PURE__ */ jsxs("label", { className: "filter-select", children: [
          /* @__PURE__ */ jsx("span", { className: "sr-only", children: "Filter by status" }),
          /* @__PURE__ */ jsxs("select", { value: status, onChange: (event) => {
            setStatus(event.target.value);
            setOffset(0);
          }, children: [
            /* @__PURE__ */ jsx("option", { value: "", children: "All statuses" }),
            STATUSES.map((value) => /* @__PURE__ */ jsx("option", { value, children: value.replaceAll("-", " ") }, value))
          ] }),
          /* @__PURE__ */ jsx(ChevronDown, { size: 14 })
        ] }),
        /* @__PURE__ */ jsxs("label", { className: "filter-date", children: [
          /* @__PURE__ */ jsx(CalendarDays, { size: 15 }),
          /* @__PURE__ */ jsx("span", { className: "sr-only", children: "From date" }),
          /* @__PURE__ */ jsx("input", { type: "date", value: afterInput, onChange: (event) => setAfterInput(event.target.value) })
        ] }),
        /* @__PURE__ */ jsx("span", { className: "date-range-divider", children: "to" }),
        /* @__PURE__ */ jsxs("label", { className: "filter-date", children: [
          /* @__PURE__ */ jsx("span", { className: "sr-only", children: "To date" }),
          /* @__PURE__ */ jsx("input", { type: "date", value: beforeInput, onChange: (event) => setBeforeInput(event.target.value) })
        ] }),
        /* @__PURE__ */ jsx(Button, { type: "submit", variant: "secondary", size: "sm", children: "Apply" }),
        (caller || status || createdAfter || createdBefore) && /* @__PURE__ */ jsxs(Button, { type: "button", variant: "ghost", size: "sm", onClick: clearFilters, children: [
          /* @__PURE__ */ jsx(X, { size: 14 }),
          "Clear"
        ] })
      ] }),
      loading ? /* @__PURE__ */ jsx("div", { className: "table-state", children: /* @__PURE__ */ jsx(LoadingState, { label: "Loading call history" }) }) : forbidden ? /* @__PURE__ */ jsx(
        "div",
        { className: "permission-card call-permission", children: [
          /* @__PURE__ */ jsx("div", { className: "permission-icon", children: /* @__PURE__ */ jsx(Phone, { size: 20 }) }),
          /* @__PURE__ */ jsx("h2", { children: "Call history is restricted" }),
          /* @__PURE__ */ jsx("p", { children: "Only business owners and admins can view caller details and transcripts." })
        ] }
      ) : rows.length === 0 ? /* @__PURE__ */ jsx(
        EmptyState,
        {
          title: caller || status || createdAfter || createdBefore ? "No calls match these filters" : "No calls yet",
          description: caller || status || createdAfter || createdBefore ? "Try changing the filters or date range." : "Calls will appear here after your Vapi assistant receives them.",
          action: caller || status || createdAfter || createdBefore ? /* @__PURE__ */ jsx(Button, { variant: "secondary", onClick: clearFilters, children: "Clear filters" }) : void 0
        }
      ) : /* @__PURE__ */ jsxs(Fragment, { children: [
        /* @__PURE__ */ jsx("div", { className: "table-scroll", children: /* @__PURE__ */ jsxs("table", { className: "data-table call-table", children: [
          /* @__PURE__ */ jsx("thead", { children: /* @__PURE__ */ jsxs("tr", { children: [
            /* @__PURE__ */ jsx("th", { children: "Caller" }),
            /* @__PURE__ */ jsx("th", { children: "Direction" }),
            /* @__PURE__ */ jsx("th", { children: "Status" }),
            /* @__PURE__ */ jsx("th", { children: "Duration" }),
            /* @__PURE__ */ jsx("th", { children: /* @__PURE__ */ jsxs("button", { className: "sort-button", onClick: sortByDate, type: "button", children: [
              "Date ",
              sortOrder === "desc" ? /* @__PURE__ */ jsx(ArrowDown, { size: 13 }) : /* @__PURE__ */ jsx(ArrowUp, { size: 13 })
            ] }) }),
            /* @__PURE__ */ jsx("th", { children: /* @__PURE__ */ jsx("span", { className: "sr-only", children: "Details" }) })
          ] }) }),
          /* @__PURE__ */ jsx("tbody", { children: rows.map((call) => /* @__PURE__ */ jsx(CallRow, { call, onClick: () => setSelectedId(call.id) }, call.id)) })
        ] }) }),
        /* @__PURE__ */ jsxs("div", { className: "table-pagination", children: [
          /* @__PURE__ */ jsxs("span", { children: [
            "Showing ",
            /* @__PURE__ */ jsxs("strong", { children: [
              from,
              "\u2013",
              to
            ] }),
            " of ",
            /* @__PURE__ */ jsx("strong", { children: page?.total ?? 0 }),
            " calls"
          ] }),
          /* @__PURE__ */ jsxs("div", { children: [
            /* @__PURE__ */ jsx(Button, { variant: "secondary", size: "sm", onClick: () => setOffset(Math.max(0, offset - PAGE_SIZE)), disabled: offset === 0, children: "Previous" }),
            /* @__PURE__ */ jsx(Button, { variant: "secondary", size: "sm", onClick: () => setOffset(offset + PAGE_SIZE), disabled: offset + rows.length >= (page?.total ?? 0), children: "Next" })
          ] })
        ] })
      ] })
    ] }),
    selectedId && /* @__PURE__ */ jsx("div", { className: "dialog-backdrop", role: "presentation", onMouseDown: (event) => {
      if (event.target === event.currentTarget) setSelectedId(null);
    }, children: /* @__PURE__ */ jsxs("section", { className: "call-detail-panel", role: "dialog", "aria-modal": "true", "aria-labelledby": "call-detail-title", children: [
      /* @__PURE__ */ jsxs("div", { className: "call-detail-header", children: [
        /* @__PURE__ */ jsxs("div", { children: [
          /* @__PURE__ */ jsx("span", { className: "eyebrow", children: "Call details" }),
          /* @__PURE__ */ jsx("h2", { id: "call-detail-title", children: details?.caller_number ?? "Unknown caller" }),
          /* @__PURE__ */ jsx("p", { className: "mono", children: details?.vapi_call_id ?? selectedId })
        ] }),
        /* @__PURE__ */ jsx("button", { className: "icon-button", "aria-label": "Close call details", onClick: () => setSelectedId(null), children: /* @__PURE__ */ jsx(X, { size: 19 }) })
      ] }),
      detailsError && /* @__PURE__ */ jsx(ErrorState, { message: detailsError }),
      detailsLoading ? /* @__PURE__ */ jsx(LoadingState, { label: "Loading call details" }) : details && /* @__PURE__ */ jsx(CallDetailsContent, { details })
    ] }) })
  ] });
}
function CallRow({ call, onClick }) {
  return /* @__PURE__ */ jsxs("tr", { className: "clickable-row", onClick, children: [
    /* @__PURE__ */ jsx("td", { children: /* @__PURE__ */ jsxs("span", { className: "caller-cell", children: [
      /* @__PURE__ */ jsx("span", { className: "caller-avatar", children: call.caller_number?.slice(-2) ?? /* @__PURE__ */ jsx(Phone, { size: 15 }) }),
      /* @__PURE__ */ jsxs("span", { children: [
        /* @__PURE__ */ jsx("strong", { children: call.caller_number ?? "Unknown caller" }),
        /* @__PURE__ */ jsx("small", { children: call.vapi_call_id })
      ] })
    ] }) }),
    /* @__PURE__ */ jsx("td", { className: "capitalize", children: call.direction ?? "\u2014" }),
    /* @__PURE__ */ jsx("td", { children: /* @__PURE__ */ jsx(StatusBadge, { status: call.status }) }),
    /* @__PURE__ */ jsx("td", { children: formatDuration(call.duration_seconds) }),
    /* @__PURE__ */ jsx("td", { children: formatDate(call.started_at ?? call.created_at) }),
    /* @__PURE__ */ jsx("td", { children: /* @__PURE__ */ jsx("button", { className: "table-arrow", "aria-label": `View call ${call.vapi_call_id}`, onClick, children: /* @__PURE__ */ jsx(ArrowRight, { size: 15 }) }) })
  ] });
}
function CallDetailsContent({ details }) {
  return /* @__PURE__ */ jsxs("div", { className: "call-details-content", children: [
    /* @__PURE__ */ jsxs("div", { className: "call-detail-summary", children: [
      /* @__PURE__ */ jsxs("div", { children: [
        /* @__PURE__ */ jsx("span", { children: "Status" }),
        /* @__PURE__ */ jsx(StatusBadge, { status: details.status })
      ] }),
      /* @__PURE__ */ jsxs("div", { children: [
        /* @__PURE__ */ jsx("span", { children: "Duration" }),
        /* @__PURE__ */ jsx("strong", { children: formatDuration(details.duration_seconds) })
      ] }),
      /* @__PURE__ */ jsxs("div", { children: [
        /* @__PURE__ */ jsx("span", { children: "Direction" }),
        /* @__PURE__ */ jsx("strong", { className: "capitalize", children: details.direction ?? "\u2014" })
      ] })
    ] }),
    /* @__PURE__ */ jsxs("div", { className: "detail-list call-meta-list", children: [
      /* @__PURE__ */ jsx(Detail, { label: "Caller", value: details.caller_number ?? "Not provided" }),
      /* @__PURE__ */ jsx(Detail, { label: "Called number", value: details.recipient_number ?? "Not provided" }),
      /* @__PURE__ */ jsx(Detail, { label: "Started", value: details.started_at ? new Date(details.started_at).toLocaleString() : "Not provided" }),
      /* @__PURE__ */ jsx(Detail, { label: "Ended", value: details.ended_at ? new Date(details.ended_at).toLocaleString() : "Not provided" }),
      /* @__PURE__ */ jsx(Detail, { label: "End reason", value: details.ended_reason ?? "Not provided" }),
      /* @__PURE__ */ jsx(Detail, { label: "Assistant ID", value: details.assistant_id, mono: true })
    ] }),
    /* @__PURE__ */ jsxs("div", { className: "call-detail-section", children: [
      /* @__PURE__ */ jsx("h3", { children: "Transcript" }),
      details.transcript ? /* @__PURE__ */ jsx("pre", { className: "transcript-box", children: details.transcript }) : /* @__PURE__ */ jsx("p", { className: "unavailable-copy", children: "No transcript was provided for this call." })
    ] }),
    /* @__PURE__ */ jsxs("div", { className: "call-detail-section", children: [
      /* @__PURE__ */ jsx("h3", { children: "Recording" }),
      details.recording_url ? /* @__PURE__ */ jsxs("a", { className: "recording-link", href: details.recording_url, target: "_blank", rel: "noreferrer", children: [
        "Open recording ",
        /* @__PURE__ */ jsx(ArrowRight, { size: 14 })
      ] }) : /* @__PURE__ */ jsx("p", { className: "unavailable-copy", children: "No recording URL was provided for this call." })
    ] })
  ] });
}
function Detail({ label, value, mono = false }) {
  return /* @__PURE__ */ jsxs("div", { className: "detail-row", children: [
    /* @__PURE__ */ jsx("span", { children: label }),
    /* @__PURE__ */ jsx("strong", { className: mono ? "mono" : "", children: value })
  ] });
}
export {
  CallsPage
};
