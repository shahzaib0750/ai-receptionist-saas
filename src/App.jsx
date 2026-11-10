import { jsx, jsxs } from "react/jsx-runtime";
import { Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./auth/AuthContext";
import { AppLayout } from "./components/AppLayout";
import { LoadingState } from "./components/ui";
import { AdminBillingPage } from "./pages/AdminBillingPage";
import { AuthPage } from "./pages/AuthPage";
import { BillingPage } from "./pages/BillingPage";
import { BusinessesPage } from "./pages/BusinessesPage";
import { CallsPage } from "./pages/CallsPage";
import { DashboardPage } from "./pages/DashboardPage";
import { HomePage } from "./pages/HomePage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { OnboardingPage } from "./pages/OnboardingPage";
import { PricingPage } from "./pages/PricingPage";
import { SettingsPage } from "./pages/SettingsPage";
import { TeamPage } from "./pages/TeamPage";
function ProtectedLayout() {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) {
    return /* @__PURE__ */ jsx("div", { className: "full-screen-state", children: /* @__PURE__ */ jsx(LoadingState, { label: "Restoring your session" }) });
  }
  if (!user) return /* @__PURE__ */ jsx(Navigate, { to: "/login", replace: true, state: { from: location } });
  return /* @__PURE__ */ jsx(Outlet, {});
}
function App() {
  const { user, loading } = useAuth();
  return /* @__PURE__ */ jsxs(Routes, { children: [
    /* @__PURE__ */ jsx(Route, { path: "/", element: /* @__PURE__ */ jsx(HomePage, { user }) }),
    /* @__PURE__ */ jsx(Route, { path: "/pricing", element: /* @__PURE__ */ jsx(PricingPage, { user }) }),
    /* @__PURE__ */ jsx(
      Route,
      {
        path: "/login",
        element: loading ? /* @__PURE__ */ jsx("div", { className: "full-screen-state", children: /* @__PURE__ */ jsx(LoadingState, {}) }) : user ? /* @__PURE__ */ jsx(Navigate, { to: "/dashboard", replace: true }) : /* @__PURE__ */ jsx(AuthPage, { mode: "login" })
      }
    ),
    /* @__PURE__ */ jsx(
      Route,
      {
        path: "/register",
        element: loading ? /* @__PURE__ */ jsx("div", { className: "full-screen-state", children: /* @__PURE__ */ jsx(LoadingState, {}) }) : user ? /* @__PURE__ */ jsx(Navigate, { to: "/dashboard", replace: true }) : /* @__PURE__ */ jsx(AuthPage, { mode: "register" })
      }
    ),
    /* @__PURE__ */ jsx(Route, { element: /* @__PURE__ */ jsx(ProtectedLayout, {}), children: /* @__PURE__ */ jsxs(Route, { element: /* @__PURE__ */ jsx(AppLayout, {}), children: [
      /* @__PURE__ */ jsx(Route, { path: "dashboard", element: /* @__PURE__ */ jsx(DashboardPage, {}) }),
      /* @__PURE__ */ jsx(Route, { path: "businesses", element: /* @__PURE__ */ jsx(BusinessesPage, {}) }),
      /* @__PURE__ */ jsx(Route, { path: "onboarding", element: /* @__PURE__ */ jsx(OnboardingPage, {}) }),
      /* @__PURE__ */ jsx(Route, { path: "receptionist", element: /* @__PURE__ */ jsx(Navigate, { to: "/onboarding", replace: true }) }),
      /* @__PURE__ */ jsx(Route, { path: "calls", element: /* @__PURE__ */ jsx(CallsPage, {}) }),
      /* @__PURE__ */ jsx(Route, { path: "billing", element: /* @__PURE__ */ jsx(BillingPage, {}) }),
      /* @__PURE__ */ jsx(Route, { path: "admin/billing", element: /* @__PURE__ */ jsx(AdminBillingPage, {}) }),
      /* @__PURE__ */ jsx(Route, { path: "integrations", element: /* @__PURE__ */ jsx(Navigate, { to: "/onboarding", replace: true }) }),
      /* @__PURE__ */ jsx(Route, { path: "settings", element: /* @__PURE__ */ jsx(SettingsPage, {}) }),
      /* @__PURE__ */ jsx(Route, { path: "team", element: /* @__PURE__ */ jsx(TeamPage, {}) })
    ] }) }),
    /* @__PURE__ */ jsx(Route, { path: "*", element: /* @__PURE__ */ jsx(NotFoundPage, {}) })
  ] });
}
export {
  App
};
