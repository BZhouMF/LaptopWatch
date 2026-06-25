import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import NotFoundPage from "../pages/NotFoundPage";

const mock_navigate = vi.fn();

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mock_navigate,
  };
});

describe("NotFoundPage", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mock_navigate.mockClear();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("displays countdown starting from 3", () => {
    render(
      <MemoryRouter>
        <NotFoundPage />
      </MemoryRouter>
    );
    expect(screen.getByText(/3 秒后自动返回/)).toBeDefined();
  });

  it("counts down each second", () => {
    render(
      <MemoryRouter>
        <NotFoundPage />
      </MemoryRouter>
    );

    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(screen.getByText(/2 秒后自动返回/)).toBeDefined();

    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(screen.getByText(/1 秒后自动返回/)).toBeDefined();
  });

  it("navigates to / after countdown", () => {
    render(
      <MemoryRouter>
        <NotFoundPage />
      </MemoryRouter>
    );

    act(() => {
      vi.advanceTimersByTime(3000);
    });

    expect(mock_navigate).toHaveBeenCalledWith("/", { replace: true });
  });

  it("shows error message", () => {
    render(
      <MemoryRouter>
        <NotFoundPage />
      </MemoryRouter>
    );
    expect(screen.getByText("路径不存在")).toBeDefined();
  });
});
