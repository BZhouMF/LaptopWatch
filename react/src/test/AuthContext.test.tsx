import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, act, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

let _mock_code = 0;
let _mock_msg = "ok";
let _mock_should_reject = false;

vi.mock("../api/client", () => ({
  default: {
    post: vi.fn(() => {
      if (_mock_should_reject) return Promise.reject(new Error("Network Error"));
      return Promise.resolve({ data: { code: _mock_code, msg: _mock_msg } });
    }),
    get: vi.fn(),
  },
}));

import { AuthProvider, useAuth } from "../contexts/AuthContext";

// Test component that consumes the context
function TestConsumer() {
  const auth = useAuth();
  return (
    <div>
      <span data-testid="loading">{String(auth.is_loading)}</span>
      <span data-testid="error">{auth.error || "none"}</span>
      <button data-testid="login-btn" onClick={() => auth.login("admin", "pass")}>Login</button>
      <button data-testid="logout-btn" onClick={auth.logout}>Logout</button>
      <button data-testid="clear-btn" onClick={auth.clear_error}>Clear</button>
    </div>
  );
}

function render_auth() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    </MemoryRouter>
  );
}

describe("AuthContext", () => {
  beforeEach(() => {
    _mock_code = 0;
    _mock_msg = "ok";
    _mock_should_reject = false;
    Object.defineProperty(window, "location", {
      value: {
        href: "",
        search: "",
        pathname: "/",
      },
      writable: true,
      configurable: true,
    });
  });

  it("throws when useAuth is used outside AuthProvider", () => {
    function BadConsumer() {
      useAuth();
      return null;
    }
    expect(() => render(<BadConsumer />)).toThrow("useAuth must be used within AuthProvider");
  });

  it("starts with is_loading=false and no error", () => {
    render_auth();
    expect(screen.getByTestId("loading").textContent).toBe("false");
    expect(screen.getByTestId("error").textContent).toBe("none");
  });

  it("clear_error clears the error state", async () => {
    _mock_should_reject = true;
    render_auth();

    await act(async () => {
      screen.getByTestId("login-btn").click();
    });

    await waitFor(() => {
      expect(screen.getByTestId("error").textContent).not.toBe("none");
    });

    await act(async () => {
      screen.getByTestId("clear-btn").click();
    });

    expect(screen.getByTestId("error").textContent).toBe("none");
  });

  it("login success resets loading state", async () => {
    render_auth();

    await act(async () => {
      screen.getByTestId("login-btn").click();
    });

    await waitFor(() => {
      expect(screen.getByTestId("loading").textContent).toBe("false");
    });
  });

  it("login failure sets error message", async () => {
    _mock_code = 1;
    _mock_msg = "密码错误";
    render_auth();

    await act(async () => {
      screen.getByTestId("login-btn").click();
    });

    await waitFor(() => {
      expect(screen.getByTestId("error").textContent).toBe("密码错误");
    });
  });

  it("login network error sets fallback message", async () => {
    _mock_should_reject = true;
    render_auth();

    await act(async () => {
      screen.getByTestId("login-btn").click();
    });

    await waitFor(() => {
      expect(screen.getByTestId("error").textContent).toContain("登录失败");
    });
  });

  it("logout sets window.location.href to /logout", () => {
    render_auth();
    screen.getByTestId("logout-btn").click();
    expect(window.location.href).toBe("/logout");
  });
});
