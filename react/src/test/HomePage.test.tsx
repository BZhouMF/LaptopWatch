import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import HomePage from "../pages/HomePage";

vi.mock("../api/client", () => ({
  default: {
    get: vi.fn((url: string) => {
      if (url === "/api/mode") {
        return Promise.resolve({
          data: {
            run_mode: "normal",
            category_browse: false,
            random_mode: false,
            page_first: 12,
            page_load: 24,
          },
        });
      }
      if (url === "/api/drives") {
        return Promise.resolve({ data: { drives: ["C"] } });
      }
      return Promise.reject(new Error("unknown"));
    }),
  },
}));

vi.mock("../components/MediaGrid", () => ({
  default: ({ page_first, page_load, is_random }: {
    page_first: number; page_load: number; is_random: boolean;
  }) => (
    <div data-testid="media-grid">
      grid-{page_first}-{page_load}-{String(is_random)}
    </div>
  ),
}));

vi.mock("../pages/MediaPlayerPage", () => ({
  default: () => <div data-testid="media-player-page" />,
}));

vi.mock("../pages/BrowsePage", () => ({
  default: () => <div data-testid="browse-page" />,
}));

describe("HomePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders drive grid in normal mode", async () => {
    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText("C")).toBeDefined();
    });
  });

  it("renders MediaGrid in video mode", async () => {
    const { default: api_client } = await import("../api/client");
    (api_client.get as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      if (url === "/api/mode") {
        return Promise.resolve({
          data: {
            run_mode: "video",
            category_browse: false,
            random_mode: false,
            page_first: 8,
            page_load: 16,
          },
        });
      }
      return Promise.reject(new Error("unknown"));
    });

    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId("media-grid")).toBeDefined();
    });
  });

  it("shows loading spinner initially", async () => {
    const { default: api_client } = await import("../api/client");
    // Override to never resolve — spinner stays visible, no async state update escapes
    (api_client.get as ReturnType<typeof vi.fn>).mockReturnValue(
      new Promise(() => {})
    );
    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>
    );
    const spinner = document.querySelector(".animate-spin");
    expect(spinner).toBeTruthy();
  });
});
