import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { InfoTip } from "./InfoTip";

/* Every stylesheet under src/ but InfoTip's own, read from disk: the test
   runner hands a CSS import to a test as an empty string. */
const here = dirname(fileURLToPath(import.meta.url));
const src = join(here, "..");
const STYLESHEETS: Record<string, string> = Object.fromEntries(
  readdirSync(src, { recursive: true, encoding: "utf8" })
    .filter((path) => path.endsWith(".css") && join(src, path) !== join(here, "InfoTip.css"))
    .map((path) => [relative(src, join(src, path)), readFileSync(join(src, path), "utf8")]),
);

const isOpen = (tip: HTMLElement) => tip.hasAttribute("data-open");

describe("InfoTip", () => {
  it("is described by the tip, which opens on focus and closes when focus leaves", async () => {
    const user = userEvent.setup();
    render(
      <>
        <InfoTip label="About the split">Base is the fixed part.</InfoTip>
        <button type="button">Next</button>
      </>,
    );
    const mark = screen.getByRole("button", { name: "About the split" });
    expect(mark).toHaveAccessibleDescription("Base is the fixed part.");
    const tip = document.getElementById(mark.getAttribute("aria-describedby")!)!;
    expect(tip).toHaveAttribute("role", "tooltip");
    expect(isOpen(tip)).toBe(false);

    await user.tab();
    expect(mark).toHaveFocus();
    expect(isOpen(tip)).toBe(true);
    await user.tab();
    expect(isOpen(tip)).toBe(false);
  });

  it("opens while the pointer is on it, and stays open for focus after the pointer leaves", () => {
    render(<InfoTip label="About the split">Base is the fixed part.</InfoTip>);
    const mark = screen.getByRole("button", { name: "About the split" });
    const tip = screen.getByRole("tooltip", { hidden: true });
    const wrap = mark.parentElement!;

    fireEvent.pointerEnter(wrap);
    expect(isOpen(tip)).toBe(true);
    fireEvent.pointerLeave(wrap);
    expect(isOpen(tip)).toBe(false);

    fireEvent.focus(mark);
    fireEvent.pointerEnter(wrap);
    fireEvent.pointerLeave(wrap);
    expect(isOpen(tip), "focus still holds it open").toBe(true);
  });

  it("is the only place a tip is placed: no stylesheet positions it from outside", () => {
    // A screen that needs the tip elsewhere asks the component (`align`,
    // `hangFrom`); a rule from outside fights the placement the component
    // computes, and is cut off by the boxes the component escapes.
    const placing = Object.entries(STYLESHEETS)
      .filter(([, css]) => /\.info-tip-popover\b/.test(css.replace(/\/\*[\s\S]*?\*\//g, "")))
      .map(([path]) => path);
    // The scan read real rules: the mark's own margin tweaks are styled from outside.
    expect(Object.values(STYLESHEETS).some((css) => /\.info-tip\s*\{/.test(css))).toBe(true);
    expect(placing).toEqual([]);
  });
});
