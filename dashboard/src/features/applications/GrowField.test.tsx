import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GrowField } from "./GrowField";

/* jsdom lays nothing out: the field's sizes are set by hand, as wrapping
 * would give them, and the size watcher is fired by hand. */
let width = 300;
let textHeight = 40;
let resized: (() => void) | null = null;
const LAYOUT = {
  clientWidth: () => width,
  scrollHeight: () => textHeight,
  clientHeight: () => 20,
  offsetHeight: () => 22,
};

beforeEach(() => {
  width = 300;
  textHeight = 40;
  resized = null;
  for (const [name, read] of Object.entries(LAYOUT)) {
    Object.defineProperty(HTMLTextAreaElement.prototype, name, { configurable: true, get: read });
  }
  vi.stubGlobal("ResizeObserver", class {
    constructor(callback: () => void) { resized = callback; }
    observe() {}
    disconnect() { resized = null; }
  });
});

afterEach(() => {
  for (const name of Object.keys(LAYOUT)) delete (HTMLTextAreaElement.prototype as unknown as Record<string, unknown>)[name];
  vi.unstubAllGlobals();
});

describe("a growing field", () => {
  it("is as tall as its text and its edge", () => {
    render(<GrowField aria-label="Step" value="Email the recruiter" onChange={() => undefined} />);
    expect(screen.getByRole("textbox", { name: "Step" }).style.height).toBe("42px");
  });

  it("grows again when it narrows and the same words wrap onto more lines", () => {
    render(<GrowField aria-label="Step" value="Email the recruiter about the second round" onChange={() => undefined} />);
    const field = screen.getByRole("textbox", { name: "Step" });
    width = 120;
    textHeight = 80;
    act(() => resized?.());
    expect(field.style.height, "the wrapped text is not cut off").toBe("82px");
  });

  it("measures again only for a change of width, so its own new height does not set it off", () => {
    render(<GrowField aria-label="Step" value="Email the recruiter" onChange={() => undefined} />);
    const field = screen.getByRole("textbox", { name: "Step" });
    textHeight = 60;
    act(() => resized?.());
    expect(field.style.height).toBe("42px");
  });
});
