import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, apiBaseUrl, authToken } from "./api";

describe("API client", () => {
  beforeEach(() => {
    authToken.clear();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("uses the documented local API URL by default", () => {
    expect(apiBaseUrl()).toBe("http://127.0.0.1:8000/api/v1");
  });

  it("sends registration and login fields matching the backend schemas", async () => {
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({
        id: "user-1",
        full_name: "Test User",
        email: "test@example.com",
      }), { status: 201, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        access_token: "test-token",
        token_type: "bearer",
      }), { status: 200, headers: { "Content-Type": "application/json" } })));

    await api.register("Test User", "test@example.com", "long-password");
    await api.login("test@example.com", "long-password");

    const [registerUrl, registerOptions] = fetch.mock.calls[0];
    expect(new URL(registerUrl).pathname).toBe("/api/v1/auth/register");
    expect(JSON.parse(registerOptions.body)).toEqual({
      full_name: "Test User",
      email: "test@example.com",
      password: "long-password",
    });

    const [loginUrl, loginOptions] = fetch.mock.calls[1];
    expect(new URL(loginUrl).pathname).toBe("/api/v1/auth/login");
    expect(JSON.parse(loginOptions.body)).toEqual({
      email: "test@example.com",
      password: "long-password",
    });
  });

  it("adds the stored access token to authenticated requests", async () => {
    authToken.write("test-token");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify([{ id: "business-1" }]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    ));

    await expect(api.businesses()).resolves.toEqual([{ id: "business-1" }]);
    const [url, options] = fetch.mock.calls[0];
    expect(url).toMatch(/\/businesses$/);
    expect(options.headers.get("Authorization")).toBe("Bearer test-token");
  });

  it("clears expired tokens and dispatches the auth expiration event", async () => {
    authToken.write("expired-token");
    const onExpired = vi.fn();
    window.addEventListener("auth:expired", onExpired);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "Not authenticated" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      }),
    ));

    await expect(api.me()).rejects.toMatchObject({
      name: "ApiError",
      status: 401,
      message: "Your session has expired. Please sign in again.",
    });

    expect(authToken.read()).toBeNull();
    expect(onExpired).toHaveBeenCalledOnce();
    window.removeEventListener("auth:expired", onExpired);
  });

  it("serializes call filters and sorting as query parameters", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ items: [], total: 0 }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    ));

    await api.calls("business-1", {
      limit: 25,
      offset: 0,
      caller: "+15551234567",
      sort_by: "created_at",
      sort_order: "asc",
      status: "",
    });

    const requestUrl = new URL(fetch.mock.calls[0][0]);
    expect(requestUrl.searchParams.get("limit")).toBe("25");
    expect(requestUrl.searchParams.get("offset")).toBe("0");
    expect(requestUrl.searchParams.get("caller")).toBe("+15551234567");
    expect(requestUrl.searchParams.get("sort_order")).toBe("asc");
    expect(requestUrl.searchParams.has("status")).toBe(false);
  });

  it("surfaces API errors with their HTTP status", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "Forbidden" }), {
        status: 403,
        headers: { "Content-Type": "application/json" },
      }),
    ));

    const rejection = api.calls("business-1");
    await expect(rejection).rejects.toBeInstanceOf(ApiError);
    await expect(rejection).rejects.toMatchObject({
      status: 403,
      kind: "http",
      message: "You don’t have permission to complete this action.",
    });
  });

  it("does not expose backend exception details or network configuration", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "database password is private" }), {
        status: 500,
        headers: {
          "Content-Type": "application/json",
          "X-Request-ID": "request-500",
        },
      }),
    ));

    await expect(api.login("user@example.com", "password")).rejects.toMatchObject({
      status: 500,
      message: "Something went wrong. Please try again later.",
      requestId: "request-500",
    });

    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    const networkError = await api.login("user@example.com", "password").catch((cause) => cause);
    expect(networkError).toMatchObject({
      status: 0,
      kind: "network",
      message: "Unable to connect to the server. Please check your connection and try again.",
    });
    expect(networkError.message).not.toContain(apiBaseUrl());
    expect(networkError.message).not.toContain("TypeError");
    expect(networkError.message).not.toContain("password");
  });

  it("does not expose validation payloads or backend messages", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        detail: [{
          msg: "invalid input",
          input: "secret-field-value",
        }],
      }), { status: 422 }),
    ));

    const error = await api.register("User", "invalid", "secret-field-value").catch((cause) => cause);
    expect(error).toMatchObject({
      status: 422,
      message: "Please check the information you entered and try again.",
    });
    expect(error.message).not.toContain("secret-field-value");
  });
});
