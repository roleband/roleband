/* Settings › AI: the Top picks card. Drawn only once Top picks is set up; it
   pauses and resumes the checks, says which assistant checks and when it last
   did, shows what the person is looking for, bounds the reading a day, and
   removes what the person gave, asking first. */

import AxeBuilder from "@axe-core/playwright";
import type { PicksState } from "../../src/api";
import { picksStateFixture } from "../../src/test/fixtures";
import { msg } from "../../src/test/msg";
import { expect, mockApi, mockGet, test, type Page } from "./fixtures";
import { expectFullyVisible, laidOut, overlapping } from "./geometry";
import { installSettingsRoutes } from "./settingsHarness";
import { healthyState } from "./topPicksHarness";

const BRIEF = "Beats a Senior Director of Engineering offer at 352,000 base. Principal or director level and above. "
  + "Leads a team or owns a product area. AI is the substance of the job.";

const setUp = (over: Partial<PicksState> = {}) => healthyState({
  schedule: "daily 09:30 and 17:30",
  brief_summary: BRIEF,
  ...over,
});

/** The AI tab with Top picks in `state`; every write answers with the state
 *  it asked for, and is recorded. */
async function openWith(page: Page, state: PicksState) {
  let current = state;
  const writes: { method: string; body: unknown }[] = [];
  await installSettingsRoutes(page);
  await mockGet(page, "/api/picks/state", (route) => route.fulfill({ json: current }));
  await mockApi(page, "PUT", "/api/picks/mode", (route) => {
    const body = route.request().postDataJSON() as { state?: "on" | "off"; daily_limit?: number };
    writes.push({ method: "PUT", body });
    current = {
      ...current,
      ...(body.state ? { state: body.state, health: body.state === "on" ? "healthy" : "off" } : {}),
      ...(body.daily_limit ? { daily_limit: body.daily_limit } : {}),
    } as PicksState;
    return route.fulfill({ json: current });
  });
  await mockApi(page, "DELETE", "/api/picks/setup", (route) => {
    writes.push({ method: "DELETE", body: null });
    current = picksStateFixture();
    return route.fulfill({ json: { briefs: 1, readings: 2, documents: 1, verdicts: 18 } });
  });
  await page.goto("/settings/intelligence");
  return { writes };
}

const picksCard = (page: Page) => page.getByRole("region", { name: msg("shell-nav-top-picks") });

test("before setup the AI tab has no Top picks card", async ({ page }) => {
  await installSettingsRoutes(page);
  await page.goto("/settings/intelligence");
  await expect(page.getByRole("region", { name: msg("ai-assistants-card-assistant-apps-2") })).toBeVisible();
  await expect(page.getByRole("region", { name: msg("ai-capabilities-card-extended-capabilities-2") })).toBeVisible();
  await expect(picksCard(page)).toHaveCount(0);
});

test("once set up the card sits after Assistant apps, with its five parts", async ({ page }) => {
  await openWith(page, setUp());
  const card = picksCard(page);
  await expect(card).toBeVisible();

  // After the assistants it depends on, before the capabilities.
  const assistants = await page.getByRole("region", { name: msg("ai-assistants-card-assistant-apps-2") }).boundingBox();
  const own = await card.boundingBox();
  const capabilities = await page.getByRole("region", { name: msg("ai-capabilities-card-extended-capabilities-2") }).boundingBox();
  expect(assistants!.y).toBeLessThan(own!.y);
  expect(own!.y).toBeLessThan(capabilities!.y);

  const status = msg("ai-top-picks-card-status", {
    state: "checked", host: msg("picks-host", { host: "claude-code" }), when: "2 hours ago",
  });
  await expect(card.getByText(`${status} · daily 09:30 and 17:30`)).toBeVisible();
  await expect(card.getByRole("checkbox", { name: msg("ai-top-picks-card-check") })).toBeChecked();
  await expect(card.getByText(BRIEF)).toBeVisible();
  const copy = card.getByRole("button", {
    name: msg("shared-copy-text", { text: msg("ai-top-picks-card-sentence") }),
  });
  await expect(copy).toBeVisible();
  // The sentence can be selected inside its button, for a refused clipboard.
  expect(await copy.getByText(msg("ai-top-picks-card-sentence")).evaluate((el) => getComputedStyle(el).userSelect)).toBe("text");
  await expect(card.getByLabel(msg("ai-top-picks-card-limit"))).toHaveValue("1000");
  await expect(card.getByRole("button", { name: msg("ai-top-picks-card-remove") })).toBeVisible();
});

test("the switch pauses the checks and resumes them, each a write of its own", async ({ page }) => {
  const { writes } = await openWith(page, setUp());
  const card = picksCard(page);
  const toggle = card.getByRole("checkbox", { name: msg("ai-top-picks-card-check") });

  // The whole row's switch is the target; the track is what the pointer hits.
  await toggle.click();
  await expect(toggle).not.toBeChecked();
  await expect(card.getByText(msg("ai-top-picks-card-status", {
    state: "paused-checked", host: msg("picks-host", { host: "claude-code" }), when: "2 hours ago",
  }), { exact: true })).toBeVisible();
  await toggle.click();
  await expect(toggle).toBeChecked();
  expect(writes).toEqual([
    { method: "PUT", body: { state: "off" } },
    { method: "PUT", body: { state: "on" } },
  ]);
});

test("the daily limit refuses 0 and anything above the most, and saves a number in range", async ({ page }) => {
  const { writes } = await openWith(page, setUp());
  const card = picksCard(page);
  const field = card.getByLabel(msg("ai-top-picks-card-limit"));
  const range = msg("ai-top-picks-card-limit-range", { max: 5000 });

  for (const refused of ["0", "5001"]) {
    await field.fill(refused);
    await field.press("Enter");
    await expect(field).toHaveAttribute("aria-invalid", "true");
    await expect(card.getByText(range)).toBeVisible();
    // The refusal is the danger edge from the one rule in shell.css.
    const edge = await field.evaluate((el) => getComputedStyle(el).borderTopColor);
    const danger = await field.evaluate((el) => {
      const probe = document.createElement("i");
      probe.style.color = "var(--app-danger)";
      el.parentElement!.append(probe);
      const colour = getComputedStyle(probe).color;
      probe.remove();
      return colour;
    });
    expect(edge).toBe(danger);
  }
  await field.blur();
  expect(writes).toEqual([]);

  await field.fill("300");
  await field.press("Enter");
  await expect.poll(() => writes).toEqual([{ method: "PUT", body: { daily_limit: 300 } }]);
  // The keyboard stays in the field, and leaving it sends nothing more.
  await expect(field).toBeFocused();
  await field.blur();
  expect(writes).toHaveLength(1);
  await expect(field).not.toHaveAttribute("aria-invalid");
  await expect(card.getByText(range)).toHaveCount(0);
});

test("Remove asks first, and only the confirmation deletes", async ({ page }) => {
  const { writes } = await openWith(page, setUp());
  const card = picksCard(page);

  await card.getByRole("button", { name: msg("ai-top-picks-card-remove") }).click();
  const dialog = page.getByRole("dialog", { name: msg("ai-top-picks-card-remove-confirm-title") });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText(msg("ai-top-picks-card-remove-confirm"))).toBeVisible();
  // A question that must be answered: the scrim does not close it.
  await page.mouse.click(5, 5);
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: msg("ai-aim-line-cancel") }).click();
  await expect(dialog).toHaveCount(0);
  expect(writes).toEqual([]);
  await expect(card).toBeVisible();

  await card.getByRole("button", { name: msg("ai-top-picks-card-remove") }).click();
  await dialog.getByRole("button", { name: msg("ai-top-picks-card-remove") }).click();
  await expect(card).toHaveCount(0);
  await expect(page.getByText(msg("ai-top-picks-card-removed"))).toBeVisible();
  expect(writes).toEqual([{ method: "DELETE", body: null }]);
});

for (const width of [1440, 2000]) {
  test(`long text wraps inside the card and nothing overlaps at ${width}`, async ({ page, isMobile }) => {
    test.skip(isMobile, "Settings is a desktop screen");
    await page.setViewportSize({ width, height: 1000 });
    const long = `${"Principal or director level and above, leading a team that owns an applied AI product area. ".repeat(4)}`
      + "Avoid-anything-that-is-a-pure-research-role-with-no-path-to-shipping-product-to-customers";
    await openWith(page, setUp({ brief_summary: long, schedule: "weekdays at 07:00, 12:30 and 18:00 local time" }));
    const card = picksCard(page);
    await expect(card.getByText(long)).toBeVisible();

    // Nothing pushes the card wider than its place on the tab.
    const widths = await card.evaluate((el) => ({ scroll: el.scrollWidth, client: el.clientWidth }));
    expect(widths.scroll).toBeLessThanOrEqual(widths.client);
    for (const control of [
      card.getByRole("button", { name: msg("shared-copy-text", { text: msg("ai-top-picks-card-sentence") }) }),
      card.getByLabel(msg("ai-top-picks-card-limit")),
      card.getByRole("button", { name: msg("ai-top-picks-card-remove") }),
    ]) {
      // In view first: what is measured is clipping by the card, not the fold.
      await control.scrollIntoViewIfNeeded();
      await expectFullyVisible(control, "a control of the card");
    }
    // Each row's words against each control: the words never run under one.
    expect(overlapping(await laidOut(card, ".intel-picks-row-copy, .intel-picks-limit, .ui-btn, .ui-copy-field"))).toEqual([]);
  });
}

for (const theme of ["light", "dark"] as const) {
  test(`each control of the card wears the ring inside the card (${theme})`, async ({ page, isMobile }) => {
    test.skip(isMobile, "Tab order is a desktop keyboard contract");
    await page.addInitScript((value) => localStorage.setItem("theme", value), theme);
    await page.setViewportSize({ width: 1440, height: 1000 });
    await openWith(page, setUp());
    const card = picksCard(page);
    const toggle = card.getByRole("checkbox", { name: msg("ai-top-picks-card-check") });
    await toggle.focus();
    await page.keyboard.press("Tab");
    await page.keyboard.press("Shift+Tab");
    const field = card.getByLabel(msg("ai-top-picks-card-limit"));
    const stops = [
      toggle,
      card.getByRole("button", { name: msg("shared-copy-text", { text: msg("ai-top-picks-card-sentence") }) }),
      field,
      card.getByRole("button", { name: msg("ai-top-picks-card-remove") }),
    ];
    for (const [i, stop] of stops.entries()) {
      if (i > 0) await page.keyboard.press("Tab");
      await expect(stop).toBeFocused();
      const ring = await stop.evaluate((el) => {
        const style = getComputedStyle(el);
        const r = el.getBoundingClientRect();
        const offset = parseFloat(style.outlineOffset);
        const width = parseFloat(style.outlineWidth);
        const out = Math.max(0, offset + width);
        const host = el.closest("section")!.getBoundingClientRect();
        return {
          drawn: style.outlineStyle !== "none" && width >= 2,
          inside: r.left - out >= host.left && r.right + out <= host.right,
          offset,
        };
      });
      expect(ring.drawn, `stop ${i} draws a ring`).toBe(true);
      expect(ring.inside, `stop ${i}'s ring stays inside the card`).toBe(true);
      // A field rings inside its own edge, read while it has the focus.
      if (stop === field) expect(ring.offset, "the field's ring sits inside its edge").toBeLessThan(0);
    }
  });

  test(`the card and its question meet contrast and naming rules (${theme})`, async ({ page }) => {
    await page.addInitScript((value) => localStorage.setItem("theme", value), theme);
    await openWith(page, setUp({ health: "late", waiting: 40 }));
    const card = picksCard(page);
    await expect(card).toBeVisible();
    const serious = async () => (await new AxeBuilder({ page }).include("[data-testid='top-picks-card']").analyze()).violations
      .filter((v) => v.impact === "serious" || v.impact === "critical")
      .map((v) => `${v.id}: ${v.nodes.map((n) => n.html).join("; ")}`);
    expect(await serious()).toEqual([]);

    await card.getByRole("button", { name: msg("ai-top-picks-card-remove") }).click();
    const dialog = page.getByRole("dialog", { name: msg("ai-top-picks-card-remove-confirm-title") });
    await expect(dialog).toBeVisible();
    // It fades in: contrast is read once it has settled.
    await expect.poll(() => dialog.evaluate((el) => el.getAnimations({ subtree: true }).every((one) => one.playState === "finished"))).toBe(true);
    const inDialog = (await new AxeBuilder({ page }).include("[role='dialog']").analyze()).violations
      .filter((v) => v.impact === "serious" || v.impact === "critical")
      .map((v) => `${v.id}: ${v.nodes.map((n) => n.html).join("; ")}`);
    expect(inDialog).toEqual([]);
  });
}
