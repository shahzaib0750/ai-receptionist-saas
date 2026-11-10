import { jsx, jsxs } from "react/jsx-runtime";
import { AlertCircle, LoaderCircle, SearchX } from "lucide-react";
function Button({
  variant = "primary",
  size = "md",
  className = "",
  ...props
}) {
  return /* @__PURE__ */ jsx(
    "button",
    {
      className: `button button-${variant} button-${size} ${className}`.trim(),
      ...props
    }
  );
}
function PageHeader({
  eyebrow,
  title,
  description,
  action
}) {
  return /* @__PURE__ */ jsxs("header", { className: "page-header", children: [
    /* @__PURE__ */ jsxs("div", { children: [
      eyebrow && /* @__PURE__ */ jsx("div", { className: "eyebrow", children: eyebrow }),
      /* @__PURE__ */ jsx("h1", { children: title }),
      description && /* @__PURE__ */ jsx("p", { className: "page-description", children: description })
    ] }),
    action && /* @__PURE__ */ jsx("div", { className: "page-header-action", children: action })
  ] });
}
function Card({
  children,
  className = ""
}) {
  return /* @__PURE__ */ jsx("section", { className: `surface ${className}`.trim(), children });
}
function LoadingState({ label = "Loading" }) {
  return /* @__PURE__ */ jsxs("div", { className: "state-block", role: "status", children: [
    /* @__PURE__ */ jsx(LoaderCircle, { className: "spin", size: 20, "aria-hidden": "true" }),
    /* @__PURE__ */ jsx("span", { children: label })
  ] });
}
function ErrorState({
  message,
  onRetry
}) {
  return /* @__PURE__ */ jsxs("div", { className: "inline-error", role: "alert", children: [
    /* @__PURE__ */ jsx(AlertCircle, { size: 18, "aria-hidden": "true" }),
    /* @__PURE__ */ jsx("span", { children: message }),
    onRetry && /* @__PURE__ */ jsx(Button, { variant: "ghost", size: "sm", onClick: onRetry, children: "Try again" })
  ] });
}
function EmptyState({
  title,
  description,
  action
}) {
  return /* @__PURE__ */ jsxs("div", { className: "empty-state", children: [
    /* @__PURE__ */ jsx("div", { className: "empty-icon", children: /* @__PURE__ */ jsx(SearchX, { size: 21, "aria-hidden": "true" }) }),
    /* @__PURE__ */ jsx("h3", { children: title }),
    /* @__PURE__ */ jsx("p", { children: description }),
    action
  ] });
}
function Field({
  label,
  hint,
  error,
  id,
  children
}) {
  return /* @__PURE__ */ jsxs("div", { className: "field", children: [
    /* @__PURE__ */ jsx("label", { htmlFor: id, children: label }),
    children,
    error ? /* @__PURE__ */ jsx("span", { className: "field-error", role: "alert", children: error }) : hint && /* @__PURE__ */ jsx("span", { className: "field-hint", children: hint })
  ] });
}
function StatusBadge({ status }) {
  const tone = status === "ended" || status === "active" || status === "owner" ? "success" : status === "in-progress" || status === "forwarding" ? "info" : status === "disabled" || status === "failed" ? "muted" : "warning";
  return /* @__PURE__ */ jsxs("span", { className: `status-badge status-${tone}`, children: [
    /* @__PURE__ */ jsx("span", { className: "status-dot" }),
    status.replaceAll("-", " ")
  ] });
}
export {
  Button,
  Card,
  EmptyState,
  ErrorState,
  Field,
  LoadingState,
  PageHeader,
  StatusBadge
};
