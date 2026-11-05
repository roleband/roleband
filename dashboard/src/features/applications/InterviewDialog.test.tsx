import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ApplicationInterview } from "../../api";
import { applicationCardFixture } from "../../test/fixtures";
import { companyName } from "../../format";
import { msg } from "../../test/msg";
import { InterviewDialog } from "./InterviewDialog";

/* The interview form asks for when first: a day from the month, then a time
 * or none yet. The round and the format wait under Optional, one click each.
 * What it sends is the contract: the reader's own day and clock. */

const card = applicationCardFixture({ job_id: 2, stage: "applied", title: "Principal Engineering Manager", company: "stripe" });

beforeEach(() => {
  // Only the date is fixed: the clock the month opens on and marks as today.
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(2026, 10, 4, 10, 0));
});
afterEach(() => vi.useRealTimers());

function open(props: Partial<Parameters<typeof InterviewDialog>[0]> = {}) {
  const onSubmit = vi.fn();
  const onCancel = vi.fn();
  render(<InterviewDialog card={card} onSubmit={onSubmit} onCancel={onCancel} {...props} />);
  const dialog = screen.getByRole("dialog");
  return { dialog, onSubmit, onCancel };
}
const add = () => screen.getByRole("button", { name: msg("applications-interview-add") });
const times = (dialog: HTMLElement) => within(dialog).getByRole("group", { name: msg("applications-interview-times") });
const summary = (dialog: HTMLElement) => dialog.querySelector(".app-interview-summary")!.textContent;

describe("the heading", () => {
  it("names the role alone when a move asks for the interview, as when one is added", () => {
    const { dialog } = open({ moving: true });
    // Names are wrapped in direction marks in the rendered line.
    const note = dialog.querySelector(".app-interview-note")!.textContent!.replace(/[\u2068\u2069]/g, "");
    expect(note).toBe(msg("applications-interview-for", { title: card.title, company: companyName(card.company) }));
    expect(dialog.textContent, "no sentence about the move under the question").not.toMatch(/moves to/i);
  });
});

describe("when", () => {
  it("asks for the day first: without one it says so and sends nothing", async () => {
    const { dialog, onSubmit } = open();
    expect(summary(dialog)).toBe(msg("applications-interview-pick-day"));
    await userEvent.click(add());
    expect(within(dialog).getByRole("alert")).toHaveTextContent(msg("applications-interview-day-missing"));
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("sends the day picked in the month and the time picked beside it, at the reader's own clock", async () => {
    const { dialog, onSubmit } = open();
    expect(within(dialog).getByRole("button", { name: "Wed, Nov 4" })).toHaveAttribute("aria-current", "date");
    await userEvent.click(within(dialog).getByRole("button", { name: "Thu, Nov 12" }));
    await userEvent.click(within(times(dialog)).getByRole("button", { name: "2:30 PM" }));

    expect(within(dialog).getByRole("button", { name: "Thu, Nov 12" })).toHaveAttribute("aria-pressed", "true");
    expect(within(times(dialog)).getByRole("button", { name: "2:30 PM" })).toHaveAttribute("aria-pressed", "true");
    expect(within(dialog).getByLabelText(msg("applications-interview-time"))).toHaveValue("2:30 PM");
    expect(summary(dialog)).toBe("Thu, Nov 12 · 2:30 PM");

    await userEvent.click(add());
    expect(onSubmit).toHaveBeenCalledWith({
      label: msg("applications-interview-default-label"),
      scheduled_at: new Date(2026, 10, 12, 14, 30).toISOString(),
      all_day: false,
      format: null,
      link: null,
    });
  });

  it("reads a typed time, and holds a time it cannot read until it is fixed", async () => {
    const { dialog, onSubmit } = open();
    await userEvent.click(within(dialog).getByRole("button", { name: "Fri, Nov 6" }));
    const field = within(dialog).getByLabelText(msg("applications-interview-time"));

    await userEvent.type(field, "25:00");
    await userEvent.click(add());
    expect(within(dialog).getByRole("alert")).toHaveTextContent(msg("applications-interview-time-invalid", { example: "2:30 PM" }));
    expect(field).toHaveAttribute("aria-invalid", "true");
    expect(onSubmit).not.toHaveBeenCalled();

    await userEvent.clear(field);
    await userEvent.type(field, "9am");
    await userEvent.click(add());
    expect(onSubmit.mock.calls[0][0]).toMatchObject({ scheduled_at: new Date(2026, 10, 6, 9, 0).toISOString(), all_day: false });
  });

  it("sends a day with No time yet as an all-day interview at the reader's midnight", async () => {
    const { dialog, onSubmit } = open();
    await userEvent.click(within(dialog).getByRole("button", { name: "Fri, Nov 6" }));
    await userEvent.click(within(times(dialog)).getByRole("button", { name: "4:00 PM" }));
    await userEvent.click(within(times(dialog)).getByRole("button", { name: msg("applications-interview-no-time") }));
    expect(within(dialog).getByLabelText(msg("applications-interview-time"))).toHaveValue("");
    expect(summary(dialog)).toBe("Fri, Nov 6 · no time yet");

    await userEvent.click(add());
    expect(onSubmit.mock.calls[0][0]).toMatchObject({ scheduled_at: new Date(2026, 10, 6).toISOString(), all_day: true });
  });

  it("walks the days with the arrows, into the next month, picking as it goes", async () => {
    const { dialog } = open();
    await userEvent.click(within(dialog).getByRole("button", { name: "Fri, Nov 27" }));
    await userEvent.keyboard("{ArrowDown}");
    expect(within(dialog).getByText("December 2026")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Fri, Dec 4" })).toHaveAttribute("aria-pressed", "true");
    expect(within(dialog).getByRole("button", { name: "Fri, Dec 4" })).toHaveFocus();
    expect(summary(dialog)).toBe("Fri, Dec 4 · no time yet");
  });

  it("keeps six rows of days in every month, so paging never changes its height", async () => {
    const { dialog } = open();
    const rows = () => dialog.querySelectorAll(".app-month-grid tbody tr").length;
    const next = within(dialog).getByRole("button", { name: msg("applications-month-next") });
    for (const month of ["November 2026", "December 2026", "January 2027", "February 2027"]) {
      expect(within(dialog).getByText(month)).toBeInTheDocument();
      expect(rows(), month).toBe(6);
      await userEvent.click(next);
    }
    // February 2027 fills four weeks; the two after it are March's, drawn as outside days.
    await userEvent.click(within(dialog).getByRole("button", { name: msg("applications-month-prev") }));
    expect(within(dialog).getByRole("button", { name: "Sun, Mar 14" })).toHaveAttribute("data-outside", "true");
  });

  it("names the zone the times are in", () => {
    const { dialog } = open();
    expect(within(dialog).getByText(/^Times in \S/)).toBeInTheDocument();
  });
});

describe("optional", () => {
  const rounds = (dialog: HTMLElement) => within(dialog).getByRole("group", { name: msg("applications-interview-round") });
  const formats = (dialog: HTMLElement) => within(dialog).getByRole("group", { name: msg("applications-interview-format") });
  const plus = (dialog: HTMLElement) => within(rounds(dialog)).getByRole("button", { name: msg("applications-interview-round-add") });
  const link = (dialog: HTMLElement) => within(dialog).queryByLabelText(msg("applications-interview-link"));

  it("offers the common rounds and the formats at once, one click each, with no field to type in", async () => {
    const { dialog, onSubmit } = open();
    // Five rounds and the plus; three formats; nothing to type until asked.
    expect(within(rounds(dialog)).getAllByRole("button")).toHaveLength(6);
    expect(within(formats(dialog)).getAllByRole("button")).toHaveLength(3);
    expect(within(dialog).queryByRole("textbox", { name: msg("applications-interview-round-name") })).toBeNull();
    expect(link(dialog)).toBeNull();

    const manager = within(rounds(dialog)).getByRole("button", { name: msg("applications-interview-round-hiring-manager") });
    await userEvent.click(manager);
    expect(manager).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(manager);
    expect(manager).toHaveAttribute("aria-pressed", "false");
    await userEvent.click(within(rounds(dialog)).getByRole("button", { name: msg("applications-interview-round-panel") }));
    await userEvent.click(within(formats(dialog)).getByRole("button", { name: msg("applications-interview-format-phone") }));
    expect(link(dialog), "a phone call has no link").toBeNull();

    await userEvent.click(within(dialog).getByRole("button", { name: "Fri, Nov 6" }));
    await userEvent.click(add());
    expect(onSubmit.mock.calls[0][0]).toMatchObject({ label: msg("applications-interview-round-panel"), format: "phone", link: null });
  });

  it("names another round in place with the plus: Enter keeps it as a chosen chip, Escape drops it, and neither leaves the form", async () => {
    const { dialog, onSubmit, onCancel } = open();
    await userEvent.click(plus(dialog));
    const name = within(dialog).getByLabelText(msg("applications-interview-round-name"));
    expect(name).toHaveFocus();
    await userEvent.type(name, "Onsite loop{Enter}");

    const custom = within(rounds(dialog)).getByRole("button", { name: "Onsite loop" });
    expect(custom).toHaveAttribute("aria-pressed", "true");
    expect(plus(dialog), "focus returns to the plus").toHaveFocus();
    expect(onSubmit, "Enter names the round, it does not send the form").not.toHaveBeenCalled();

    await userEvent.click(plus(dialog));
    await userEvent.type(within(dialog).getByLabelText(msg("applications-interview-round-name")), "Bar raiser{Escape}");
    expect(within(rounds(dialog)).queryByRole("button", { name: "Bar raiser" })).toBeNull();
    expect(within(rounds(dialog)).getByRole("button", { name: "Onsite loop" })).toHaveAttribute("aria-pressed", "true");
    expect(onCancel, "Escape closes the field, not the dialog").not.toHaveBeenCalled();
    expect(plus(dialog)).toHaveFocus();

    await userEvent.click(within(dialog).getByRole("button", { name: "Fri, Nov 6" }));
    await userEvent.click(add());
    expect(onSubmit.mock.calls[0][0]).toMatchObject({ label: "Onsite loop" });
  });

  it("keeps a typed name when the field is left, and a common round takes its place when picked", async () => {
    const { dialog } = open();
    await userEvent.click(plus(dialog));
    await userEvent.type(within(dialog).getByLabelText(msg("applications-interview-round-name")), "Take-home review");
    await userEvent.click(within(dialog).getByRole("button", { name: "Fri, Nov 6" }));
    expect(within(rounds(dialog)).getByRole("button", { name: "Take-home review" })).toHaveAttribute("aria-pressed", "true");

    await userEvent.click(within(rounds(dialog)).getByRole("button", { name: msg("applications-interview-round-technical") }));
    expect(within(rounds(dialog)).queryByRole("button", { name: "Take-home review" })).toBeNull();
  });

  it("opens the meeting link under Video, and keeps a link already typed when the format changes", async () => {
    const { dialog, onSubmit } = open();
    await userEvent.click(within(formats(dialog)).getByRole("button", { name: msg("applications-interview-format-video") }));
    await userEvent.type(link(dialog)!, "https://meet.google.com/abc-defg-hij");
    await userEvent.click(within(formats(dialog)).getByRole("button", { name: msg("applications-interview-format-onsite") }));
    expect(link(dialog)).toHaveValue("https://meet.google.com/abc-defg-hij");

    await userEvent.click(within(dialog).getByRole("button", { name: "Fri, Nov 6" }));
    await userEvent.click(add());
    expect(onSubmit.mock.calls[0][0]).toMatchObject({ format: "onsite", link: "https://meet.google.com/abc-defg-hij" });
  });
});

describe("changing an interview", () => {
  const stored: ApplicationInterview = {
    id: 7, label: "Panel", scheduled_at: new Date(2026, 11, 3, 16, 15).toISOString(), all_day: false,
    format: "phone", link: null, outcome: "passed", notes: "Went well",
    created_at: "2026-11-01T09:00:00Z", updated_at: "2026-11-01T09:00:00Z",
  };

  it("opens on its own month and day, with its time, round and format chosen", async () => {
    const { dialog, onSubmit } = open({ interview: stored, onDelete: vi.fn() });
    expect(within(dialog).getByText("December 2026")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Thu, Dec 3" })).toHaveAttribute("aria-pressed", "true");
    expect(within(dialog).getByLabelText(msg("applications-interview-time"))).toHaveValue("4:15 PM");
    expect(within(dialog).getByRole("button", { name: msg("applications-interview-round-panel") })).toHaveAttribute("aria-pressed", "true");
    expect(within(dialog).getByRole("button", { name: msg("applications-interview-format-phone") })).toHaveAttribute("aria-pressed", "true");
    expect(within(dialog).getByLabelText(msg("applications-interview-notes"))).toHaveValue("Went well");

    await userEvent.click(screen.getByRole("button", { name: msg("applications-interview-edit-submit") }));
    expect(onSubmit).toHaveBeenCalledWith({
      label: "Panel",
      scheduled_at: stored.scheduled_at,
      all_day: false,
      format: "phone",
      link: null,
      outcome: "passed",
      notes: "Went well",
    });
  });

  it("shows a round of its own name as a chosen chip, and an unnamed one as no round", async () => {
    open({ interview: { ...stored, label: "Bar raiser" } });
    expect(screen.getByRole("button", { name: "Bar raiser" })).toHaveAttribute("aria-pressed", "true");
  });

  it("does not offer the name saved for an unnamed round as a round, and saves it unchanged", async () => {
    const { dialog, onSubmit } = open({ interview: { ...stored, label: msg("applications-interview-default-label") } });
    const group = within(dialog).getByRole("group", { name: msg("applications-interview-round") });
    expect(within(group).queryAllByRole("button", { pressed: true })).toHaveLength(0);
    await userEvent.click(screen.getByRole("button", { name: msg("applications-interview-edit-submit") }));
    expect(onSubmit.mock.calls[0][0]).toMatchObject({ label: msg("applications-interview-default-label") });
  });

  it("asks before deleting, and deletes only on the second answer", async () => {
    const onDelete = vi.fn();
    const { dialog, onCancel } = open({ interview: stored, onDelete });
    const remove = within(dialog).getByRole("button", { name: msg("applications-interview-delete") });
    await userEvent.click(remove);
    expect(onDelete, "the first click only asks").not.toHaveBeenCalled();
    const question = within(dialog).getByRole("group", { name: msg("applications-interview-delete-confirm") });
    expect(within(question).getByRole("button", { name: msg("applications-interview-cancel") })).toHaveFocus();
    expect(within(dialog).queryByRole("button", { name: msg("applications-interview-edit-submit") }), "Save waits behind the question").toBeNull();

    // Escape answers the question, not the dialog.
    await userEvent.keyboard("{Escape}");
    expect(onCancel).not.toHaveBeenCalled();
    expect(within(dialog).queryByRole("group", { name: msg("applications-interview-delete-confirm") })).toBeNull();
    expect(within(dialog).getByRole("button", { name: msg("applications-interview-delete") })).toHaveFocus();
    expect(onDelete).not.toHaveBeenCalled();

    await userEvent.click(within(dialog).getByRole("button", { name: msg("applications-interview-delete") }));
    await userEvent.click(within(dialog).getByRole("button", { name: msg("applications-comment-delete") }));
    expect(onDelete).toHaveBeenCalledTimes(1);
  });
});
