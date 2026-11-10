import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { api } from "../lib/api";
import { HomePage } from "./HomePage";
import { PricingPage } from "./PricingPage";

vi.mock("../lib/api", () => ({
  api: {
    billingPlans: vi.fn(),
  },
  userFacingErrorMessage: (_error, fallback) => fallback,
}));

const publishedPlan = {
  id: "plan-1",
  name: "Essentials",
  description: "For teams getting started.",
  monthly_price: "39.00",
  currency: "USD",
  included_minutes: 500,
  max_phone_numbers: 1,
};

function renderPage(element) {
  return render(<MemoryRouter>{element}</MemoryRouter>);
}

describe("public marketing pages", () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.clearAllMocks();
    api.billingPlans.mockResolvedValue([publishedPlan]);
  });

  it("renders the public homepage and clearly distinguishes unavailable features", async () => {
    renderPage(<HomePage user={null} />);

    expect(screen.getByRole("heading", {
      name: "Your AI Receptionist. Always Ready. Always Answering.",
    })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /get started/i }).every((link) => link.getAttribute("href") === "/register")).toBe(true);
    expect(screen.getByRole("link", { name: /explore pricing/i })).toHaveAttribute("href", "#pricing");
    expect(screen.getByText(/not currently available/i)).toBeInTheDocument();
    expect(screen.getByText(/does not book or change appointments/i)).toBeInTheDocument();
    expect(await screen.findByText("Essentials")).toBeInTheDocument();
    expect(api.billingPlans).toHaveBeenCalledOnce();
  });

  it("shows actual public plan values and avoids suggesting checkout is live", async () => {
    renderPage(<PricingPage user={null} />);

    expect(await screen.findByRole("heading", { name: "Essentials" })).toBeInTheDocument();
    expect(screen.getAllByText("$39.00")).toHaveLength(2);
    expect(screen.getAllByText("500", { exact: false })).toHaveLength(2);
    expect(document.querySelector(".marketing-plan-details")).toHaveTextContent("Up to 1 phone number");
    expect(screen.getByRole("table", { name: "Compare published plans" })).toBeInTheDocument();
    expect(screen.getByText(/live checkout, subscription changes, and payment processing are not currently available/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /create an account/i })).toHaveAttribute("href", "/register");
  });

  it("shows a real empty-catalog fallback without inventing a plan", async () => {
    api.billingPlans.mockResolvedValue([]);
    renderPage(<PricingPage user={null} />);

    expect(await screen.findByText("Plans are being prepared.")).toBeInTheDocument();
    expect(screen.queryByText("Essentials")).not.toBeInTheDocument();
  });

  it("provides a retry when the public plan request fails", async () => {
    api.billingPlans.mockRejectedValueOnce(new Error("Service unavailable"));
    renderPage(<PricingPage user={null} />);

    expect(await screen.findByText("Plan information is temporarily unavailable.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));

    await waitFor(() => expect(api.billingPlans).toHaveBeenCalledTimes(2));
    expect(await screen.findByRole("heading", { name: "Essentials" })).toBeInTheDocument();
  });

  it("offers signed-in visitors a dashboard link", async () => {
    renderPage(<HomePage user={{ id: "user-1" }} />);

    const dashboardLinks = screen.getAllByRole("link", { name: "Dashboard" });
    expect(dashboardLinks).toHaveLength(2);
    expect(dashboardLinks.every((link) => link.getAttribute("href") === "/dashboard")).toBe(true);
    const dashboardActions = await screen.findAllByRole("link", { name: /open dashboard/i });
    expect(dashboardActions).toHaveLength(1);
    expect(dashboardActions[0]).toHaveAttribute("href", "/dashboard");
  });
});
