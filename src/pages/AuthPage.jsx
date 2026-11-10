import { jsx, jsxs } from "react/jsx-runtime";
import { Eye, EyeOff, Headphones, LoaderCircle, LockKeyhole, Mail, UserRound } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { userFacingErrorMessage } from "../lib/api";
function AuthPage({ mode }) {
  const isRegister = mode === "register";
  const { signIn, signUp } = useAuth();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (event) => {
    event.preventDefault();
    setError("");
    if (isRegister && password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      if (isRegister) await signUp(name.trim(), email.trim(), password);
      else await signIn(email.trim(), password);
      navigate("/dashboard", { replace: true });
    } catch (cause) {
      setError(userFacingErrorMessage(cause));
    } finally {
      setBusy(false);
    }
  };
  const strength = password.length === 0 ? 0 : password.length >= 12 && /[A-Z]/.test(password) && /\d/.test(password) ? 3 : password.length >= 8 ? 2 : 1;
  return /* @__PURE__ */ jsxs("div", { className: "auth-page", children: [
    /* @__PURE__ */ jsxs("div", { className: "auth-panel", children: [
      /* @__PURE__ */ jsxs(Link, { to: "/", className: "auth-brand", "aria-label": "Relay home", children: [
        /* @__PURE__ */ jsx("span", { className: "brand-mark", children: /* @__PURE__ */ jsx(Headphones, { size: 18 }) }),
        /* @__PURE__ */ jsx("span", { className: "brand-name", children: "relay" })
      ] }),
      /* @__PURE__ */ jsxs("div", { className: "auth-form-wrap", children: [
        /* @__PURE__ */ jsxs("div", { className: "auth-heading", children: [
          /* @__PURE__ */ jsx("div", { className: "auth-kicker", children: "AI-powered conversations" }),
          /* @__PURE__ */ jsx("h1", { children: isRegister ? "Build a better first hello." : "Welcome back." }),
          /* @__PURE__ */ jsx("p", { children: isRegister ? "Create your account and set up your AI receptionist." : "Sign in to manage your receptionist and calls." })
        ] }),
        /* @__PURE__ */ jsxs("form", { className: "auth-form", onSubmit: (event) => void submit(event), children: [
          isRegister && /* @__PURE__ */ jsxs("div", { className: "field", children: [
            /* @__PURE__ */ jsx("label", { htmlFor: "full-name", children: "Full name" }),
            /* @__PURE__ */ jsxs("div", { className: "input-icon-wrap", children: [
              /* @__PURE__ */ jsx(UserRound, { size: 17, "aria-hidden": "true" }),
              /* @__PURE__ */ jsx(
                "input",
                {
                  id: "full-name",
                  name: "name",
                  autoComplete: "name",
                  value: name,
                  onChange: (event) => setName(event.target.value),
                  required: true,
                  minLength: 1,
                  maxLength: 200,
                  placeholder: "Your name"
                }
              )
            ] })
          ] }),
          /* @__PURE__ */ jsxs("div", { className: "field", children: [
            /* @__PURE__ */ jsx("label", { htmlFor: "email", children: "Email address" }),
            /* @__PURE__ */ jsxs("div", { className: "input-icon-wrap", children: [
              /* @__PURE__ */ jsx(Mail, { size: 17, "aria-hidden": "true" }),
              /* @__PURE__ */ jsx(
                "input",
                {
                  id: "email",
                  name: "email",
                  type: "email",
                  autoComplete: "email",
                  value: email,
                  onChange: (event) => setEmail(event.target.value),
                  required: true,
                  placeholder: "you@company.com"
                }
              )
            ] })
          ] }),
          /* @__PURE__ */ jsxs("div", { className: "field", children: [
            /* @__PURE__ */ jsxs("div", { className: "field-label-row", children: [
              /* @__PURE__ */ jsx("label", { htmlFor: "password", children: "Password" }),
              !isRegister && /* @__PURE__ */ jsx("span", { className: "field-note", children: "Minimum 8 characters" })
            ] }),
            /* @__PURE__ */ jsxs("div", { className: "input-icon-wrap", children: [
              /* @__PURE__ */ jsx(LockKeyhole, { size: 17, "aria-hidden": "true" }),
              /* @__PURE__ */ jsx(
                "input",
                {
                  id: "password",
                  name: "password",
                  type: showPassword ? "text" : "password",
                  autoComplete: isRegister ? "new-password" : "current-password",
                  value: password,
                  onChange: (event) => setPassword(event.target.value),
                  required: true,
                  minLength: isRegister ? 8 : void 0,
                  maxLength: 128,
                  placeholder: "Enter your password"
                }
              ),
              /* @__PURE__ */ jsx(
                "button",
                {
                  type: "button",
                  className: "field-icon-button",
                  "aria-label": showPassword ? "Hide password" : "Show password",
                  onClick: () => setShowPassword((show) => !show),
                  children: showPassword ? /* @__PURE__ */ jsx(EyeOff, { size: 17 }) : /* @__PURE__ */ jsx(Eye, { size: 17 })
                }
              )
            ] }),
            isRegister && password.length > 0 && /* @__PURE__ */ jsxs("div", { className: "password-strength", "aria-live": "polite", children: [
              /* @__PURE__ */ jsx("div", { className: "strength-bars", children: [1, 2, 3].map((level) => /* @__PURE__ */ jsx("span", { className: strength >= level ? `strength-${strength}` : "" }, level)) }),
              /* @__PURE__ */ jsx("span", { children: strength === 3 ? "Strong" : strength === 2 ? "Good" : "Too short" })
            ] })
          ] }),
          isRegister && /* @__PURE__ */ jsxs("div", { className: "field", children: [
            /* @__PURE__ */ jsx("label", { htmlFor: "confirm-password", children: "Confirm password" }),
            /* @__PURE__ */ jsxs("div", { className: "input-icon-wrap", children: [
              /* @__PURE__ */ jsx(LockKeyhole, { size: 17, "aria-hidden": "true" }),
              /* @__PURE__ */ jsx(
                "input",
                {
                  id: "confirm-password",
                  name: "confirm-password",
                  type: showPassword ? "text" : "password",
                  autoComplete: "new-password",
                  value: confirmPassword,
                  onChange: (event) => setConfirmPassword(event.target.value),
                  required: true,
                  maxLength: 128,
                  placeholder: "Re-enter your password"
                }
              )
            ] })
          ] }),
          error && /* @__PURE__ */ jsx("div", { className: "form-alert", role: "alert", children: error }),
          /* @__PURE__ */ jsxs("button", { type: "submit", className: "button button-primary auth-submit", disabled: busy, children: [
            busy && /* @__PURE__ */ jsx(LoaderCircle, { size: 16, className: "spin" }),
            busy ? "Please wait\u2026" : isRegister ? "Create account" : "Sign in"
          ] })
        ] }),
        /* @__PURE__ */ jsxs("p", { className: "auth-switch", children: [
          isRegister ? "Already have an account?" : "New to Relay?",
          " ",
          /* @__PURE__ */ jsx(Link, { to: isRegister ? "/login" : "/register", children: isRegister ? "Sign in" : "Create an account" })
        ] }),
        /* @__PURE__ */ jsxs("div", { className: "auth-footer", children: [
          /* @__PURE__ */ jsx("span", { children: "Secure sign-in" }),
          /* @__PURE__ */ jsx("span", { className: "auth-footer-dot" }),
          /* @__PURE__ */ jsx("span", { children: "Your conversations stay yours" })
        ] })
      ] })
    ] }),
    /* @__PURE__ */ jsxs("aside", { className: "auth-aside", children: [
      /* @__PURE__ */ jsxs("div", { className: "auth-aside-art", children: [
        /* @__PURE__ */ jsx("div", { className: "orbit orbit-one" }),
        /* @__PURE__ */ jsx("div", { className: "orbit orbit-two" }),
        /* @__PURE__ */ jsx("div", { className: "orbit orbit-three" }),
        /* @__PURE__ */ jsxs("div", { className: "art-center", children: [
          /* @__PURE__ */ jsx(Headphones, { size: 39, strokeWidth: 1.4 }),
          /* @__PURE__ */ jsx("span", { className: "art-pulse" })
        ] }),
        /* @__PURE__ */ jsxs("div", { className: "art-callout callout-top", children: [
          /* @__PURE__ */ jsxs("span", { className: "callout-wave", children: [
            /* @__PURE__ */ jsx("i", {}),
            /* @__PURE__ */ jsx("i", {}),
            /* @__PURE__ */ jsx("i", {}),
            /* @__PURE__ */ jsx("i", {}),
            /* @__PURE__ */ jsx("i", {})
          ] }),
          "Always ready to help"
        ] }),
        /* @__PURE__ */ jsxs("div", { className: "art-callout callout-bottom", children: [
          /* @__PURE__ */ jsx("span", { className: "callout-dot" }),
          "Call answered ",
          /* @__PURE__ */ jsx("strong", { children: "just now" })
        ] })
      ] }),
      /* @__PURE__ */ jsxs("div", { className: "auth-aside-copy", children: [
        /* @__PURE__ */ jsx("span", { className: "aside-label", children: "A more human first impression" }),
        /* @__PURE__ */ jsxs("h2", { children: [
          "Every call deserves",
          /* @__PURE__ */ jsx("br", {}),
          "a thoughtful answer."
        ] }),
        /* @__PURE__ */ jsx("p", { children: "Let your receptionist take care of the first hello, so your team can focus on what comes next." })
      ] }),
      /* @__PURE__ */ jsxs("div", { className: "auth-aside-bottom", children: [
        /* @__PURE__ */ jsxs("span", { children: [
          "\xA9 ",
          (/* @__PURE__ */ new Date()).getFullYear(),
          " Relay"
        ] }),
        /* @__PURE__ */ jsx("span", { children: "Made for teams that care" })
      ] })
    ] })
  ] });
}
export {
  AuthPage
};
