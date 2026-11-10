import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, useLocation } from "react-router-dom";
import { App } from "./App";
import { useAuth } from "./auth/AuthContext";
import { api } from "./lib/api";
import { AuthPage } from "./pages/AuthPage";

const authActions = vi.hoisted(() => ({
  signIn: vi.fn(),
  signUp: vi.fn(),
}));

vi.mock("./auth/AuthContext", () => ({
  useAuth: vi.fn(),
}));

vi.mock("./lib/api", () => ({
  api: {
    billingPlans: vi.fn(),
  },
  ApiError: class ApiError extends Error {},
}));

function renderAt(path) {
  return render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>);
}

function LocationProbe() {
  const location = useLocation();
  return <output aria-label="Current path">{location.pathname}</output>;
}

describe("public and protected routes", () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.clearAllMocks();
    authActions.signIn.mockResolvedValue(undefined);
    authActions.signUp.mockResolvedValue(undefined);
    useAuth.mockReturnValue({
      user: null,
      loading: false,
      signIn: authActions.signIn,
      signUp: authActions.signUp,
    });
    api.billingPlans.mockResolvedValue([]);
  });

  it("uses the public marketing page as the default route", () => {
    renderAt("/");

    expect(screen.getByRole("heading", {
      name: "Your AI Receptionist. Always Ready. Always Answering.",
    })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /get started/i }).every((link) => link.getAttribute("href") === "/register")).toBe(true);
  });

  it("keeps pricing public and routes login and registration to the existing auth page", () => {
    const pricing = renderAt("/pricing");
    expect(screen.getByRole("heading", { name: "Simple plans. Clear limits." })).toBeInTheDocument();
    pricing.unmount();

    const login = renderAt("/login");
    expect(screen.getByRole("heading", { name: "Welcome back." })).toBeInTheDocument();
    login.unmount();

    renderAt("/register");
    expect(screen.getByRole("heading", { name: "Build a better first hello." })).toBeInTheDocument();
  });

  it.each(["/dashboard", "/calls", "/billing"])("protects the existing route %s", (path) => {
    renderAt(path);

    expect(screen.getByRole("heading", { name: "Welcome back." })).toBeInTheDocument();
  });

  it("shows a public not-found page for unknown routes", () => {
    renderAt("/missing-page");

    expect(screen.getByRole("heading", { name: "Page not found" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Welcome back." })).not.toBeInTheDocument();
  });

  it("keeps login and registration using the existing auth actions", async () => {
    const user = userEvent.setup();
    const login = render(
      <MemoryRouter>
        <AuthPage mode="login" />
        <LocationProbe />
      </MemoryRouter>,
    );
    await user.type(screen.getByLabelText("Email address"), "owner@example.com");
    await user.type(screen.getByLabelText("Password"), "password123");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByLabelText("Current path")).toHaveTextContent("/dashboard");
    expect(authActions.signIn).toHaveBeenCalledWith("owner@example.com", "password123");
    login.unmount();

    render(
      <MemoryRouter>
        <AuthPage mode="register" />
        <LocationProbe />
      </MemoryRouter>,
    );
    await user.type(screen.getByLabelText("Full name"), "Workspace Owner");
    await user.type(screen.getByLabelText("Email address"), "new-owner@example.com");
    await user.type(screen.getByLabelText("Password"), "password123");
    await user.type(screen.getByLabelText("Confirm password"), "password123");
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByLabelText("Current path")).toHaveTextContent("/dashboard");
    expect(authActions.signUp).toHaveBeenCalledWith(
      "Workspace Owner",
      "new-owner@example.com",
      "password123",
    );
  });
});
