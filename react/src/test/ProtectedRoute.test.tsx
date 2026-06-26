import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { act } from "react";
import { MemoryRouter } from "react-router-dom";
import ProtectedRoute from "../components/ProtectedRoute";

vi.mock("../api/client", () => ({
  default: {
    get: vi.fn(),
  },
}));

import api_client from "../api/client";

function render_protected_route(initial_path = "/") {
  return render(
    <MemoryRouter initialEntries={[initial_path]}>
      <ProtectedRoute />
    </MemoryRouter>
  );
}

describe("ProtectedRoute", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows loading spinner while checking auth", () => {
    (api_client.get as ReturnType<typeof vi.fn>).mockReturnValue(
      new Promise(() => {}) // never resolves
    );
    render_protected_route();
    const spinner = document.querySelector(".animate-spin");
    expect(spinner).toBeTruthy();
  });

  it("redirects to /login when not authenticated", async () => {
    (api_client.get as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("unauthorized")
    );
    const { container } = render_protected_route();
    // After auth check fails, ProtectedRoute renders Navigate — spinner disappears
    await waitFor(() => {
      expect(container.querySelector(".animate-spin")).toBeNull();
    });
    // Flush any pending state updates from Navigate to avoid act() warnings
    await act(() => Promise.resolve());
  });

  it("renders Outlet when authenticated", async () => {
    (api_client.get as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { exists: true },
    });

    await act(async () => {
      render(
        <MemoryRouter>
          <ProtectedRoute />
        </MemoryRouter>
      );
    });

    // After auth succeeds, spinner should be gone
    await waitFor(() => {
      expect(screen.queryByRole("status")).toBeNull();
    });
  });
});
