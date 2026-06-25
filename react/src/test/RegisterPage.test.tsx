import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import RegisterPage from "../pages/RegisterPage";

const mock_navigate = vi.fn();

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mock_navigate,
  };
});

vi.mock("../api/client", () => ({
  default: {
    post: vi.fn(),
  },
}));

import api_client from "../api/client";

function render_register() {
  return render(
    <MemoryRouter>
      <RegisterPage />
    </MemoryRouter>
  );
}

describe("RegisterPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders registration form", () => {
    render_register();
    expect(screen.getByPlaceholderText("请输入账号")).toBeDefined();
    expect(screen.getByPlaceholderText("请输入密码")).toBeDefined();
    expect(screen.getByPlaceholderText("请再次输入密码")).toBeDefined();
    expect(screen.getByRole("button", { name: /注 册/ })).toBeDefined();
  });

  it("shows validation error for invalid chars in account", async () => {
    render_register();
    fireEvent.change(screen.getByPlaceholderText("请输入账号"), {
      target: { value: "test<>name" },
    });
    fireEvent.submit(screen.getByRole("button", { name: /注 册/ }));
    expect(
      await screen.findByText("账号包含不允许的字符")
    ).toBeDefined();
  });

  it("shows validation error for password mismatch", async () => {
    render_register();
    fireEvent.change(screen.getByPlaceholderText("请输入账号"), {
      target: { value: "testuser" },
    });
    fireEvent.change(screen.getByPlaceholderText("请输入密码"), {
      target: { value: "abc123" },
    });
    fireEvent.change(screen.getByPlaceholderText("请再次输入密码"), {
      target: { value: "different" },
    });
    fireEvent.submit(screen.getByRole("button", { name: /注 册/ }));
    expect(
      await screen.findByText("两次输入的密码不一致")
    ).toBeDefined();
  });

  it("shows server error on failed registration", async () => {
    (api_client.post as ReturnType<typeof vi.fn>).mockRejectedValue({
      response: { data: { msg: "服务器错误" } },
    });

    render_register();
    fireEvent.change(screen.getByPlaceholderText("请输入账号"), {
      target: { value: "legituser" },
    });
    fireEvent.change(screen.getByPlaceholderText("请输入密码"), {
      target: { value: "abc123!@#" },
    });
    fireEvent.change(screen.getByPlaceholderText("请再次输入密码"), {
      target: { value: "abc123!@#" },
    });
    fireEvent.submit(screen.getByRole("button", { name: /注 册/ }));

    await waitFor(() => {
      expect(screen.getByText("服务器错误")).toBeDefined();
    });
  });

  it("navigates to /login on success", async () => {
    (api_client.post as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { code: 0 },
    });

    render_register();
    fireEvent.change(screen.getByPlaceholderText("请输入账号"), {
      target: { value: "legituser" },
    });
    fireEvent.change(screen.getByPlaceholderText("请输入密码"), {
      target: { value: "abc123!@#" },
    });
    fireEvent.change(screen.getByPlaceholderText("请再次输入密码"), {
      target: { value: "abc123!@#" },
    });
    fireEvent.submit(screen.getByRole("button", { name: /注 册/ }));

    await waitFor(() => {
      expect(mock_navigate).toHaveBeenCalledWith("/login", { replace: true });
    });
  });
});
