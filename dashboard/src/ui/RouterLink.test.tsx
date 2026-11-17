import { createRef } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { Button } from "./Button";
import { RouterLink, type RouterLinkProps } from "./RouterLink";

/* Contracts for the in-app link in Button's look (docs/ui.md, Controls). It
 * must stay an anchor with an address, so the browser's own link behaviour
 * (open in a new tab, copy the address) keeps working, and it must wear
 * exactly the classes `Button` wears for the same variant and size.
 */

const VARIANTS = ["primary", "ghost", "icon", "link", "danger"] as const;

function Where() {
  const { pathname, state } = useLocation();
  return (
    <>
      <output aria-label="location">{pathname}</output>
      <output aria-label="state">{JSON.stringify(state)}</output>
    </>
  );
}

function renderAt(props: RouterLinkProps) {
  return render(
    <MemoryRouter initialEntries={["/from"]}>
      <RouterLink {...props} />
      <Routes>
        <Route path="*" element={<Where />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("RouterLink", () => {
  it("is a link with an address, not a button", () => {
    renderAt({ to: "/companies", children: "Follow companies" });
    const el = screen.getByRole("link", { name: "Follow companies" });
    expect(el.tagName).toBe("A");
    expect(el).toHaveAttribute("href", "/companies");
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("moves to its address on a plain click", () => {
    renderAt({ to: "/companies", children: "Follow companies" });
    fireEvent.click(screen.getByRole("link", { name: "Follow companies" }));
    expect(screen.getByRole("status", { name: "location" })).toHaveTextContent("/companies");
  });

  it.each([
    ["metaKey", { metaKey: true }],
    ["ctrlKey", { ctrlKey: true }],
    ["middle button", { button: 1 }],
  ])("leaves a %s click to the browser, so it opens in a new tab", (_, init) => {
    renderAt({ to: "/companies", children: "Follow companies" });
    const notPrevented = fireEvent.click(screen.getByRole("link", { name: "Follow companies" }), init);
    expect(notPrevented).toBe(true);
    expect(screen.getByRole("status", { name: "location" })).toHaveTextContent("/from");
  });

  it.each(VARIANTS)("wears Button's classes for the %s variant", (variant) => {
    render(
      <MemoryRouter>
        <RouterLink to="/x" variant={variant} size="sm">Go</RouterLink>
        <Button variant={variant} size="sm">Act</Button>
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: "Go" }).className)
      .toBe(screen.getByRole("button", { name: "Act" }).className);
  });

  it("defaults to the ghost rank at md, as Button does", () => {
    renderAt({ to: "/x", children: "Back" });
    const el = screen.getByRole("link", { name: "Back" });
    expect(el.className).toContain("ui-btn-ghost");
    expect(el.className).toContain("ui-btn-md");
  });

  it("gives link no size class: it is text, and inherits its line", () => {
    renderAt({ to: "/x", variant: "link", size: "lg", children: "Change what you look for" });
    const el = screen.getByRole("link", { name: "Change what you look for" });
    expect(el.className).toContain("ui-btn-link");
    expect(el.className).not.toMatch(/ui-btn-(sm|md|lg)/);
  });

  it("carries the caller's className and router state without dropping its own", () => {
    renderAt({ to: "/x", className: "app-page-back", state: { from: "board" }, children: "Back" });
    const el = screen.getByRole("link", { name: "Back" });
    expect(el.className).toContain("ui-btn-ghost");
    expect(el.className).toContain("app-page-back");
    fireEvent.click(el);
    expect(screen.getByRole("status", { name: "state" })).toHaveTextContent('{"from":"board"}');
  });

  it("forwards its ref to the anchor", () => {
    const ref = createRef<HTMLAnchorElement>();
    render(
      <MemoryRouter>
        <RouterLink ref={ref} to="/x">Go</RouterLink>
      </MemoryRouter>,
    );
    expect(ref.current).toBe(screen.getByRole("link", { name: "Go" }));
  });
});
