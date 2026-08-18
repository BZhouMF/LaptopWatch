import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import CategoryBrowsePage from "../pages/CategoryBrowsePage";

function make_media(prefix: string, count: number) {
  return Array.from({ length: count }, (_, i) => ({
    name: `${prefix}${i}.jpg`,
    relative_path: `${prefix}${i}.jpg`,
    is_video: false,
    modify_time: 0,
  }));
}

const root_data = {
  code: 0,
  data: {
    folder_name: "根目录",
    folder_path: "",
    parent_path: "",
    categories: [
      { name: "子分类A", path: "subA", files: make_media("a", 10), total_files: 10, has_more: false },
    ],
    root_files: [],
    total_categories: 1,
  },
};

const sub_data = {
  code: 0,
  data: {
    folder_name: "子分类A",
    folder_path: "subA",
    parent_path: "",
    categories: [],
    root_files: make_media("img", 3),
    total_categories: 0,
  },
};

vi.mock("../api/client", () => ({
  default: {
    get: vi.fn((url: string, opts?: { params?: { path?: string } }) => {
      if (url === "/api/mode") {
        return Promise.resolve({ data: { page_first: 28, page_load: 28 } });
      }
      if (url === "/category/data") {
        const path = opts?.params?.path ?? "";
        return Promise.resolve({ data: path ? sub_data : root_data });
      }
      if (url === "/category/grid_more") {
        return Promise.resolve({ data: { code: 0, data: sub_data.data.root_files, has_more: false } });
      }
      return Promise.reject(new Error("unknown"));
    }),
  },
}));

describe("CategoryBrowsePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.scrollTo = vi.fn();
  });

  afterEach(() => {
    delete (window as { scrollY?: number }).scrollY;
  });

  it("module can be imported without error", async () => {
    const mod = await import("../pages/CategoryBrowsePage");
    expect(mod.default).toBeDefined();
  });

  it("exports a default component", async () => {
    const mod = await import("../pages/CategoryBrowsePage");
    expect(typeof mod.default).toBe("function");
  });

  it("restores category page scroll position after returning from 显示更多", async () => {
    Object.defineProperty(window, "scrollY", { configurable: true, value: 500 });

    render(
      <MemoryRouter>
        <CategoryBrowsePage />
      </MemoryRouter>
    );

    // 根分类视图渲染完成
    await waitFor(() => {
      expect(screen.getByText("根目录")).toBeDefined();
    });

    // 用户已向下滚动 → 点击「显示更多」进入该分类的 grid 视图
    fireEvent.click(screen.getByText("显示更多"));

    // grid 视图渲染（出现返回按钮）
    await waitFor(() => {
      expect(screen.getByText("← 返回")).toBeDefined();
    });

    // 点击「返回」→ 回到分类视图并恢复离开前的滚动位置
    fireEvent.click(screen.getByText("← 返回"));

    await waitFor(() => {
      expect(window.scrollTo).toHaveBeenCalledWith(0, 500);
    });
  });
});
