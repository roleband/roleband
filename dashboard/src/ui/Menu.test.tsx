import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { Menu, MenuCheck, MenuGroup, MenuItem, MenuRadio } from "./Menu";

/* The menu's contracts: rows are named by their words alone, the arrows walk
 * the rows and skip what is off, a radio keeps its own arrows, and the
 * spacing lives inside the painted panel, never on the popover's outer box. */

function Harness({ onPick = () => undefined }: { onPick?: (what: string) => void }) {
  const [anchor, setAnchor] = useState<HTMLButtonElement | null>(null);
  const [open, setOpen] = useState(false);
  const [overdue, setOverdue] = useState(false);
  const [mode, setMode] = useState("only");
  return (
    <>
      <button ref={setAnchor} onClick={() => setOpen(true)}>Open</button>
      <Menu isOpen={open} onClose={() => setOpen(false)} anchor={anchor} label="Filter applications">
        <MenuGroup label="Quick filters">
          <MenuCheck checked={overdue} onChange={setOverdue} count={3}>Overdue</MenuCheck>
          <MenuCheck checked={false} onChange={() => undefined} disabled>Gone quiet</MenuCheck>
        </MenuGroup>
        <MenuGroup label="While filtering">
          <MenuRadio name="mode" checked={mode === "only"} onChange={() => setMode("only")} hint="What doesn't match leaves.">
            Show only matches
          </MenuRadio>
          <MenuRadio name="mode" checked={mode === "highlight"} onChange={() => setMode("highlight")}>
            Highlight matches
          </MenuRadio>
        </MenuGroup>
        <MenuGroup>
          <MenuItem current detail="Nov 2" onSelect={() => onPick("applied")}>Applied</MenuItem>
          <MenuItem onSelect={() => onPick("reset")}>Show all columns</MenuItem>
        </MenuGroup>
        <MenuGroup>
          <MenuItem onSelect={() => onPick("notes")} hint="What you know and who you met">Notes</MenuItem>
          <MenuItem onSelect={() => onPick("activity")} hint="Comments and what changed">Activity</MenuItem>
        </MenuGroup>
      </Menu>
    </>
  );
}

async function openMenu() {
  await userEvent.click(screen.getByRole("button", { name: "Open" }));
  return screen.findByRole("dialog", { name: "Filter applications" });
}

describe("Menu", () => {
  it("names each row by its words, not its count or hint, and groups rows under their headings", async () => {
    render(<Harness />);
    const menu = await openMenu();
    expect(within(menu).getByRole("group", { name: "Quick filters" })).toBeInTheDocument();
    const overdue = within(menu).getByRole("checkbox", { name: "Overdue" });
    expect(overdue).not.toBeChecked();
    await userEvent.click(overdue);
    expect(overdue).toBeChecked();
    expect(within(menu).getByRole("checkbox", { name: "Gone quiet" })).toBeDisabled();
    expect(within(menu).getByRole("radio", { name: "Show only matches" }))
      .toHaveAccessibleDescription("What doesn't match leaves.");
    expect(within(menu).getByRole("button", { name: /^Applied/ })).toHaveAttribute("aria-current", "true");
    // An action's line under its name describes it; the name stays its words.
    const notes = within(menu).getByRole("button", { name: "Notes" });
    expect(notes).toHaveAccessibleDescription("What you know and who you met");
    expect(notes).toHaveAttribute("data-hinted");
    expect(within(menu).getByRole("button", { name: "Show all columns" })).not.toHaveAttribute("data-hinted");
  });

  it("walks the rows with the arrows, skipping a row that is off, and Home and End go to the ends", async () => {
    render(<Harness />);
    await openMenu();
    const overdue = screen.getByRole("checkbox", { name: "Overdue" });
    const last = screen.getByRole("button", { name: "Activity" });

    await userEvent.keyboard("{ArrowDown}");
    expect(overdue).toHaveFocus();
    await userEvent.keyboard("{ArrowDown}");
    expect(screen.getByRole("radio", { name: "Show only matches" })).toHaveFocus();
    await userEvent.keyboard("{End}");
    expect(last).toHaveFocus();
    await userEvent.keyboard("{ArrowDown}");
    expect(overdue).toHaveFocus();
    await userEvent.keyboard("{ArrowUp}");
    expect(last).toHaveFocus();
    await userEvent.keyboard("{Home}");
    expect(overdue).toHaveFocus();
  });

  it("leaves a radio's own arrows to choose within its group", async () => {
    render(<Harness />);
    await openMenu();
    const only = screen.getByRole("radio", { name: "Show only matches" });
    act(() => only.focus());
    await userEvent.keyboard("{ArrowDown}");
    expect(screen.getByRole("radio", { name: "Highlight matches" })).toBeChecked();
  });

  it("runs an action on press", async () => {
    const onPick = vi.fn();
    render(<Harness onPick={onPick} />);
    await openMenu();
    await userEvent.click(screen.getByRole("button", { name: "Show all columns" }));
    expect(onPick).toHaveBeenCalledWith("reset");
  });

  it("pads and sizes the body inside the painted panel, and leaves the popover's outer box alone", async () => {
    render(<Harness />);
    const menu = await openMenu();
    expect(menu.className.split(" ").sort()).toEqual(["app-overlay", "ui-menu", "ui-overlay-content", "ui-popover"]);
    const body = menu.querySelector(".ui-menu-body");
    expect(body?.parentElement).toHaveClass("ui-popover-inner");
  });
});
