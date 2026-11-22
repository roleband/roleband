import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { msg } from "../../test/msg";
import type { Due } from "./board";
import { DueBadge, dueText } from "./DueBadge";

/* Red says something is wrong. Only a step past its date is: an interview
 * tomorrow, or one that started an hour ago, is a date, not a fault. A due
 * date is words in the row's ink, never a pill. */

const now = new Date(2026, 10, 4, 10, 0);
const at = (days: number, hours = 0) => new Date(now.getTime() + days * 86_400_000 + hours * 3_600_000);
const badge = (due: Due) => {
  render(<DueBadge due={due} now={now} />);
  return screen.getByText(/./);
};
const alarm = (element: HTMLElement) => element.hasAttribute("data-overdue");
const pill = (element: HTMLElement) => [...element.classList].some((name) => name.startsWith("ui-badge"));

describe("the due badge", () => {
  it("marks a step past its date as late, saying how late, in words and not a pill", () => {
    const element = badge({ kind: "step", at: at(-2), on: at(-2) });
    expect(element).toHaveTextContent(msg("applications-card-overdue", { days: 2 }));
    expect(alarm(element)).toBe(true);
    expect(pill(element)).toBe(false);
  });

  it("keeps an interview tomorrow neutral, its words saying it is close", () => {
    const element = badge({ kind: "interview", at: at(1), on: at(1) });
    expect(element).toHaveTextContent(msg("applications-card-due-interview", { offset: 1, date: "" }));
    expect(alarm(element)).toBe(false);
    expect(pill(element)).toBe(false);
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

describe("the words of a due date", () => {
  it("says a late step the same way wherever it is asked, labelled or bare", () => {
    const late: Due = { kind: "step", at: at(-3), on: at(-3) };
    expect(dueText(late, now)).toBe(msg("applications-card-overdue", { days: 3 }));
    expect(dueText(late, now, { bare: true })).toBe(dueText(late, now));
  });

  it("names only the day under a label that already says Due", () => {
    const tomorrow: Due = { kind: "step", at: at(1), on: at(1) };
    expect(dueText(tomorrow, now)).toBe(msg("applications-card-due-step", { offset: 1, date: "" }));
    expect(dueText(tomorrow, now, { bare: true })).toBe(msg("applications-posting-due-day", { offset: 1, date: "" }));
  });
});
