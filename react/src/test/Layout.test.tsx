import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Layout from "../components/Layout";

describe("Layout", () => {
  it("renders with correct CSS classes", () => {
    const { container } = render(
      <MemoryRouter>
        <Layout />
      </MemoryRouter>
    );
    const root = container.firstElementChild;
    expect(root).toBeTruthy();
    expect(root!.className).toContain("flex");
    expect(root!.className).toContain("min-h-screen");
    expect(root!.className).toContain("bg-bg-primary");
    expect(root!.className).toContain("text-text-primary");
  });

  it("renders Outlet inside root div", () => {
    const { container } = render(
      <MemoryRouter initialEntries={["/"]}>
        <Layout />
      </MemoryRouter>
    );
    const root = container.firstElementChild;
    expect(root).toBeTruthy();
    expect(root!.className).toContain("bg-bg-primary");
  });
});
