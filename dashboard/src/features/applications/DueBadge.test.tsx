import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { msg } from "../../test/msg";
import type { Due } from "./board";
import { DueBadge } from "./DueBadge";

/* Red says something is wrong. Only a step past its date is: an interview
 * tomorrow, or one that started an hour ago, is a date, not a fault. */

const now = new Date(2026, 10, 4, 10, 0);
const at = (days: number, hours = 0) => new Date(now.getTime() + days * 86_400_000 + hours * 3_600_000);
const badge = (due: Due) => {
  render(<DueBadge due={due} now={now} />);
  return screen.getByText(/./);
};
const alarm = (element: HTMLElement) => element.classList.contains("ui-badge-danger");

describe("the due badge", () => {
  it("paints a step past its date red and solid, saying how late it is", () => {
    const element = badge({ kind: "step", at: at(-2), on: at(-2) });
    expect(element).toHaveTextContent(msg("applications-card-overdue", { days: 2 }));
    expect(alarm(element)).toBe(true);
    expect(element).toHaveClass("ui-badge-solid");
  });

  it("keeps an interview tomorrow neutral, its words saying it is close", () => {
    const element = badge({ kind: "interview", at: at(1), on: at(1) });
    expect(element).toHaveTextContent(msg("applications-card-due-interview", { offset: 1, date: "" }));
    expect(alarm(element)).toBe(false);
    expect(element).toHaveClass("ui-badge-neutral", "ui-badge-tint");
  });

  it("keeps a step due later today neutral", () => {
    const element = badge({ kind: "step", at: at(0, 3), on: at(0, 3) });
    expect(element).toHaveTextContent(msg("applications-card-due-step", { offset: 0, date: "" }));
    expect(alarm(element)).toBe(false);
  });

  it("never calls an interview that has started overdue", () => {
    const element = badge({ kind: "interview", at: at(0, -1), on: at(0, -1) });
    expect(element).toHaveTextContent(msg("applications-card-due-interview", { offset: 0, date: "" }));
    expect(alarm(element)).toBe(false);
  });
});
