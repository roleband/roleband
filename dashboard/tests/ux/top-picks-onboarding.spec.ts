/* Top picks before setup: the Onboarding pattern. Step 1 is one sentence the
   person says in their assistant, in a control that copies it; the screen
   mirrors what the setup conversation saves, read again while it is open, and
   gives way to the list once the checks are set up. */

import type { Page } from "@playwright/test";
import type { AgentAccessState, PicksState } from "../../src/api";
import { agentAccessFixture, picksSetupFixture, picksStateFixture } from "../../src/test/fixtures";
import { msg } from "../../src/test/msg";
import { expect, mockApi, mockGet, test } from "./fixtures";
import { expectFullyVisible, laidOut, overlapping } from "./geometry";
import { healthyState, installTopPicksRoutes } from "./topPicksHarness";

const SENTENCE = msg("picks-onboard-sentence");
const copyField = (page: Page, text: string) =>
  page.getByRole("button", { name: msg("shared-copy-text", { text }) });
const onboarding = (page: Page) => page.locator("section.onboard");

const connected = (): AgentAccessState => ({
  ...agentAccessFixture,
  enabled: true,
  allow_writes: true,
  apps: agentAccessFixture.apps.map((app) =>
    app.app === "claude-code" ? { ...app, connection: "connected", last_call_at: new Date().toISOString() } : app),
});

/** The Radar's and Top picks' routes, with the picks state and assistant
 *  access served from what the spec holds, so it can change them mid-visit. */
async function installOnboarding(page: Page, held: { picks: PicksState; access: AgentAccessState }) {
  await installTopPicksRoutes(page, { state: held.picks });
  await mockGet(page, "/api/picks/state", (route) => route.fulfill({ json: held.picks }));
  await mockApi(page, "POST", "/api/picks/opened", (route) => route.fulfill({ json: held.picks }));
  await mockApi(page, ["GET", "PUT"], "/api/intelligence/agents", (route) => {
    if (route.request().method() === "PUT") held.access = { ...held.access, ...route.request().postDataJSON() };
    return route.fulfill({ json: held.access });
  });
  return held;
}

test.describe("before the setup conversation saves anything", () => {
  test("the sentence copies whole, and the control says so", async ({ page, context, browserName }) => {
    test.skip(browserName !== "chromium", "clipboard permissions are granted in Chromium only");
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await installOnboarding(page, { picks: picksStateFixture(), access: { ...agentAccessFixture, enabled: true } });
    await page.goto("/top-picks");
    const field = copyField(page, SENTENCE);
    await expect(field).toContainText("roleband connect --apply");
    await field.click();
    await expect(field).toContainText(msg("shared-copied"));
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(SENTENCE);
  });

  test("a connected assistant is asked only for setup, and the Terminal fallback goes", async ({ page }) => {
    const held = await installOnboarding(page, { picks: picksStateFixture(), access: { ...agentAccessFixture, enabled: true } });
    await page.goto("/top-picks");
    await expect(copyField(page, SENTENCE)).toBeVisible();
    await expect(page.getByRole("button", { name: msg("picks-onboard-terminal") })).toBeVisible();

    held.access = connected();
    const short = msg("picks-onboard-sentence-connected");
    await expect(copyField(page, short)).toBeVisible({ timeout: 10_000 });
    await expect(copyField(page, SENTENCE)).toHaveCount(0);
    await expect(page.getByText(msg("picks-onboard-connected", { host: msg("picks-host", { host: "claude-code" }) }))).toBeVisible();
    await expect(page.getByRole("button", { name: msg("picks-onboard-terminal") })).toHaveCount(0);
  });

  test("with assistant apps off, its switch comes first and turns them on with writes", async ({ page }) => {
    const held = await installOnboarding(page, { picks: picksStateFixture(), access: agentAccessFixture });
    const saved = page.waitForRequest((request) =>
      request.method() === "PUT" && request.url().endsWith("/api/intelligence/agents"));
    await page.goto("/top-picks");
    const allow = page.getByRole("checkbox", { name: msg("ai-assistants-card-allow-assistant-apps-to-connect") });
    await expect(allow).not.toBeChecked();
    // The switch's label is its hit target.
    await allow.locator("xpath=..").click();
    expect((await saved).postDataJSON()).toEqual({ enabled: true, allow_writes: true });
    await expect(allow).toHaveCount(0);
    expect(held.access.enabled).toBe(true);
  });

  test("Terminal gives the engine's command for the chosen assistant, then setup in it", async ({ page }) => {
    await installOnboarding(page, { picks: picksStateFixture(), access: { ...agentAccessFixture, enabled: true } });
    await page.goto("/top-picks");
    await page.getByRole("button", { name: msg("picks-onboard-terminal") }).click();
    await expect(copyField(page, "roleband connect claude-code --apply")).toBeVisible();
    await page.getByRole("combobox", { name: msg("picks-onboard-terminal-host") }).selectOption("codex");
    await expect(copyField(page, "roleband connect codex --apply")).toBeVisible();
    await expect(page.getByText(msg("picks-onboard-in-host", { host: msg("picks-host", { host: "codex" }) }))).toBeVisible();
    await page.getByRole("button", { name: msg("picks-onboard-back") }).click();
    await expect(copyField(page, SENTENCE)).toBeVisible();
  });
});

test.describe("while the conversation saves", () => {
  test("each saved stage shows without a reload, and the list takes over once the checks are set up", async ({ page }) => {
    const held = await installOnboarding(page, { picks: picksStateFixture(), access: connected() });
    await page.goto("/top-picks");
    await expect(page.getByRole("heading", { level: 2, name: msg("picks-onboard-headline") })).toBeVisible();

    held.picks = picksStateFixture({ setup: picksSetupFixture("situation") });
    const host = msg("picks-host", { host: "claude-code" });
    await expect(page.getByRole("heading", { level: 2, name: msg("picks-onboard-under-way") })).toBeVisible({ timeout: 10_000 });
    const now = page.locator('.picks-setup-row[aria-current="step"]');
    await expect(now).toContainText(msg("picks-onboard-row", { step: "situation", host }));
    await expect(now).toContainText(msg("picks-onboard-row-now", { step: "situation" }));

    held.picks = picksStateFixture({ setup: picksSetupFixture("rules") });
    await expect(now).toContainText(msg("picks-onboard-row", { step: "rules", host }), { timeout: 10_000 });
    await expect(page.locator(".picks-setup-row.is-saved")).toHaveCount(4);

    held.picks = healthyState({ setup: picksSetupFixture("done") });
    await expect(page.locator(".job-row").first()).toBeVisible({ timeout: 10_000 });
    await expect(onboarding(page)).toHaveCount(0);
  });
});

test.describe("layout", () => {
  for (const width of [1440, 2000]) {
    test(`at ${width}, the picture, the steps and the sentence sit in one centred column, nothing on anything`, async ({ page, isMobile }) => {
      test.skip(isMobile, "desktop screens only");
      await page.setViewportSize({ width, height: 1000 });
      await installOnboarding(page, { picks: picksStateFixture(), access: { ...agentAccessFixture, enabled: true } });
      await page.goto("/top-picks");
      const section = onboarding(page);
      await expectFullyVisible(copyField(page, SENTENCE), "the sentence");
      const main = (await page.getByRole("main").boundingBox())!;
      const box = (await section.boundingBox())!;
      // The pattern's own measure, whatever the main gives its other children.
      expect(box.width).toBeLessThanOrEqual(920);
      // Centred in the main column, within a pixel.
      expect(Math.abs(box.x - main.x - (main.x + main.width - box.x - box.width))).toBeLessThanOrEqual(2);
      // The picture's field, arrow and card side by side, in that order.
      const [field, arrow, card] = await Promise.all(
        [".picks-picture-field", ".picks-picture-arrow", ".picks-picture-card"].map(async (sel) => (await section.locator(sel).boundingBox())!),
      );
      expect(field.x + field.width).toBeLessThanOrEqual(arrow.x + 0.5);
      expect(arrow.x + arrow.width).toBeLessThanOrEqual(card.x + 0.5);
      expect(overlapping(await laidOut(section, ".onboard-headline, .onboard-line, .picks-picture, .onboard-steps, .onboard-action, .onboard-footnote"))).toEqual([]);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    });
  }

  for (const language of ["es", "zh-Hans"]) {
    test(`in ${language}, every line stays inside its column, the sentence too`, async ({ page, isMobile }) => {
      test.skip(isMobile, "desktop screens only");
      await page.setViewportSize({ width: 1440, height: 1000 });
      await mockGet(page, "/api/settings/locale", (route) => route.fulfill({ json: { language, region: null } }));
      await installOnboarding(page, { picks: picksStateFixture(), access: agentAccessFixture });
      await page.goto("/top-picks");
      await expect(page.locator("html")).toHaveAttribute("lang", language);
      const section = onboarding(page);
      await expect(section.locator(".onboard-headline")).not.toHaveText(msg("picks-onboard-headline"));
      const column = (await section.boundingBox())!;
      for (const box of await laidOut(section, ".onboard-headline, .onboard-line, .ui-copy-field, .picks-onboard-access, .picks-onboard-foot, .onboard-footnote, .picks-picture-reasons li")) {
        expect(box.left, box.what).toBeGreaterThanOrEqual(column.x - 0.5);
        expect(box.right, box.what).toBeLessThanOrEqual(column.x + column.width + 0.5);
      }
      expect(overlapping(await laidOut(section, ".picks-onboard-access, .picks-onboard-say, .ui-copy-field, .picks-onboard-foot"))).toEqual([]);
    });
  }

  test("under way, a long run of stages keeps each row on its line and its state beside it", async ({ page, isMobile }) => {
    test.skip(isMobile, "desktop screens only");
    await page.setViewportSize({ width: 1440, height: 1000 });
    const setup = picksSetupFixture("budget", {
      saved: ["connect", "background", "situation", "bar", "rules", "tradeoffs", "targets"],
      deferred: ["calibration", "trial"],
    });
    await installOnboarding(page, { picks: picksStateFixture({ setup }), access: connected() });
    await page.goto("/top-picks");
    const rows = page.locator(".picks-setup-row");
    await expect(rows).toHaveCount(10);
    await expect(page.locator(".picks-setup-row.is-waits")).toContainText(msg("picks-onboard-row-waits"));
    expect(overlapping(await laidOut(page.locator(".picks-setup-rows"), ".picks-setup-row > *"))).toEqual([]);
  });

  test("in a contrast theme the picture keeps its dots, its pick and its bars", async ({ page, isMobile }) => {
    test.skip(isMobile, "desktop screens only");
    await page.emulateMedia({ forcedColors: "active" });
    await page.setViewportSize({ width: 1440, height: 1000 });
    await installOnboarding(page, { picks: picksStateFixture(), access: agentAccessFixture });
    await page.goto("/top-picks");
    await expect(page.locator(".picks-picture")).toBeVisible();
    const paint = await page.evaluate(() => {
      const style = (selector: string) => getComputedStyle(document.querySelector(selector)!);
      const ground = getComputedStyle(document.querySelector(".onboard")!.closest(".main") ?? document.body).backgroundColor;
      return {
        ground,
        dot: style(".picks-picture-dots > i:not(.is-lit)").backgroundColor,
        lit: style(".picks-picture-dots > i.is-lit").boxShadow,
        bar: style(".picks-picture-bar").backgroundColor,
        arrow: style(".picks-picture-arrow").stroke,
      };
    });
    const blank = (color: string) => color === paint.ground || color === "rgba(0, 0, 0, 0)" || color === "transparent";
    expect(blank(paint.dot), `a dot paints ${paint.dot} on ${paint.ground}`).toBe(false);
    expect(blank(paint.bar), `a bar paints ${paint.bar} on ${paint.ground}`).toBe(false);
    expect(paint.lit, "a lit dot has no ring").toContain("inset");
    expect(blank(paint.arrow), "the arrow has no stroke").toBe(false);
  });

  test("the copy control shows its focus ring inside its own edge", async ({ page, isMobile }) => {
    test.skip(isMobile, "keyboard focus is a desktop claim");
    await page.setViewportSize({ width: 1440, height: 1000 });
    await installOnboarding(page, { picks: picksStateFixture(), access: { ...agentAccessFixture, enabled: true } });
    await page.goto("/top-picks");
    const field = copyField(page, SENTENCE);
    await expect(field).toBeVisible();
    await field.focus();
    await page.keyboard.press("Shift+Tab");
    await page.keyboard.press("Tab");
    await expect(field).toBeFocused();
    const ring = await field.evaluate((el) => {
      const cs = getComputedStyle(el);
      return { style: cs.outlineStyle, width: parseFloat(cs.outlineWidth), offset: parseFloat(cs.outlineOffset) };
    });
    expect(ring.style).not.toBe("none");
    expect(ring.width).toBeGreaterThan(0);
    expect(ring.offset + ring.width).toBeLessThanOrEqual(0);
  });
});
