import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import SelectionBar from "../components/browse/SelectionBar";

describe("SelectionBar", () => {
  const default_props = {
    count: 3,
    on_download_merge: vi.fn(),
    on_download_separate: vi.fn(),
    on_cancel: vi.fn(),
  };

  it("displays selected count", () => {
    render(<SelectionBar {...default_props} />);
    expect(screen.getByText("3")).toBeDefined();
  });

  it("disables download buttons when count is 0", () => {
    render(<SelectionBar {...default_props} count={0} />);
    const merge_btn = screen.getByText("合并下载");
    const separate_btn = screen.getByText("分别下载");
    expect((merge_btn as HTMLButtonElement).disabled).toBe(true);
    expect((separate_btn as HTMLButtonElement).disabled).toBe(true);
  });

  it("enables download buttons when count > 0", () => {
    render(<SelectionBar {...default_props} />);
    const merge_btn = screen.getByText("合并下载") as HTMLButtonElement;
    expect(merge_btn.disabled).toBe(false);
  });

  it("calls on_download_merge when merge button clicked", () => {
    const on_download_merge = vi.fn();
    render(<SelectionBar {...default_props} on_download_merge={on_download_merge} />);
    fireEvent.click(screen.getByText("合并下载"));
    expect(on_download_merge).toHaveBeenCalled();
  });

  it("calls on_download_separate when separate button clicked", () => {
    const on_download_separate = vi.fn();
    render(
      <SelectionBar {...default_props} on_download_separate={on_download_separate} />
    );
    fireEvent.click(screen.getByText("分别下载"));
    expect(on_download_separate).toHaveBeenCalled();
  });

  it("calls on_cancel when cancel button clicked", () => {
    const on_cancel = vi.fn();
    render(<SelectionBar {...default_props} on_cancel={on_cancel} />);
    fireEvent.click(screen.getByText("取消"));
    expect(on_cancel).toHaveBeenCalled();
  });
});
