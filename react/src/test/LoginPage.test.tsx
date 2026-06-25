import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
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

function render_login() {
  return render(
    <MemoryRouter>
      <LoginPage />
    </MemoryRouter>
  );
}

describe("LoginPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders login form with inputs", () => {
    render_login();
    expect(screen.getByPlaceholderText("请输入账号")).toBeDefined();
    expect(screen.getByPlaceholderText("请输入密码")).toBeDefined();
    expect(screen.getByRole("button", { name: /登 录/ })).toBeDefined();
  });

  it("shows register link", () => {
    render_login();
    const link = screen.getByText("立即注册");
    expect(link).toBeDefined();
    expect(link.getAttribute("href")).toBe("/register");
  });

  it("calls login on form submit", () => {
    render_login();
    fireEvent.change(screen.getByPlaceholderText("请输入账号"), {
      target: { value: "admin" },
    });
    fireEvent.change(screen.getByPlaceholderText("请输入密码"), {
      target: { value: "123456" },
    });
    fireEvent.submit(screen.getByRole("button", { name: /登 录/ }));
    expect(mock_login).toHaveBeenCalledWith("admin", "123456");
  });

  it("disables submit button when loading", () => {
    mock_is_loading = true;
    mock_error = null;
    render_login();
    const button = screen.getByRole("button", { name: /登录中/ }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    mock_is_loading = false;
  });

  it("displays error message when present", () => {
    mock_is_loading = false;
    mock_error = "密码错误";
    render_login();
    expect(screen.getByText("密码错误")).toBeDefined();
    mock_error = null;
  });
});
