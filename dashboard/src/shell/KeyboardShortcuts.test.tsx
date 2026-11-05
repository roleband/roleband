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
});
