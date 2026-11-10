const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api/v1").replace(/\/+$/, "");
const TOKEN_KEY = "receptionist.access-token";
class ApiError extends Error {
  constructor(message, status, requestId = null, kind = "http") {
    super(message);
    this.status = status;
    this.kind = kind;
    this.requestId = requestId;
    this.name = "ApiError";
  }
}

function messageForStatus(status, path) {
  if (status === 0) return "Unable to connect to the server. Please check your connection and try again.";
  if (status === 401 && path === "/auth/login") return "The email or password is incorrect.";
  if (status === 401) return "Your session has expired. Please sign in again.";
  if (status === 403) return "You don’t have permission to complete this action.";
  if (status === 404) return "The requested information could not be found.";
  if (status === 409) return "This information conflicts with an existing record. Please review it and try again.";
  if (status === 422) return "Please check the information you entered and try again.";
  if (status === 429) return "Too many requests. Please wait a moment and try again.";
  if (status === 503) return "The service is temporarily unavailable. Please try again later.";
  if (status >= 500) return "Something went wrong. Please try again later.";
  return "Your request couldn’t be completed. Please review your information and try again.";
}

function userFacingErrorMessage(error, fallback = "Something went wrong. Please try again.") {
  return error instanceof ApiError ? error.message : fallback;
}

const authToken = {
  read: () => sessionStorage.getItem(TOKEN_KEY),
  write: (token) => sessionStorage.setItem(TOKEN_KEY, token),
  clear: () => sessionStorage.removeItem(TOKEN_KEY)
};
async function request(path, options = {}, authenticated = true) {
  const headers = new Headers(options.headers);
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const token = authenticated ? authToken.read() : null;
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers
    });
  } catch {
    throw new ApiError(messageForStatus(0, path), 0, null, "network");
  }
  if (response.status === 401 && authenticated) {
    authToken.clear();
    window.dispatchEvent(new Event("auth:expired"));
  }
  if (!response.ok) {
    throw new ApiError(
      messageForStatus(response.status, path),
      response.status,
      response.headers.get("X-Request-ID")
    );
  }
  if (response.status === 204) return void 0;
  try {
    return await response.json();
  } catch {
    throw new ApiError(
      "The server returned an unexpected response. Please try again.",
      response.status,
      response.headers.get("X-Request-ID"),
      "response"
    );
  }
}
const json = (method, value) => ({
  method,
  ...value === void 0 ? {} : { body: JSON.stringify(value) }
});
const api = {
  async login(email, password) {
    return request(
      "/auth/login",
      json("POST", { email, password }),
      false
    );
  },
  register: (full_name, email, password) => request(
    "/auth/register",
    json("POST", { full_name, email, password }),
    false
  ),
  me: () => request("/auth/me"),
  updateProfile: (payload) => request("/auth/me", json("PATCH", payload)),
  changePassword: (current_password, new_password) => request(
    "/auth/change-password",
    json("POST", { current_password, new_password })
  ),
  businesses: () => request("/businesses"),
  createBusiness: (name) => request("/businesses", json("POST", { name })),
  updateBusiness: (businessId, name) => request(`/businesses/${businessId}`, json("PATCH", { name })),
  onboarding: (businessId) => request(`/businesses/${businessId}/onboarding`),
  saveOnboarding: (businessId, payload) => request(
    `/businesses/${businessId}/onboarding`,
    json("PUT", payload)
  ),
  provisionReceptionist: (businessId, acceptPhoneProvisioning) => request(
    `/businesses/${businessId}/receptionist/provision`,
    json("POST", {
      accept_phone_number_provisioning: acceptPhoneProvisioning,
    })
  ),
  activateReceptionist: (businessId) => request(
    `/businesses/${businessId}/receptionist/activate`,
    json("POST")
  ),
  members: (businessId) => request(`/businesses/${businessId}/members`),
  addMember: (businessId, email, role) => request(
    `/businesses/${businessId}/members`,
    json("POST", { email, role })
  ),
  updateMember: (businessId, userId, role) => request(
    `/businesses/${businessId}/members/${userId}`,
    json("PATCH", { role })
  ),
  removeMember: (businessId, userId) => request(
    `/businesses/${businessId}/members/${userId}`,
    json("DELETE")
  ),
  receptionist: (businessId) => request(
    `/businesses/${businessId}/receptionist-configuration`
  ),
  createReceptionist: (businessId, payload) => request(
    `/businesses/${businessId}/receptionist-configuration`,
    json("POST", payload)
  ),
  updateReceptionist: (businessId, payload) => request(
    `/businesses/${businessId}/receptionist-configuration`,
    json("PATCH", payload)
  ),
  vapi: (businessId) => request(
    `/businesses/${businessId}/vapi-configuration`
  ),
  createVapi: (businessId, payload) => request(
    `/businesses/${businessId}/vapi-configuration`,
    json("POST", payload)
  ),
  updateVapi: (businessId, payload) => request(
    `/businesses/${businessId}/vapi-configuration`,
    json("PATCH", payload)
  ),
  calls: (businessId, params = {}) => {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value !== void 0 && value !== "") query.set(key, String(value));
    }
    const suffix = query.size ? `?${query.toString()}` : "";
    return request(`/businesses/${businessId}/calls${suffix}`);
  },
  call: (businessId, callId) => request(`/businesses/${businessId}/calls/${callId}`),
  billingPlans: () => request("/billing/plans"),
  billingSubscription: (businessId) => request(`/businesses/${businessId}/billing/subscription`),
  billingUsage: (businessId) => request(`/businesses/${businessId}/billing/usage`),
  billingInvoices: (businessId) => request(`/businesses/${businessId}/billing/invoices`),
  createBillingCheckout: (businessId, planId) => request(
    `/businesses/${businessId}/billing/checkout`,
    json("POST", { plan_id: planId })
  ),
  cancelBillingSubscription: (businessId) => request(
    `/businesses/${businessId}/billing/cancel`,
    json("POST")
  ),
  changeBillingPlan: (businessId, planId) => request(
    `/businesses/${businessId}/billing/change-plan`,
    json("POST", { plan_id: planId })
  ),
  billingPortal: (businessId) => request(
    `/businesses/${businessId}/billing/portal`,
    json("POST")
  ),
  adminBillingOverview: () => request("/admin/billing/overview"),
  adminBillingPlans: () => request("/admin/billing/plans"),
  adminBillingSubscriptions: () => request("/admin/billing/subscriptions"),
  adminBillingUsage: () => request("/admin/billing/usage"),
  adminBillingPayments: () => request("/admin/billing/payments"),
  createBillingPlan: (payload) => request("/admin/billing/plans", json("POST", payload)),
  updateBillingPlan: (planId, payload) => request(
    `/admin/billing/plans/${planId}`,
    json("PATCH", payload)
  ),
  grantBillingMinutes: (subscriptionId, minutes, reason) => request(
    `/admin/billing/subscriptions/${subscriptionId}/adjust-minutes`,
    json("POST", { minutes, reason })
  ),
  suspendBillingSubscription: (subscriptionId) => request(
    `/admin/billing/subscriptions/${subscriptionId}/suspend`,
    json("POST")
  ),
  reactivateBillingSubscription: (subscriptionId) => request(
    `/admin/billing/subscriptions/${subscriptionId}/reactivate`,
    json("POST")
  )
};
function apiBaseUrl() {
  return API_BASE_URL;
}
export {
  ApiError,
  api,
  apiBaseUrl,
  authToken,
  userFacingErrorMessage
};
