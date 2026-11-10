import { jsx, jsxs } from "react/jsx-runtime";
import {
  Activity,
  AudioLines,
  Building2,
  ChevronDown,
  ChevronsUpDown,
  CreditCard,
  Headphones,
  LayoutDashboard,
  LogOut,
  Menu,
  Phone,
  ShieldCheck,
  Settings,
  Users,
  X
} from "lucide-react";
import { useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { useBusiness } from "../business/BusinessContext";
import { ErrorState, LoadingState } from "./ui";
const navigation = [
  { to: "/dashboard", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/businesses", label: "Businesses", icon: Building2 },
  { to: "/onboarding", label: "AI receptionist", icon: AudioLines },
  { to: "/calls", label: "Call history", icon: Phone },
  { to: "/billing", label: "Billing", icon: CreditCard },
  { to: "/admin/billing", label: "Billing admin", icon: ShieldCheck },
];
function AppLayout() {
  const { user, signOut } = useAuth();
  const {
    businesses,
    activeBusiness,
    activeBusinessId,
    loading,
    error,
    selectBusiness,
    refreshBusinesses
  } = useBusiness();
  const location = useLocation();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [businessMenuOpen, setBusinessMenuOpen] = useState(false);
  const [profileMenuOpen, setProfileMenuOpen] = useState(false);
  const pageTitle = navigation.find(
    (item) => item.end ? location.pathname === item.to : location.pathname.startsWith(item.to)
  )?.label ?? (location.pathname.startsWith("/settings") ? "Settings" : "Workspace");
  const logout = () => {
    signOut();
    navigate("/login", { replace: true });
  };
  return /* @__PURE__ */ jsxs("div", { className: "app-shell", children: [
    sidebarOpen && /* @__PURE__ */ jsx(
      "button",
      {
        className: "mobile-backdrop",
        "aria-label": "Close navigation",
        onClick: () => setSidebarOpen(false)
      }
    ),
    /* @__PURE__ */ jsxs("aside", { className: `sidebar ${sidebarOpen ? "sidebar-open" : ""}`, children: [
      /* @__PURE__ */ jsxs("div", { className: "brand-row", children: [
        /* @__PURE__ */ jsx("div", { className: "brand-mark", children: /* @__PURE__ */ jsx(Headphones, { size: 18, strokeWidth: 2.2 }) }),
        /* @__PURE__ */ jsx("span", { className: "brand-name", children: "relay" }),
        /* @__PURE__ */ jsx(
          "button",
          {
            className: "icon-button sidebar-close",
            "aria-label": "Close navigation",
            onClick: () => setSidebarOpen(false),
            children: /* @__PURE__ */ jsx(X, { size: 18 })
          }
        )
      ] }),
      /* @__PURE__ */ jsxs("div", { className: "workspace-picker-wrap", children: [
        /* @__PURE__ */ jsxs(
          "button",
          {
            className: "workspace-picker",
            onClick: () => setBusinessMenuOpen((open) => !open),
            "aria-expanded": businessMenuOpen,
            children: [
              /* @__PURE__ */ jsx("span", { className: "workspace-avatar", children: activeBusiness?.name.slice(0, 1).toUpperCase() ?? "R" }),
              /* @__PURE__ */ jsxs("span", { className: "workspace-text", children: [
                /* @__PURE__ */ jsx("strong", { children: activeBusiness?.name ?? "Your workspace" }),
                /* @__PURE__ */ jsx("small", { children: businesses.length === 1 ? "Workspace" : `${businesses.length} workspaces` })
              ] }),
              /* @__PURE__ */ jsx(ChevronsUpDown, { size: 15, className: "muted-icon" })
            ]
          }
        ),
        businessMenuOpen && /* @__PURE__ */ jsxs("div", { className: "popover business-popover", children: [
          /* @__PURE__ */ jsx("div", { className: "popover-caption", children: "Workspaces" }),
          businesses.map((business) => /* @__PURE__ */ jsxs(
            "button",
            {
              className: `popover-item ${business.id === activeBusinessId ? "selected" : ""}`,
              onClick: () => {
                selectBusiness(business.id);
                setBusinessMenuOpen(false);
                setSidebarOpen(false);
              },
              children: [
                /* @__PURE__ */ jsx("span", { className: "workspace-avatar small", children: business.name.slice(0, 1).toUpperCase() }),
                /* @__PURE__ */ jsx("span", { children: business.name })
              ]
            },
            business.id
          )),
          /* @__PURE__ */ jsxs(
            "button",
            {
              className: "popover-item",
              onClick: () => {
                navigate("/businesses");
                setBusinessMenuOpen(false);
              },
              children: [
                /* @__PURE__ */ jsx(Building2, { size: 16 }),
                "Manage businesses"
              ]
            }
          )
        ] })
      ] }),
      /* @__PURE__ */ jsx("div", { className: "nav-section-label", children: "Workspace" }),
      /* @__PURE__ */ jsx("nav", { className: "main-nav", "aria-label": "Main navigation", children: navigation.map(({ to, label, icon: Icon, end }) => /* @__PURE__ */ jsxs(
        NavLink,
        {
          to,
          end,
          className: ({ isActive }) => `nav-link ${isActive ? "nav-link-active" : ""}`,
          onClick: () => setSidebarOpen(false),
          children: [
            /* @__PURE__ */ jsx(Icon, { size: 17, strokeWidth: 1.9 }),
            /* @__PURE__ */ jsx("span", { children: label })
          ]
        },
        to
      )) }),
      /* @__PURE__ */ jsx("div", { className: "nav-section-label settings-label", children: "Account" }),
      /* @__PURE__ */ jsxs("nav", { className: "main-nav", "aria-label": "Account navigation", children: [
        /* @__PURE__ */ jsxs(
          NavLink,
          {
            to: "/settings",
            className: ({ isActive }) => `nav-link ${isActive ? "nav-link-active" : ""}`,
            onClick: () => setSidebarOpen(false),
            children: [
              /* @__PURE__ */ jsx(Settings, { size: 17, strokeWidth: 1.9 }),
              /* @__PURE__ */ jsx("span", { children: "Settings" })
            ]
          }
        ),
        /* @__PURE__ */ jsxs(
          NavLink,
          {
            to: "/team",
            className: ({ isActive }) => `nav-link ${isActive ? "nav-link-active" : ""}`,
            onClick: () => setSidebarOpen(false),
            children: [
              /* @__PURE__ */ jsx(Users, { size: 17, strokeWidth: 1.9 }),
              /* @__PURE__ */ jsx("span", { children: "Team" })
            ]
          }
        )
      ] }),
      /* @__PURE__ */ jsxs("div", { className: "sidebar-bottom", children: [
        /* @__PURE__ */ jsxs("div", { className: "help-panel", children: [
          /* @__PURE__ */ jsx("span", { className: "help-icon", children: /* @__PURE__ */ jsx(Activity, { size: 15 }) }),
          /* @__PURE__ */ jsxs("div", { children: [
            /* @__PURE__ */ jsx("strong", { children: "Need a hand?" }),
            /* @__PURE__ */ jsx("p", { children: "Explore your workspace setup." })
          ] }),
          /* @__PURE__ */ jsx(ChevronDown, { size: 14, className: "help-chevron" })
        ] }),
        /* @__PURE__ */ jsxs("div", { className: "sidebar-user", children: [
          /* @__PURE__ */ jsx("span", { className: "user-avatar", children: user?.full_name.slice(0, 1).toUpperCase() ?? "U" }),
          /* @__PURE__ */ jsxs("span", { className: "sidebar-user-copy", children: [
            /* @__PURE__ */ jsx("strong", { children: user?.full_name ?? "User" }),
            /* @__PURE__ */ jsx("small", { children: user?.email })
          ] }),
          /* @__PURE__ */ jsx(
            "button",
            {
              className: "icon-button logout-button",
              onClick: logout,
              title: "Log out",
              "aria-label": "Log out",
              children: /* @__PURE__ */ jsx(LogOut, { size: 16 })
            }
          )
        ] })
      ] })
    ] }),
    /* @__PURE__ */ jsxs("div", { className: "main-column", children: [
      /* @__PURE__ */ jsxs("header", { className: "topbar", children: [
        /* @__PURE__ */ jsxs("div", { className: "topbar-left", children: [
          /* @__PURE__ */ jsx(
            "button",
            {
              className: "icon-button mobile-menu",
              "aria-label": "Open navigation",
              onClick: () => setSidebarOpen(true),
              children: /* @__PURE__ */ jsx(Menu, { size: 19 })
            }
          ),
          /* @__PURE__ */ jsxs("div", { className: "breadcrumbs", children: [
            /* @__PURE__ */ jsx("span", { children: "Workspace" }),
            /* @__PURE__ */ jsx("span", { className: "breadcrumb-divider", children: "/" }),
            /* @__PURE__ */ jsx("strong", { children: pageTitle })
          ] })
        ] }),
        /* @__PURE__ */ jsxs("div", { className: "topbar-right", children: [
          businesses.length > 0 && /* @__PURE__ */ jsxs("label", { className: "topbar-business", children: [
            /* @__PURE__ */ jsx("span", { className: "sr-only", children: "Select business" }),
            /* @__PURE__ */ jsx(Building2, { size: 15 }),
            /* @__PURE__ */ jsx(
              "select",
              {
                value: activeBusinessId ?? "",
                onChange: (event) => selectBusiness(event.target.value),
                "aria-label": "Select business",
                children: businesses.map((business) => /* @__PURE__ */ jsx("option", { value: business.id, children: business.name }, business.id))
              }
            ),
            /* @__PURE__ */ jsx(ChevronDown, { size: 13 })
          ] }),
          /* @__PURE__ */ jsxs("div", { className: "profile-wrap", children: [
            /* @__PURE__ */ jsxs(
              "button",
              {
                className: "profile-button",
                onClick: () => setProfileMenuOpen((open) => !open),
                "aria-expanded": profileMenuOpen,
                "aria-label": "Open profile menu",
                children: [
                  /* @__PURE__ */ jsx("span", { className: "user-avatar small-avatar", children: user?.full_name.slice(0, 1).toUpperCase() ?? "U" }),
                  /* @__PURE__ */ jsx(ChevronDown, { size: 14 })
                ]
              }
            ),
            profileMenuOpen && /* @__PURE__ */ jsxs("div", { className: "popover profile-popover", children: [
              /* @__PURE__ */ jsxs("div", { className: "profile-popover-user", children: [
                /* @__PURE__ */ jsx("strong", { children: user?.full_name }),
                /* @__PURE__ */ jsx("small", { children: user?.email })
              ] }),
              /* @__PURE__ */ jsxs(
                "button",
                {
                  className: "popover-item",
                  onClick: () => {
                    navigate("/settings");
                    setProfileMenuOpen(false);
                  },
                  children: [
                    /* @__PURE__ */ jsx(Settings, { size: 16 }),
                    " Account settings"
                  ]
                }
              ),
              /* @__PURE__ */ jsxs("button", { className: "popover-item", onClick: logout, children: [
                /* @__PURE__ */ jsx(LogOut, { size: 16 }),
                " Log out"
              ] })
            ] })
          ] })
        ] })
      ] }),
      /* @__PURE__ */ jsx("main", { className: "content-area", children: error && businesses.length === 0 && !loading ? /* @__PURE__ */ jsx("div", { className: "content-state", children: /* @__PURE__ */ jsx(ErrorState, { message: error, onRetry: () => void refreshBusinesses() }) }) : loading && businesses.length === 0 ? /* @__PURE__ */ jsx("div", { className: "content-state", children: /* @__PURE__ */ jsx(LoadingState, { label: "Loading workspace" }) }) : /* @__PURE__ */ jsx(Outlet, {}) })
    ] }),
    /* @__PURE__ */ jsx(
      "button",
      {
        className: "click-catcher",
        "aria-label": "Close menus",
        tabIndex: -1,
        onClick: () => {
          setBusinessMenuOpen(false);
          setProfileMenuOpen(false);
        }
      }
    ),
    /* @__PURE__ */ jsx(
      "button",
      {
        className: "sr-only",
        "aria-label": "Refresh businesses",
        onClick: () => void refreshBusinesses(),
        children: "Refresh businesses"
      }
    )
  ] });
}
export {
  AppLayout
};
