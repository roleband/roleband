import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { api } from "../../api";
import { msg } from "../../test/msg";
import { fakeViewChoiceServer } from "../../test/viewChoicesServer";
import { PreferencesSection } from "./PreferencesSection";

/* The side bar that follows these switches is tested with the switches in
   `shell/NavRail.test.tsx`: the shell may import a feature, not the reverse. */

function preferences() {
  render(<PreferencesSection />);
  const card = screen.getByRole("region", { name: msg("settings-side-bar-title") });
  return { card, place: (name: string) => within(card).getByRole("checkbox", { name }) };
}

describe("Settings › Preferences", () => {
  it("offers the three optional places at their defaults, and says what Duplicates holds", () => {
    fakeViewChoiceServer({});
    const view = preferences();
    expect(view.place(msg("shell-nav-insights"))).toBeChecked();
    expect(view.place(msg("shell-nav-companies"))).toBeChecked();
    expect(view.place(msg("shell-nav-duplicates"))).not.toBeChecked();
    expect(view.place(msg("shell-nav-duplicates"))).toHaveAccessibleDescription(msg("settings-side-bar-duplicates"));
    // Fixed places are not offered: the side bar always lists them.
    expect(within(view.card).getAllByRole("checkbox")).toHaveLength(3);
    expect(screen.getByRole("heading", { level: 2, name: msg("settings-language-title") })).toBeInTheDocument();
  });

  it("shows the person's saved answer, not the default", async () => {
    fakeViewChoiceServer({ "sidebar.companies": false, "sidebar.duplicates": true });
    const view = preferences();
    // The answer arrives with the read: wait for it, not for the switch.
    await vi.waitFor(() => expect(view.place(msg("shell-nav-duplicates"))).toBeChecked());
    expect(view.place(msg("shell-nav-companies"))).not.toBeChecked();
    expect(view.place(msg("shell-nav-insights"))).toBeChecked();
  });

  it("saves each switch as the person's choice", async () => {
    const server = fakeViewChoiceServer({});
    const user = userEvent.setup();
    const view = preferences();
    await user.click(view.place(msg("shell-nav-duplicates")));
    await user.click(view.place(msg("shell-nav-insights")));
    expect(view.place(msg("shell-nav-duplicates"))).toBeChecked();
    expect(view.place(msg("shell-nav-insights"))).not.toBeChecked();
    await vi.waitFor(() =>
      expect(server.saved()).toEqual({ "sidebar.duplicates": true, "sidebar.insights": false }));
  });

  it("says a failed save, and keeps the choice for this visit", async () => {
    fakeViewChoiceServer({});
    vi.spyOn(api, "saveViewChoice").mockRejectedValue(new Error("down"));
    const user = userEvent.setup();
    const view = preferences();
    await user.click(view.place(msg("shell-nav-duplicates")));
    expect(await within(view.card).findByRole("alert")).toHaveTextContent(msg("settings-save-failed"));
    expect(view.place(msg("shell-nav-duplicates"))).toBeChecked();
  });
});
