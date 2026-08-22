import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import MediaGrid from "../components/MediaGrid";

vi.mock("../api/client", () => ({
  default: {
    get: vi.fn(),
  },
}));

import api_client from "../api/client";

// jsdom 不实现 location 导航，替换为可写对象以捕获跳转目标
const save_location = window.location;

function mock_window_location(): { href: string } {
  const location_mock = { href: "" };
  Object.defineProperty(window, "location", {
    configurable: true,
    writable: true,
    value: location_mock,
  });
  return location_mock;
}

function restore_window_location() {
  Object.defineProperty(window, "location", {
    configurable: true,
    writable: true,
    value: save_location,
  });
}

describe("MediaGrid", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mock_window_location();
  });

  afterEach(() => {
    restore_window_location();
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

  it("video click opens the native browser player (serve_media URL)", async () => {
    (api_client.get as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: {
        data: [
          { name: "video.mp4", relative_path: "videos/video.mp4", is_video: true, modify_time: 1700000000 },
        ],
        has_more: false,
        total: 1,
      },
    });
    render(<MediaGrid page_first={12} page_load={24} is_random={false} />);

    await waitFor(() => {
      expect(screen.getByText("video.mp4")).toBeDefined();
    });
    fireEvent.click(screen.getByText("video.mp4"));

    const location_mock = window.location as unknown as { href: string };
    expect(location_mock.href).toBe("/media/player?path=videos%2Fvideo.mp4");
  });

  it("image click opens the custom player page", async () => {
    (api_client.get as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: {
        data: [
          { name: "photo.jpg", relative_path: "photos/photo.jpg", is_video: false, modify_time: 1700000000 },
        ],
        has_more: false,
        total: 1,
      },
    });
    render(<MediaGrid page_first={12} page_load={24} is_random={false} />);

    await waitFor(() => {
      expect(screen.getByText("photo.jpg")).toBeDefined();
    });
    fireEvent.click(screen.getByText("photo.jpg"));

    const location_mock = window.location as unknown as { href: string };
    expect(location_mock.href).toBe("/media/player?path=photos%2Fphoto.jpg");
  });
});
