import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import PreviewModal from "../components/browse/PreviewModal";

describe("PreviewModal", () => {
  const default_props = {
    url: "/media/serve_media/test.jpg",
    name: "test.jpg",
    is_video: false,
    download_url: "/file/view/test.jpg",
    on_close: vi.fn(),
  };

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders image for non-video", () => {
    render(<PreviewModal {...default_props} />);
    const img = screen.getByRole("img");
    expect(img).toBeDefined();
    expect(img.getAttribute("src")).toBe("/media/serve_media/test.jpg");
  });

  it("renders video element when is_video=true", () => {
    render(<PreviewModal {...default_props} is_video={true} />);
    const video = document.querySelector("video");
    expect(video).toBeTruthy();
  });

  it("calls on_close when close button clicked", () => {
    vi.useFakeTimers();
    const on_close = vi.fn();
    render(<PreviewModal {...default_props} on_close={on_close} />);
    fireEvent.click(screen.getByLabelText("关闭"));
    vi.advanceTimersByTime(200);
    expect(on_close).toHaveBeenCalled();
    vi.useRealTimers();
  });

  it("calls on_close on Escape key", () => {
    vi.useFakeTimers();
    const on_close = vi.fn();
    render(<PreviewModal {...default_props} on_close={on_close} />);
    fireEvent.keyDown(document, { key: "Escape" });
    vi.advanceTimersByTime(200);
    expect(on_close).toHaveBeenCalled();
    vi.useRealTimers();
  });

  it("calls on_close on backdrop click", () => {
    vi.useFakeTimers();
    const on_close = vi.fn();
    const { container } = render(
      <PreviewModal {...default_props} on_close={on_close} />
    );
    const backdrop = container.firstElementChild;
    expect(backdrop).toBeTruthy();
    if (backdrop) {
      fireEvent.click(backdrop);
    }
    vi.advanceTimersByTime(200);
    expect(on_close).toHaveBeenCalled();
    vi.useRealTimers();
  });

  it("renders download link", () => {
    render(<PreviewModal {...default_props} />);
    const link = screen.getByText("下载");
    expect(link).toBeDefined();
    expect(link.tagName).toBe("A");
  });

  it("shows file name", () => {
    render(<PreviewModal {...default_props} />);
    expect(screen.getByText("test.jpg")).toBeDefined();
  });
});
