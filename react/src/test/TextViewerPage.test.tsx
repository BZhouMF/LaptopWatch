import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

let _mock_filepath = "";
let _mock_text = "default text";
let _mock_should_fail = false;
let _mock_never_resolve = false;
let _mock_content_length: string | undefined = "100";

vi.mock("../api/client", () => ({
  default: {
    get: vi.fn(() => {
      if (_mock_never_resolve) return new Promise(() => {});
      if (_mock_should_fail) return Promise.reject(new Error("fail"));
      const encoder = new TextEncoder();
      const headers: Record<string, string> = {};
      if (_mock_content_length !== undefined) {
        headers["content-length"] = _mock_content_length;
      }
      return Promise.resolve({
        data: encoder.encode(_mock_text).buffer,
        headers,
      });
    }),
    post: vi.fn(),
  },
}));

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useParams: () => ({ "*": _mock_filepath }),
  };
});

// Mock clipboard
const mock_write_text = vi.fn();
Object.defineProperty(navigator, "clipboard", {
  value: { writeText: mock_write_text },
  writable: true,
  configurable: true,
});

// Mock window.open
const mock_window_open = vi.fn();
window.open = mock_window_open;

import TextViewerPage from "../pages/TextViewerPage";

function render_page(path: string) {
  _mock_filepath = path;
  return render(
    <MemoryRouter initialEntries={[`/file/text/${path}`]}>
      <TextViewerPage />
    </MemoryRouter>
  );
}

describe("TextViewerPage", () => {
  beforeEach(() => {
    _mock_filepath = "";
    _mock_text = "default text";
    _mock_should_fail = false;
    _mock_never_resolve = false;
    _mock_content_length = "100";
    mock_write_text.mockReset();
    mock_window_open.mockReset();
  });

  it("shows loading spinner initially", () => {
    _mock_never_resolve = true;
    render_page("test.txt");
    expect(document.querySelector(".animate-spin")).toBeTruthy();
  });

  it("shows error message on fetch failure", async () => {
    _mock_should_fail = true;
    render_page("test.txt");
    await waitFor(() => {
      expect(screen.getByText("无法加载文件内容")).toBeDefined();
    });
  });

  it("shows error message when filepath is empty", async () => {
    render(
      <MemoryRouter initialEntries={["/file/text/"]}>
        <TextViewerPage />
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(screen.getByText("未指定文件路径")).toBeDefined();
    });
  });

  it("renders text content with line numbers on success", async () => {
    _mock_text = "line one\nline two\nline three";
    _mock_content_length = "100";
    render_page("sample.txt");

    await waitFor(() => {
      expect(screen.getByText("sample.txt")).toBeDefined();
    });
    expect(screen.getByText("line one")).toBeDefined();
    expect(screen.getByText(/总行数: 3/)).toBeDefined();
  });

  it("shows encoding label", async () => {
    _mock_text = "hello";
    render_page("hello.txt");

    await waitFor(() => {
      expect(screen.getByText("编码: UTF-8")).toBeDefined();
    });
  });

  it("shows file size in KB", async () => {
    _mock_text = "x".repeat(2048);
    _mock_content_length = "2048";
    render_page("large.txt");

    await waitFor(() => {
      expect(screen.getByText(/2\.0 KB/)).toBeDefined();
    });
  });

  it("shows file size in B when small", async () => {
    _mock_text = "hi";
    _mock_content_length = undefined; // no content-length header -> uses buffer.byteLength
    render_page("tiny.txt");

    await waitFor(() => {
      expect(screen.getByText(/文件大小:.*B/)).toBeDefined();
    });
  });

  it("copy button copies content and shows feedback", async () => {
    mock_write_text.mockResolvedValueOnce(undefined);
    _mock_text = "copy me";
    render_page("copy_test.txt");

    await waitFor(() => {
      expect(screen.getByText("复制内容")).toBeDefined();
    });

    await act(async () => {
      screen.getByText("复制内容").click();
    });

    expect(mock_write_text).toHaveBeenCalledWith("copy me");
    await waitFor(() => {
      expect(screen.getByText("已复制")).toBeDefined();
    });
    // After 2s, reverts naturally (real timer)
    await waitFor(() => {
      expect(screen.getByText("复制内容")).toBeDefined();
    }, { timeout: 3000 });
  });

  it("download button opens file raw URL", async () => {
    _mock_text = "test";
    render_page("download/file.txt");

    await waitFor(() => {
      expect(screen.getByText("下载文件")).toBeDefined();
    });

    screen.getByText("下载文件").click();
    expect(mock_window_open).toHaveBeenCalledWith(
      "/file/raw/download/file.txt",
      "_blank"
    );
  });

  it("back button is rendered", async () => {
    _mock_text = "test";
    render_page("back_test.txt");

    await waitFor(() => {
      expect(screen.getByText("返回")).toBeDefined();
    });
  });
});
