import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import LoginPage from "../pages/LoginPage";

const mock_login = vi.fn();
const mock_clear_error = vi.fn();

let mock_is_loading = false;
let mock_error: string | null = null;

vi.mock("../contexts/AuthContext", () => ({
  useAuth: () => ({
    login: mock_login,
    logout: vi.fn(),
    is_loading: mock_is_loading,
    error: mock_error,
    clear_error: mock_clear_error,
  }),
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
}));

// 模拟 api_client: 让 check_path 返回 401（无有效 session），触发登录表单渲染
vi.mock("../api/client", () => ({
  default: {
    get: vi.fn().mockRejectedValue({ response: { status: 401 } }),
  },
}));

async function render_login() {
  const result = render(
    <MemoryRouter>
      <LoginPage />
    </MemoryRouter>
  );
  // 等待 check_path 的异步调用完成后表单才显示
  await waitFor(() => {
    expect(screen.queryByText("检查登录状态...")).toBeNull();
  });
  return result;
}

describe("LoginPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders login form with inputs", async () => {
    await render_login();
    expect(screen.getByPlaceholderText("请输入账号")).toBeDefined();
    expect(screen.getByPlaceholderText("请输入密码")).toBeDefined();
    expect(screen.getByRole("button", { name: /登 录/ })).toBeDefined();
  });

  it("shows register link", async () => {
    await render_login();
    const link = screen.getByText("立即注册");
    expect(link).toBeDefined();
    expect(link.getAttribute("href")).toBe("/register");
  });

  it("calls login on form submit", async () => {
    await render_login();
    fireEvent.change(screen.getByPlaceholderText("请输入账号"), {
      target: { value: "admin" },
    });
    fireEvent.change(screen.getByPlaceholderText("请输入密码"), {
      target: { value: "123456" },
    });
    fireEvent.submit(screen.getByRole("button", { name: /登 录/ }));
    expect(mock_login).toHaveBeenCalledWith("admin", "123456");
  });

  it("disables submit button when loading", async () => {
    mock_is_loading = true;
    mock_error = null;
    await render_login();
    const button = screen.getByRole("button", { name: /登录中/ }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    mock_is_loading = false;
  });

  it("displays error message when present", async () => {
    mock_is_loading = false;
    mock_error = "密码错误";
    await render_login();
    expect(screen.getByText("密码错误")).toBeDefined();
    mock_error = null;
  });
});
