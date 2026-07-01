import { describe, it, expect, vi } from "vitest";

vi.mock("../api/client", () => ({
  default: { get: vi.fn(() => new Promise(() => {})), post: vi.fn() },
}));

describe("CategoryBrowsePage", () => {
  it("module can be imported without error", async () => {
    const mod = await import("../pages/CategoryBrowsePage");
    expect(mod.default).toBeDefined();
  });

  it("exports a default component", async () => {
    const mod = await import("../pages/CategoryBrowsePage");
    expect(typeof mod.default).toBe("function");
  });
});
