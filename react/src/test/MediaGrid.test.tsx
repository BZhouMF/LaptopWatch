import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import MediaGrid from "../components/MediaGrid";

vi.mock("../api/client", () => ({
  default: {
    get: vi.fn(),
  },
}));

import api_client from "../api/client";

describe("MediaGrid", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows spinner while loading", () => {
    (api_client.get as ReturnType<typeof vi.fn>).mockReturnValue(
      new Promise(() => {})
    );
    render(<MediaGrid page_first={12} page_load={24} is_random={false} />);
    // Should show a spinning element
    const el = document.querySelector(".animate-spin");
    expect(el).toBeTruthy();
  });

  it("shows empty state when no items", async () => {
    (api_client.get as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { data: [], has_more: false, total: 0 },
    });
    render(<MediaGrid page_first={12} page_load={24} is_random={false} />);

    await waitFor(() => {
      expect(screen.getByText("没有找到媒体文件")).toBeDefined();
    });
  });

  it("renders media items", async () => {
    (api_client.get as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: {
        data: [
          {
            name: "video.mp4",
            relative_path: "videos/video.mp4",
            is_video: true,
            modify_time: 1700000000,
            size_str: "10.5MB",
            duration_str: "03:25",
          },
          {
            name: "photo.jpg",
            relative_path: "photos/photo.jpg",
            is_video: false,
            modify_time: 1700000000,
            size_str: "2.1MB",
          },
        ],
        has_more: false,
        total: 2,
      },
    });
    render(<MediaGrid page_first={12} page_load={24} is_random={false} />);

    await waitFor(() => {
      expect(screen.getByText("video.mp4")).toBeDefined();
      expect(screen.getByText("photo.jpg")).toBeDefined();
    });
  });

  it("shows pagination when has_more is true", async () => {
    (api_client.get as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: {
        data: [{ name: "v.mp4", relative_path: "v.mp4", is_video: true, modify_time: 1 }],
        has_more: true,
        total: 50,
      },
    });
    render(<MediaGrid page_first={12} page_load={24} is_random={false} />);

    await waitFor(() => {
      expect(screen.getByText("下一页")).toBeDefined();
    });
  });
});
