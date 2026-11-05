import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ApplicationInterview } from "../../api";
import { applicationCardFixture } from "../../test/fixtures";
import { msg } from "../../test/msg";
import { InterviewDialog, isMeetingLink } from "./InterviewDialog";

/* The interview form asks for when first: a day from the month, then a time
 * or none yet. The round, the format and the link wait under Optional. What
 * it sends is the contract: the reader's own day and clock. */

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

  it("names the zone the times are in", () => {
    const { dialog } = open();
    expect(within(dialog).getByText(/^Times in \S/)).toBeInTheDocument();
  });
});

describe("optional", () => {
  it("keeps the round and the place shut until asked, and a quick pick names the round", async () => {
    const { dialog, onSubmit } = open();
    expect(within(dialog).queryByLabelText(msg("applications-interview-round"))).toBeNull();
    expect(within(dialog).queryByLabelText(msg("applications-interview-link"))).toBeNull();

    await userEvent.click(within(dialog).getByRole("button", { name: msg("applications-interview-add-round") }));
    const round = within(dialog).getByLabelText(msg("applications-interview-round"));
    expect(round).toHaveFocus();
    await userEvent.click(within(dialog).getByRole("button", { name: msg("applications-interview-round-hiring-manager") }));
    expect(round).toHaveValue(msg("applications-interview-round-hiring-manager"));

    await userEvent.click(within(dialog).getByRole("button", { name: "Fri, Nov 6" }));
    await userEvent.click(add());
    expect(onSubmit.mock.calls[0][0]).toMatchObject({ label: msg("applications-interview-round-hiring-manager") });
  });

  it("takes a pasted meeting link as a video interview, and leaves a format already chosen", async () => {
    const { dialog, onSubmit } = open();
    await userEvent.click(within(dialog).getByRole("button", { name: msg("applications-interview-add-link") }));
    const formats = within(dialog).getByRole("group", { name: msg("applications-interview-format") });
    const video = within(formats).getByRole("button", { name: msg("applications-interview-format-video") });
    const onsite = within(formats).getByRole("button", { name: msg("applications-interview-format-onsite") });
    const link = within(dialog).getByLabelText(msg("applications-interview-link"));

    await userEvent.type(link, "https://us02web.zoom.us/j/123");
    expect(video).toHaveAttribute("aria-pressed", "true");

    await userEvent.click(onsite);
    await userEvent.clear(link);
    await userEvent.type(link, "https://meet.google.com/abc-defg-hij");
    expect(onsite).toHaveAttribute("aria-pressed", "true");
    expect(video).toHaveAttribute("aria-pressed", "false");

    await userEvent.click(within(dialog).getByRole("button", { name: "Fri, Nov 6" }));
    await userEvent.click(add());
    expect(onSubmit.mock.calls[0][0]).toMatchObject({ format: "onsite", link: "https://meet.google.com/abc-defg-hij" });
  });

  it("knows a meeting room's link from any other", () => {
    expect(isMeetingLink("https://us02web.zoom.us/j/123")).toBe(true);
    expect(isMeetingLink("https://teams.microsoft.com/l/meetup-join/x")).toBe(true);
    expect(isMeetingLink("https://zoom.us.example.com/j/1")).toBe(false);
    expect(isMeetingLink("https://careers.stripe.com/zoom.us")).toBe(false);
    expect(isMeetingLink("not a link")).toBe(false);
  });
});

describe("changing an interview", () => {
  const stored: ApplicationInterview = {
    id: 7, label: "Panel", scheduled_at: new Date(2026, 11, 3, 16, 15).toISOString(), all_day: false,
    format: "phone", link: null, outcome: "passed", notes: "Went well",
    created_at: "2026-11-01T09:00:00Z", updated_at: "2026-11-01T09:00:00Z",
  };

  it("opens on its own month and day, with its time, round and format standing open", async () => {
    const { dialog, onSubmit } = open({ interview: stored, onDelete: vi.fn() });
    expect(within(dialog).getByText("December 2026")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Thu, Dec 3" })).toHaveAttribute("aria-pressed", "true");
    expect(within(dialog).getByLabelText(msg("applications-interview-time"))).toHaveValue("4:15 PM");
    expect(within(dialog).getByLabelText(msg("applications-interview-round"))).toHaveValue("Panel");
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
});
