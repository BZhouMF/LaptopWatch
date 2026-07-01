import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Outlet } from "react-router-dom";

// Mock all page components as stubs
vi.mock("../pages/LoginPage", () => ({
  default: () => <div data-testid="login-page">Login</div>,
}));
vi.mock("../pages/RegisterPage", () => ({
  default: () => <div data-testid="register-page">Register</div>,
}));
vi.mock("../pages/HomePage", () => ({
  default: () => <div data-testid="home-page">Home</div>,
}));
vi.mock("../pages/BrowsePage", () => ({
  default: () => <div data-testid="browse-page">Browse</div>,
}));
vi.mock("../pages/CategoryBrowsePage", () => ({
  default: () => <div data-testid="category-browse-page">Category</div>,
}));
vi.mock("../pages/MediaPlayerPage", () => ({
  default: () => <div data-testid="media-player-page">Player</div>,
}));
vi.mock("../pages/TextViewerPage", () => ({
  default: () => <div data-testid="text-viewer-page">Text</div>,
}));
vi.mock("../pages/NotFoundPage", () => ({
  default: () => <div data-testid="not-found-page">404</div>,
}));
vi.mock("../components/ProtectedRoute", () => ({
  default: () => <div data-testid="protected-route"><Outlet /></div>,
}));
vi.mock("../components/Layout", () => ({
  default: () => <div data-testid="layout"><Outlet /></div>,
}));

import AppRouter from "../router";

describe("AppRouter", () => {
  it("renders LoginPage at /login", () => {
    render(
      <MemoryRouter initialEntries={["/login"]}>
        <AppRouter />
      </MemoryRouter>
    );
    expect(screen.getByTestId("login-page")).toBeDefined();
  });

  it("renders RegisterPage at /register", () => {
    render(
      <MemoryRouter initialEntries={["/register"]}>
        <AppRouter />
      </MemoryRouter>
    );
    expect(screen.getByTestId("register-page")).toBeDefined();
  });

  it("renders NotFoundPage for unknown paths", () => {
    render(
      <MemoryRouter initialEntries={["/nonexistent"]}>
        <AppRouter />
      </MemoryRouter>
    );
    expect(screen.getByTestId("not-found-page")).toBeDefined();
  });

  it("renders HomePage at / inside ProtectedRoute and Layout", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <AppRouter />
      </MemoryRouter>
    );
    expect(screen.getByTestId("protected-route")).toBeDefined();
    expect(screen.getByTestId("layout")).toBeDefined();
    expect(screen.getByTestId("home-page")).toBeDefined();
  });

  it("renders BrowsePage at /browse/* inside ProtectedRoute and Layout", () => {
    render(
      <MemoryRouter initialEntries={["/browse/some/path"]}>
        <AppRouter />
      </MemoryRouter>
    );
    expect(screen.getByTestId("protected-route")).toBeDefined();
    expect(screen.getByTestId("layout")).toBeDefined();
    expect(screen.getByTestId("browse-page")).toBeDefined();
  });

  it("renders CategoryBrowsePage at /category/* inside ProtectedRoute", () => {
    render(
      <MemoryRouter initialEntries={["/category/grid/test"]}>
        <AppRouter />
      </MemoryRouter>
    );
    expect(screen.getByTestId("protected-route")).toBeDefined();
    expect(screen.getByTestId("category-browse-page")).toBeDefined();
  });

  it("renders MediaPlayerPage at /media/player inside ProtectedRoute", () => {
    render(
      <MemoryRouter initialEntries={["/media/player"]}>
        <AppRouter />
      </MemoryRouter>
    );
    expect(screen.getByTestId("protected-route")).toBeDefined();
    expect(screen.getByTestId("media-player-page")).toBeDefined();
  });

  it("renders TextViewerPage at /file/text/* inside ProtectedRoute", () => {
    render(
      <MemoryRouter initialEntries={["/file/text/some/file.txt"]}>
        <AppRouter />
      </MemoryRouter>
    );
    expect(screen.getByTestId("protected-route")).toBeDefined();
    expect(screen.getByTestId("text-viewer-page")).toBeDefined();
  });

  it("login and register pages are NOT wrapped in ProtectedRoute", () => {
    render(
      <MemoryRouter initialEntries={["/login"]}>
        <AppRouter />
      </MemoryRouter>
    );
    expect(screen.queryByTestId("protected-route")).toBeNull();
    expect(screen.getByTestId("login-page")).toBeDefined();
  });
});
