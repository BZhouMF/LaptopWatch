import { describe, it, expect, vi, beforeEach } from "vitest";

const mock_axios = {
  create: vi.fn(() => ({
    interceptors: {
      response: {
        use: vi.fn(),
      },
    },
  })),
};

vi.mock("axios", () => ({ default: mock_axios }));

describe("api_client", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.resetModules();
  });

  it("creates axios instance with credentials", async () => {
    await import("../api/client");
    expect(mock_axios.create).toHaveBeenCalledWith(
      expect.objectContaining({
        withCredentials: true,
        timeout: 30000,
      })
    );
  });

  it("registers a response interceptor", async () => {
    const interceptor_use = vi.fn();
    mock_axios.create.mockReturnValue({
      interceptors: { response: { use: interceptor_use } },
    });

    await import("../api/client");
    expect(interceptor_use).toHaveBeenCalled();
  });

  it("redirects to /login on 401 outside /login page", async () => {
    // jsdom doesn't implement navigation, mock window.location before the interceptor runs
    const location_mock = { href: "", pathname: "/" };
    Object.defineProperty(window, "location", {
      value: location_mock,
      writable: true,
      configurable: true,
    });

    const interceptor_use = vi.fn();
    mock_axios.create.mockReturnValue({
      interceptors: { response: { use: interceptor_use } },
    });

    vi.resetModules();
    await import("../api/client");

    const error_handler = interceptor_use.mock.calls[0]?.[1];
    expect(error_handler).toBeDefined();

    const fake_error = {
      response: { status: 401 },
    };

    error_handler(fake_error)?.catch(() => {});

    expect(location_mock.href).toBe("/login?redirect=%2F");
  });
});
