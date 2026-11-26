import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { companyName } from "../../format";
import { jobFixture } from "../../test/fixtures";
import { msg } from "../../test/msg";
import { PickFeedbackDialog } from "./PickFeedbackDialog";

const job = { ...jobFixture, id: 41, title: "Staff Product Manager, Payments", company: "stripe" };

function renderDialog(open = true) {
  const onRemove = vi.fn();
  const onKeep = vi.fn();
  render(<PickFeedbackDialog job={open ? job : null} onRemove={onRemove} onKeep={onKeep} />);
  return { onRemove, onKeep };
}

/** Each answer's label, and the code it stores. */
const REASONS: [string, string][] = [
  [msg("picks-why-pay"), "pay_too_low"],
  [msg("picks-why-level"), "wrong_level"],
  [msg("picks-why-work"), "wrong_role"],
  [msg("picks-why-company"), "company"],
  [msg("picks-why-place"), "wrong_place"],
  [msg("picks-why-other"), "other"],
];

describe("PickFeedbackDialog", () => {
  it("asks nothing until a pick is named", () => {
    renderDialog(false);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("asks why about the named role, with the reasons in order and the safe answer focused", async () => {
    renderDialog();
    const dialog = await screen.findByRole("dialog", { name: msg("picks-why-title") });
    const title = within(dialog).getByText("Staff Product Manager, Payments");
    expect(title.parentElement).toHaveTextContent(msg("picks-why-role", { title: job.title, company: companyName(job.company) }));
    // The employer's words sit in the sentence as content, never translated.
    expect(title).toHaveAttribute("data-copy", "content");
    expect(within(dialog).getByText(companyName(job.company))).toHaveAttribute("data-copy", "content");
    const buttons = within(dialog).getAllByRole("button").map((button) => button.textContent);
    expect(buttons).toEqual([
      ...REASONS.map(([label]) => label), msg("picks-why-skip"), msg("picks-why-keep"),
    ]);
    expect(within(dialog).getByRole("button", { name: msg("picks-why-keep") })).toHaveFocus();
  });

  it.each(REASONS)("removes the role with the code its reason stores: %s", async (label, code) => {
    const { onRemove, onKeep } = renderDialog();
    await userEvent.click(await screen.findByRole("button", { name: label }));
    expect(onRemove).toHaveBeenCalledExactlyOnceWith(job, code);
    expect(onKeep).not.toHaveBeenCalled();
  });

  it("removes the role with no reason when the person skips it", async () => {
    const { onRemove } = renderDialog();
    await userEvent.click(await screen.findByRole("button", { name: msg("picks-why-skip") }));
    expect(onRemove).toHaveBeenCalledExactlyOnceWith(job, null);
  });

  it("keeps the role on Keep it and on Escape", async () => {
    const { onRemove, onKeep } = renderDialog();
    await userEvent.click(await screen.findByRole("button", { name: msg("picks-why-keep") }));
    await userEvent.keyboard("{Escape}");
    expect(onKeep).toHaveBeenCalledTimes(2);
    expect(onRemove).not.toHaveBeenCalled();
  });
});
