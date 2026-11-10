import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ErrorBoundary } from "./ErrorBoundary";

function BrokenPage() {
  throw new Error("database credentials must not be shown");
}

describe("ErrorBoundary", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("shows a friendly recovery page without rendering the exception", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});

    render(<ErrorBoundary><BrokenPage /></ErrorBoundary>);

    expect(screen.getByRole("heading", { name: "Something went wrong" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
    expect(screen.queryByText(/database credentials/i)).not.toBeInTheDocument();
  });
});
