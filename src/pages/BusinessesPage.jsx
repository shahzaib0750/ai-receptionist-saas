import { Fragment, jsx, jsxs } from "react/jsx-runtime";
import { ArrowRight, AudioLines, Building2, Check, ChevronRight, Phone, Plus, Save, UsersRound, X } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { useBusiness } from "../business/BusinessContext";
import { Button, Card, EmptyState, ErrorState, Field, PageHeader } from "../components/ui";
import { api, userFacingErrorMessage } from "../lib/api";
function BusinessesPage() {
  const { user } = useAuth();
  const {
    businesses,
    activeBusiness,
    activeBusinessId,
    selectBusiness,
    refreshBusinesses
  } = useBusiness();
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const createBusiness = async (event) => {
    event.preventDefault();
    setError("");
    setNotice("");
    setBusy(true);
    try {
      const business = await api.createBusiness(newName.trim());
      const refreshed = await refreshBusinesses(business.id);
      if (!refreshed?.some((item) => item.id === business.id)) {
        setError("Business created, but the workspace list could not be refreshed. Try again.");
        return;
      }
      setNewName("");
      setCreating(false);
      navigate("/onboarding");
    } catch (cause) {
      setError(userFacingErrorMessage(cause, "Could not create business."));
    } finally {
      setBusy(false);
    }
  };
  const saveBusiness = async (event) => {
    event.preventDefault();
    if (!activeBusiness) return;
    setError("");
    setNotice("");
    setBusy(true);
    try {
      await api.updateBusiness(activeBusiness.id, editName.trim());
      const refreshed = await refreshBusinesses();
      if (!refreshed) {
        setError("Business name saved, but the workspace list could not be refreshed. Try again.");
        return;
      }
      setEditing(false);
      setNotice("Business details saved.");
    } catch (cause) {
      setError(userFacingErrorMessage(cause, "Could not save business."));
    } finally {
      setBusy(false);
    }
  };
  return /* @__PURE__ */ jsxs("div", { className: "page-stack", children: [
    /* @__PURE__ */ jsx(
      PageHeader,
      {
        eyebrow: "Workspace",
        title: "Businesses",
        description: "Manage the business workspaces connected to your account.",
        action: /* @__PURE__ */ jsxs(Button, { onClick: () => {
          setCreating(true);
          setError("");
        }, children: [
          /* @__PURE__ */ jsx(Plus, { size: 16 }),
          " Add business"
        ] })
      }
    ),
    error && /* @__PURE__ */ jsx(ErrorState, { message: error }),
    notice && /* @__PURE__ */ jsxs("div", { className: "success-banner", children: [
      /* @__PURE__ */ jsx(Check, { size: 16 }),
      " ",
      notice
    ] }),
    creating && /* @__PURE__ */ jsxs(Card, { className: "form-card", children: [
      /* @__PURE__ */ jsxs("div", { className: "card-heading", children: [
        /* @__PURE__ */ jsxs("div", { children: [
          /* @__PURE__ */ jsx("h2", { children: "Create a business" }),
          /* @__PURE__ */ jsx("p", { children: "Start a workspace for your receptionist." })
        ] }),
        /* @__PURE__ */ jsx("button", { className: "icon-button", "aria-label": "Cancel", onClick: () => setCreating(false), children: /* @__PURE__ */ jsx(X, { size: 17 }) })
      ] }),
      /* @__PURE__ */ jsxs("form", { className: "inline-form", onSubmit: (event) => void createBusiness(event), children: [
        /* @__PURE__ */ jsx(Field, { label: "Business name", id: "new-business-name", hint: "You can update the name later.", children: /* @__PURE__ */ jsx(
          "input",
          {
            id: "new-business-name",
            value: newName,
            onChange: (event) => setNewName(event.target.value),
            maxLength: 200,
            required: true,
            placeholder: "e.g. Northstar Dental",
            autoFocus: true
          }
        ) }),
        /* @__PURE__ */ jsxs("div", { className: "form-actions", children: [
          /* @__PURE__ */ jsx(Button, { variant: "secondary", type: "button", onClick: () => setCreating(false), children: "Cancel" }),
          /* @__PURE__ */ jsx(Button, { type: "submit", disabled: busy || !newName.trim(), children: busy ? "Creating\u2026" : "Create workspace" })
        ] })
      ] })
    ] }),
    businesses.length === 0 && !creating ? /* @__PURE__ */ jsx(Card, { children: /* @__PURE__ */ jsx(
      EmptyState,
      {
        title: "No businesses yet",
        description: "Create your first workspace to configure a receptionist and start receiving call data.",
        action: /* @__PURE__ */ jsxs(Button, { onClick: () => setCreating(true), children: [
          /* @__PURE__ */ jsx(Plus, { size: 16 }),
          " Create a business"
        ] })
      }
    ) }) : /* @__PURE__ */ jsxs("div", { className: "business-page-grid", children: [
      /* @__PURE__ */ jsxs(Card, { className: "business-list-card", children: [
        /* @__PURE__ */ jsx("div", { className: "card-heading", children: /* @__PURE__ */ jsxs("div", { children: [
          /* @__PURE__ */ jsx("h2", { children: "Your workspaces" }),
          /* @__PURE__ */ jsxs("p", { children: [
            businesses.length,
            " ",
            businesses.length === 1 ? "business" : "businesses"
          ] })
        ] }) }),
        /* @__PURE__ */ jsx("div", { className: "business-list", children: businesses.map((business) => /* @__PURE__ */ jsxs(
          "button",
          {
            type: "button",
            className: `business-list-item ${business.id === activeBusinessId ? "business-list-item-active" : ""}`,
            onClick: () => {
              selectBusiness(business.id);
              setEditing(false);
            },
            children: [
              /* @__PURE__ */ jsx("span", { className: "business-icon", children: /* @__PURE__ */ jsx(Building2, { size: 18 }) }),
              /* @__PURE__ */ jsxs("span", { className: "business-item-copy", children: [
                /* @__PURE__ */ jsx("strong", { children: business.name }),
                /* @__PURE__ */ jsx("small", { children: business.owner_user_id === user?.id ? "Owner" : "Team workspace" })
              ] }),
              business.id === activeBusinessId ? /* @__PURE__ */ jsx("span", { className: "selected-mark", children: /* @__PURE__ */ jsx(Check, { size: 15 }) }) : /* @__PURE__ */ jsx(ChevronRight, { size: 16, className: "muted-icon" })
            ]
          },
          business.id
        )) })
      ] }),
      activeBusiness && /* @__PURE__ */ jsxs(Card, { className: "business-detail-card", children: [
        /* @__PURE__ */ jsxs("div", { className: "business-detail-head", children: [
          /* @__PURE__ */ jsx("span", { className: "business-icon large", children: /* @__PURE__ */ jsx(Building2, { size: 21 }) }),
          /* @__PURE__ */ jsxs("div", { children: [
            /* @__PURE__ */ jsx("div", { className: "eyebrow", children: "Business workspace" }),
            /* @__PURE__ */ jsx("h2", { children: activeBusiness.name })
          ] })
        ] }),
        editing ? /* @__PURE__ */ jsxs("form", { className: "settings-form", onSubmit: (event) => void saveBusiness(event), children: [
          /* @__PURE__ */ jsx(Field, { label: "Business name", id: "business-name", children: /* @__PURE__ */ jsx("input", { id: "business-name", value: editName, onChange: (event) => setEditName(event.target.value), maxLength: 200, required: true, autoFocus: true }) }),
          /* @__PURE__ */ jsxs("div", { className: "form-actions", children: [
            /* @__PURE__ */ jsx(Button, { type: "button", variant: "secondary", onClick: () => setEditing(false), children: "Cancel" }),
            /* @__PURE__ */ jsxs(Button, { type: "submit", disabled: busy || !editName.trim(), children: [
              /* @__PURE__ */ jsx(Save, { size: 15 }),
              busy ? "Saving\u2026" : "Save changes"
            ] })
          ] })
        ] }) : /* @__PURE__ */ jsxs(Fragment, { children: [
          /* @__PURE__ */ jsxs("div", { className: "detail-list", children: [
            /* @__PURE__ */ jsx(Detail, { label: "Business name", value: activeBusiness.name }),
            /* @__PURE__ */ jsx(Detail, { label: "Workspace ID", value: activeBusiness.id, mono: true }),
            /* @__PURE__ */ jsx(Detail, { label: "Created", value: new Date(activeBusiness.created_at).toLocaleDateString() }),
            /* @__PURE__ */ jsx(Detail, { label: "Your role", value: activeBusiness.owner_user_id === user?.id ? "Owner" : "Member" })
          ] }),
          /* @__PURE__ */ jsxs("div", { className: "business-quick-links", children: [
            /* @__PURE__ */ jsxs("button", { onClick: () => navigate("/onboarding"), children: [
              /* @__PURE__ */ jsxs("span", { children: [
                /* @__PURE__ */ jsx("span", { className: "quick-link-icon", children: /* @__PURE__ */ jsx(AudioLines, { size: 15 }) }),
                "AI receptionist"
              ] }),
              /* @__PURE__ */ jsx(ArrowRight, { size: 15 })
            ] }),
            /* @__PURE__ */ jsxs("button", { onClick: () => navigate("/onboarding"), children: [
              /* @__PURE__ */ jsxs("span", { children: [
                /* @__PURE__ */ jsx("span", { className: "quick-link-icon", children: /* @__PURE__ */ jsx(Phone, { size: 15 }) }),
                "Receptionist setup"
              ] }),
              /* @__PURE__ */ jsx(ArrowRight, { size: 15 })
            ] }),
            /* @__PURE__ */ jsxs("button", { onClick: () => navigate("/team"), children: [
              /* @__PURE__ */ jsxs("span", { children: [
                /* @__PURE__ */ jsx("span", { className: "quick-link-icon", children: /* @__PURE__ */ jsx(UsersRound, { size: 15 }) }),
                "Team members"
              ] }),
              /* @__PURE__ */ jsx(ArrowRight, { size: 15 })
            ] })
          ] }),
          /* @__PURE__ */ jsx(
            Button,
            {
              variant: "secondary",
              className: "business-edit-button",
              onClick: () => {
                setEditName(activeBusiness.name);
                setEditing(true);
                setError("");
              },
              children: "Edit business name"
            }
          )
        ] })
      ] })
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
  BusinessesPage
};
