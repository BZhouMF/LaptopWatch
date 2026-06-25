import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

// Mock the API client to avoid actual network calls in child components
vi.mock("../api/client", () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: { exists: true } }),
    post: vi.fn().mockResolvedValue({ data: { code: 0 } }),
  },
}));

// Mock heavy child pages for simpler smoke test
vi.mock("../pages/HomePage", () => ({
  default: () => <div data-testid="home-page">Home</div>,
}));

vi.mock("../pages/LoginPage", () => ({
  default: () => <div data-testid="login-page">Login</div>,
}));

vi.mock("../pages/RegisterPage", () => ({
  default: () => <div data-testid="register-page">Register</div>,
}));

vi.mock("../pages/BrowsePage", () => ({
  default: () => <div data-testid="browse-page">Browse</div>,
}));

vi.mock("../pages/CategoryBrowsePage", () => ({
  default: () => <div data-testid="category-page">Category</div>,
}));

vi.mock("../pages/MediaPlayerPage", () => ({
  default: () => <div data-testid="player-page">Player</div>,
}));

vi.mock("../pages/NotFoundPage", () => ({
  default: () => <div data-testid="not-found-page">404</div>,
}));

vi.mock("../components/ProtectedRoute", () => ({
  default: () => {
    const { Outlet } = require("react-router-dom");
    return <Outlet />;
  },
}));

vi.mock("../components/Layout", () => ({
  default: () => {
    const { Outlet } = require("react-router-dom");
    return <Outlet />;
  },
}));

import App from "../App";

describe("App", () => {
  it("renders login page at /login", async () => {
    render(
      <MemoryRouter initialEntries={["/login"]}>
        <App />
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(screen.getByTestId("login-page")).toBeDefined();
    });
  });

  it("renders register page at /register", async () => {
    render(
      <MemoryRouter initialEntries={["/register"]}>
        <App />
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(screen.getByTestId("register-page")).toBeDefined();
    });
  });

  it("renders home page at /", async () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(screen.getByTestId("home-page")).toBeDefined();
    });
  });

  it("renders not found page for unknown paths", async () => {
    render(
      <MemoryRouter initialEntries={["/nonexistent"]}>
        <App />
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(screen.getByTestId("not-found-page")).toBeDefined();
    });
  });
});
