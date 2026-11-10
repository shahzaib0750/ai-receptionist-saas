import { Component } from "react";
import { jsx, jsxs } from "react/jsx-runtime";

export class ErrorBoundary extends Component {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  render() {
    if (!this.state.hasError) return this.props.children;

    return /* @__PURE__ */ jsxs("main", {
      className: "full-screen-state",
      children: [
        /* @__PURE__ */ jsxs("section", {
          className: "surface error-boundary-card",
          role: "alert",
          children: [
            /* @__PURE__ */ jsx("h1", { children: "Something went wrong" }),
            /* @__PURE__ */ jsx("p", {
              children: "We couldn’t load this page. Please try again.",
            }),
            /* @__PURE__ */ jsxs("div", {
              className: "error-boundary-actions",
              children: [
                /* @__PURE__ */ jsx("button", {
                  className: "button button-primary",
                  onClick: () => this.setState({ hasError: false }),
                  children: "Try again",
                }),
                /* @__PURE__ */ jsx("a", {
                  className: "button button-secondary",
                  href: "/",
                  children: "Go to homepage",
                }),
              ],
            }),
          ],
        }),
      ],
    });
  }
}
