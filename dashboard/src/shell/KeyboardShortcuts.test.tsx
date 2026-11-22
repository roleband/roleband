import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { msg } from "../test/msg";
import { KeyboardShortcuts } from "./KeyboardShortcuts";

describe("the shortcuts sheet", () => {
  it("lists the pipeline's keys in a group of their own: M, the stage numbers and I", () => {
    render(<KeyboardShortcuts onClose={() => {}} />);
    const group = screen.getByRole("heading", { name: msg("shortcuts-keyboard-shortcuts-pipeline") }).closest("section")!;
    const rows = within(group).getAllByRole("term").map((term) => [term.textContent, term.nextElementSibling?.textContent]);
    expect(rows).toEqual([
      ["m", msg("shortcuts-keyboard-shortcuts-change-stage")],
      ["1–5", msg("shortcuts-keyboard-shortcuts-pick-stage")],
      ["i", msg("shortcuts-keyboard-shortcuts-add-interview")],
    ]);
  });

  it("lists J and K once, as the keys between a list's rows, and has no group for stepping between postings", () => {
    render(<KeyboardShortcuts onClose={() => {}} />);
    const group = screen.getByRole("heading", { name: msg("shortcuts-keyboard-shortcuts-on-a-role-in-a") }).closest("section")!;
    const terms = within(group).getAllByRole("term").map((term) => term.textContent);
    expect(terms.slice(0, 2)).toEqual(["j↓", "k↑"]);
    for (const key of ["j", "k"]) expect(screen.getAllByText(key, { exact: true })).toHaveLength(1);
    expect(screen.queryByText(/in the list/i)).toBeNull();
    expect(screen.getAllByRole("heading", { level: 3 })).toHaveLength(4);
  });
});
