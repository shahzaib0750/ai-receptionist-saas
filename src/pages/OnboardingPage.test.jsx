import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { OnboardingPage } from "./OnboardingPage";

const mocks = vi.hoisted(() => ({
  business: { id: "business-1", name: "Northstar Dental" },
  onboarding: vi.fn(),
  saveOnboarding: vi.fn(),
  provisionReceptionist: vi.fn(),
  activateReceptionist: vi.fn(),
}));

vi.mock("../business/BusinessContext", () => ({
  useBusiness: () => ({
    activeBusiness: mocks.business,
  }),
}));

vi.mock("../lib/api", () => ({
  api: {
    onboarding: mocks.onboarding,
    saveOnboarding: mocks.saveOnboarding,
    provisionReceptionist: mocks.provisionReceptionist,
    activateReceptionist: mocks.activateReceptionist,
  },
}));

const draft = {
  business_id: "business-1",
  name: "Northstar Dental",
  country_code: "US",
  selected_services: ["call_answering"],
  business_timezone: "America/New_York",
  fallback_instructions: "Do not guess.",
  status: "draft",
  attempts: 0,
};

describe("business onboarding", () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.clearAllMocks();
    mocks.onboarding.mockResolvedValue(draft);
    mocks.saveOnboarding.mockResolvedValue(draft);
  });

  it("saves business requirements and shows activation only after provisioning is ready", async () => {
    const user = userEvent.setup();
    mocks.provisionReceptionist.mockResolvedValue({
      ...draft,
      status: "ready",
      phone_number: "+12125550123",
    });
    render(
      <MemoryRouter>
        <OnboardingPage />
      </MemoryRouter>,
    );

    await screen.findByLabelText("Business name");
    await user.type(
      screen.getByLabelText("Your receptionist brief"),
      "We miss calls after work and need help answering questions about our services.",
    );
    expect(screen.getByText("AI call answering")).toBeInTheDocument();
    expect(screen.queryByText("Appointment booking")).not.toBeInTheDocument();
    await user.click(screen.getByLabelText(/I authorize the platform/));

    await user.click(screen.getByRole("button", { name: "Save and set up" }));

    await screen.findByRole("button", { name: "Activate receptionist" });
    expect(mocks.saveOnboarding).toHaveBeenCalledWith(
      "business-1",
      expect.objectContaining({
        selected_services: ["call_answering"],
        requirements_text: expect.stringContaining("We miss calls after work"),
      }),
    );
    expect(mocks.provisionReceptionist).toHaveBeenCalledWith("business-1", true);
    expect(screen.getByText("+12125550123")).toBeInTheDocument();

    mocks.activateReceptionist.mockResolvedValue({
      ...draft,
      status: "active",
      phone_number: "+12125550123",
    });
    await user.click(screen.getByRole("button", { name: "Activate receptionist" }));
    await waitFor(() => {
      expect(screen.getByText("Receptionist is active")).toBeInTheDocument();
    });
  });

  it("shows a real provisioning failure and offers a retry", async () => {
    const user = userEvent.setup();
    mocks.provisionReceptionist.mockResolvedValueOnce({
      ...draft,
      status: "failed",
      safe_error_code: "twilio_no_number",
      error_message: "No voice-enabled number is currently available.",
    }).mockResolvedValueOnce({
      ...draft,
      status: "ready",
      phone_number: "+12125550123",
    });
    render(
      <MemoryRouter>
        <OnboardingPage />
      </MemoryRouter>,
    );

    await screen.findByLabelText("Business name");
    fireEvent.change(screen.getByLabelText("Your receptionist brief"), {
      target: { value: "We need help answering calls and callers ask about our services." },
    });
    await user.click(screen.getByLabelText(/I authorize the platform/));
    await user.click(screen.getByRole("button", { name: "Save and set up" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "No voice-enabled number is currently available.",
    );

    await user.click(screen.getByRole("button", { name: "Retry or check setup" }));
    await screen.findByRole("button", { name: "Activate receptionist" });
    expect(mocks.provisionReceptionist).toHaveBeenCalledTimes(2);
  });
});
