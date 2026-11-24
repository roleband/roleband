/* THE TWO STATES, read off the screens (docs/ui.md
   "Two states"). One option CHOSEN among others is gold on every screen, in
   every control: wash behind it, its name in the chosen ink. A thing's own ON
   state (a switch, the row it governs) is ink. The failure this guards is
   many looks for "selected" (gold tint, gold tint with ink text, a raised
   neutral segment, a neutral tint, an ink fill), each correct on its own
   screen and each different from its neighbour's.

   Each control is measured where it lives, against the tokens resolved in
   that same place, and every screen must resolve the same tokens: a material
   or scope that restated them would pass the first check and fail the second.
   The source half (no state CLASSES, no state painted outside the two token
   sets) is `src/design/state-grammar.test.ts`. */

import type { Locator } from "@playwright/test";
import { expect, test, type Page } from "./fixtures";
import { installEveryRoute } from "./routesHarness";
import { installSettingsRoutes } from "./settingsHarness";

test.beforeEach(async ({ page }) => {
  await installEveryRoute(page);
  await installSettingsRoutes(page);
});

type Paint = { wash: string; ink: string };

/** The two token sets as this element's own context resolves them. */
async function tokensAt(locator: Locator): Promise<{ chosen: Paint; on: Paint }> {
  return locator.evaluate((node) => {
    const read = (bg: string, fg: string) => {
      const probe = document.createElement("span");
      probe.style.backgroundColor = `var(${bg})`;
      probe.style.color = `var(${fg})`;
      node.parentElement!.appendChild(probe);
      const cs = getComputedStyle(probe);
      const out = { wash: cs.backgroundColor, ink: cs.color };
      probe.remove();
      return out;
    };
    return {
      chosen: read("--app-chosen-wash", "--app-chosen-text"),
      on: read("--app-on-wash", "--app-on-fill"),
    };
  });
}

/** What the control actually paints: its own background, and the colour of
 *  its NAME (the element carrying the words, which for a card is its label). */
async function painted(control: Locator, name: string | null): Promise<Paint> {
  return control.evaluate((node, nameSel: string | null) => {
    const words = (nameSel ? node.querySelector(nameSel) : node) as HTMLElement;
    return { wash: getComputedStyle(node).backgroundColor, ink: getComputedStyle(words).color };
  }, name);
}

type Case = {
  family: string;
  path: string;
  control: (page: Page) => Locator;
  name: string | null;
};

const CHOSEN: Case[] = [
  { family: "Settings tab bar", path: "/settings/schedule", control: (p) => p.getByRole("tab", { selected: true }).first(), name: null },
  { family: "Schedule day chip", path: "/settings/schedule", control: (p) => p.locator('.ui-chip[aria-pressed="true"]').first(), name: null },
  { family: "Insights segment", path: "/statistics/overview", control: (p) => p.locator('.ui-seg-btn[aria-pressed="true"]').first(), name: null },
  { family: "Profile option card", path: "/profile/direction", control: (p) => p.locator(".walk-cards label.select-card:has(> input:checked)").first(), name: ".select-card-label" },
  { family: "Topbar lens chip", path: "/", control: (p) => p.locator('.stat-chip[aria-current="page"]').first(), name: ".l" },
];

for (const theme of ["light", "dark"] as const) {
  test(`one option chosen is the same gold in every control on every screen (${theme})`, async ({ page }) => {
    await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
    await page.setViewportSize({ width: 1280, height: 800 });
    let first: Paint | null = null;
    for (const c of CHOSEN) {
      await page.goto(c.path);
      const control = c.control(page);
      await expect(control, `${c.family}: nothing chosen rendered`).toBeVisible();
      const { chosen } = await tokensAt(control);
      // Transitions on background/colour settle within --app-duration-fast.
      await expect.poll(() => painted(control, c.name), { message: `${c.family} is not painted chosen` }).toEqual(chosen);
      first ??= chosen;
      expect(chosen, `${c.family}: this screen resolves the chosen tokens differently`).toEqual(first);
    }
    // The wash is the action colour in either theme. The name is the pale
    // gold on dark and the ink on light: a step in lightness from the muted
    // idle names beside it, which a blue name of their lightness is not.
    expect(first!.wash).toBe(theme === "dark" ? "rgba(219, 203, 144, 0.12)" : "rgba(39, 98, 177, 0.1)");
    expect(first!.ink).toBe(theme === "dark" ? "rgb(232, 220, 172)" : "rgb(25, 26, 28)");
  });

  test(`a thing that is on is ink, the switch and the row it governs alike (${theme})`, async ({ page }) => {
    await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
    await page.goto("/settings/companies");
    const track = page.locator(".ui-switch-track:checked").first();
    await expect(track).toBeAttached();
    const { on, chosen } = await tokensAt(track);
    await expect.poll(() => track.evaluate((n) => getComputedStyle(n).backgroundColor)).toBe(on.ink);
    const row = page.locator(".ledger-row:has(.ui-switch-track:checked)").first();
    await expect.poll(() => row.evaluate((n) => getComputedStyle(n).backgroundColor)).toBe(on.wash);
    // And on is not chosen: a governed row never lies on the chosen wash.
    expect(on.wash).not.toBe(chosen.wash);
  });

  test(`the rail's chosen view stands apart from idle ones by lightness, its marks in the accent (${theme})`, async ({ page, isMobile }) => {
    test.skip(isMobile, "The dock under 860px is its own layout.");
    await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/");
    const chosen = page.locator('.nav-rail .rail-item[aria-current="page"]');
    await expect(chosen).toHaveCount(1);

    const read = () => chosen.evaluate((node) => {
      const idle = node.parentElement!.querySelector<HTMLElement>(".rail-item:not([aria-current]):not(.rail-family-star)")!;
      const paintOf = (token: string) => {
        const probe = document.createElement("span");
        probe.style.color = `var(${token})`;
        node.appendChild(probe);
        const out = getComputedStyle(probe).color;
        probe.remove();
        return out;
      };
      /** The first colour in a computed value as [r, g, b, alpha]; a value
       *  with no colour in it ("none") paints nothing. */
      const rgba = (value: string): number[] => {
        const parts = value.match(/rgba?\(([^)]+)\)/)?.[1].split(/[\s,/]+/).filter(Boolean).map(Number);
        return parts ? [parts[0], parts[1], parts[2], parts[3] ?? 1] : [0, 0, 0, 0];
      };
      const luminance = (value: string) => {
        const [r, g, b] = rgba(value).slice(0, 3).map((v) => {
          const c = v / 255;
          return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
        });
        return 0.2126 * r + 0.7152 * g + 0.0722 * b;
      };
      const own = getComputedStyle(node);
      const [hi, lo] = [luminance(own.color), luminance(getComputedStyle(idle).color)].sort((a, b) => b - a);
      const wash = rgba(own.backgroundColor).slice(0, 3);
      return {
        step: (hi + 0.05) / (lo + 0.05),
        name: own.color,
        icon: getComputedStyle(node.querySelector("svg")!).color,
        iconToken: paintOf("--rail-accent-icon"),
        accent: paintOf("--rail-accent"),
        washSpread: Math.max(...wash) - Math.min(...wash),
        edgeAlpha: rgba(own.borderTopColor)[3],
        glowAlpha: rgba(getComputedStyle(node, "::before").boxShadow)[3],
      };
    });

    // Colour transitions settle within --app-duration-fast.
    await expect
      .poll(async () => (await read()).step, { message: "the chosen name differs from an idle one by hue alone" })
      .toBeGreaterThanOrEqual(1.7);
    const row = await read();
    expect(row.icon).toBe(row.iconToken);
    if (theme === "light") {
      // On white the name is ink and the blue is a mark: the icon, not the words.
      expect(row.icon).toBe(row.accent);
      expect(row.name).not.toBe(row.accent);
      // The wash is a veil of ink, so its channels sit together; the action
      // wash's blue channel stands more than a hundred above its red.
      expect(row.washSpread, "the chosen wash is tinted").toBeLessThanOrEqual(16);
      expect(row.edgeAlpha, "the chosen row draws an edge").toBe(0);
      expect(row.glowAlpha, "the chosen bar glows").toBe(0);
    }

    // The star is the Pipeline's mark and keeps the accent when it is chosen.
    await page.goto("/pipeline/board");
    const star = page.locator('.nav-rail .rail-family-star[aria-current="true"]');
    await expect(star).toHaveCount(1);
    await expect
      .poll(() => star.evaluate((node) => {
        const probe = document.createElement("span");
        probe.style.color = "var(--rail-accent)";
        node.appendChild(probe);
        const accent = getComputedStyle(probe).color;
        probe.remove();
        return getComputedStyle(node.querySelector("svg")!).color === accent;
      }))
      .toBe(true);
  });
}
