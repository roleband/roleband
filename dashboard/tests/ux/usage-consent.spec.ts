import AxeBuilder from "@axe-core/playwright";
import { expect, mockGet, test } from "./fixtures";
import { msg } from "../../src/test/msg";
import type { Page } from "./fixtures";
import type { Request } from "@playwright/test";
import {
  facetsFixture, jobListFixture, notificationsFixture, statsFixture, statusFixture, usageStateFixture,
} from "../../src/test/fixtures";
import type { UsageConsent, UsageState } from "../../src/api";
import { scopeCatalog, scopePreview } from "./scopeFixtures";
import { uxProfile } from "./runProfile";

/* Usage sharing asks once, records the words it showed, and never asks over
   the welcome walk (docs/architecture.md):

   - a fresh install is asked between the radar intro and the walk, and Back
     from the walk's first step (setup's, or the browser's) asks again, on the
     answer given, which can be kept or changed;
   - a configured install from before sharing existed is asked once, in a
     dialog whose safe answer has focus and whose Escape is "No thanks";
   - an answered install is not asked; a group widened since is asked alone;
   - Settings > Privacy turns one kind on with the words beside its switch.

   Every request is mocked; the catch-all below fails any other. */

const SAID_USAGE = "Anonymous usage data: Which screens and features you use, and how scans go.";
const SAID_NEVER = "Never sent: Company names, role titles, compensation, your CV or anything you type.";

test.beforeEach(async ({ page }) => {
  await page.route("/api/**", async (route) => {
    await route.abort("blockedbyclient");
    throw new Error(`Unmocked usage-consent API request: ${route.request().method()} ${route.request().url()}`);
  });
  // The page-level guard outranks the context fixtures: repeat the bootstrap reads.
  await page.route("/api/companies/names", (route) => route.fulfill({ json: { names: {} } }));
  await page.route("/api/compare-selection**", (route) => route.fulfill({ json: { job_ids: [] } }));
  await page.route("/api/settings/locale", (route) => route.fulfill({ json: { language: "en", region: null } }));
  await page.route("/api/stats", (route) => route.fulfill({ json: statsFixture }));
  await page.route("/api/status", (route) => route.fulfill({ json: statusFixture }));
  await page.route("/api/facets", (route) => route.fulfill({ json: facetsFixture }));
  await page.route("/api/notifications**", (route) => route.fulfill({ json: notificationsFixture }));
  await page.route("/api/jobs?**", (route) => route.fulfill({ json: jobListFixture }));
  await page.route("/api/scope/catalog", (route) => route.fulfill({ json: scopeCatalog }));
  await page.route("/api/scope/preview", (route) => route.fulfill({ json: scopePreview }));
  await page.route("/api/scope/rules", (route) => route.fulfill({ json: { rules: [] } }));
  await page.route("/api/companies", (route) => route.fulfill({ json: { companies: [] } }));
  // The radar intro says how many companies are within reach.
  await page.route("/api/companies/directory/status", (route) => route.fulfill({
    json: { size: 12_500, following: false, since: null, checked: 0, to_check: 12_500, with_roles: 0, waiting_for_power: false },
  }));
  // An install that already shares starts PostHog's library; answer it here
  // (what it sends is sharing-canary.spec.ts's subject, not this file's).
  await page.route(/^https:\/\/[^/]*posthog\.com\//, (route) => route.fulfill({ status: 200, contentType: "application/json", body: "{}" }));
});

/** Serve `state` for GET /api/usage and record every consent PUT. */
async function usageServer(page: Page, state: UsageState) {
  const answers: UsageConsent[] = [];
  let reads = 0;
  let current = state;
  await page.route("/api/usage", (route) => {
    reads += 1;
    return route.fulfill({ json: current });
  });
  await page.route("/api/usage/consent", async (route) => {
    const body = route.request().postDataJSON() as UsageConsent;
    answers.push(body);
    current = {
      ...current,
      groups: current.groups.map((group) =>
        group.group in body.answers
          ? { ...group, status: body.answers[group.group] ? "shared" : "declined" }
          : group,
      ),
    };
    await route.fulfill({ json: current });
  });
  return { answers, reads: () => reads };
}

/** The shell's question has loaded and drawn its decision, so whether it asks
    is settled. Its lazy module has arrived; React shows content that suspended
    no sooner than 300 ms after its fallback, so a page timer set after that
    began, past it, fires after the reveal is scheduled, under any load; and
    two frames let it draw. */
async function questionDecided(page: Page) {
  await page.waitForFunction(() =>
    performance.getEntriesByType("resource").some((entry) => entry.name.includes("UsageConsentGate")));
  await page.evaluate(() => new Promise((done) => {
    setTimeout(() => requestAnimationFrame(() => requestAnimationFrame(() => done(null))), 400);
  }));
}

async function configured(page: Page) {
  await page.route("/api/profile", (route) => route.fulfill({
    json: { profile: null, scope_configured: true, intent_statement: "" },
  }));
}

const posthogRequests = (page: Page) => {
  const seen: Request[] = [];
  page.on("request", (request) => {
    const { hostname } = new URL(request.url());
    if (hostname === "posthog.com" || hostname.endsWith(".posthog.com")) seen.push(request);
  });
  return seen;
};

test("a fresh install is asked before the walk, and the record is the words it showed", async ({ page }) => {
  await page.route("/api/profile", (route) => route.fulfill({
    json: { profile: null, scope_configured: false, intent_statement: "" },
  }));
  const usage = await usageServer(page, usageStateFixture("undecided"));
  const posthog = posthogRequests(page);

  await page.goto("/");
  await expect(page).toHaveURL(/\/welcome$/);
  await page.getByRole("button", { name: msg("welcome-intro-begin") }).click();

  const question = page.getByRole("region", { name: msg("privacy-consent-title") });
  await expect(question).toBeVisible();
  await expect(question).toContainText("free and open source");
  await expect(question.getByRole("checkbox")).toHaveCount(0);
  await question.getByRole("button", { name: msg("privacy-happy-to-help") }).click();

  await expect(page).toHaveURL(/\/profile\/direction\?setup=1$/);
  await expect(page.getByRole("heading", { name: msg("profile-walk-steps-what-kind-of-role-are") })).toBeVisible();
  expect(usage.answers).toHaveLength(1);
  const [answer] = usage.answers;
  expect(answer.answers).toEqual({ usage: true, crashes: true, questions: true });
  expect(answer.fingerprints).toEqual({
    usage: "usage-fingerprint", crashes: "crashes-fingerprint", questions: "questions-fingerprint",
  });
  expect(answer.locale).toBe("en");
  expect(answer.text.split("\n\n")).toContain(SAID_USAGE);
  expect(answer.text.split("\n\n")).toContain(SAID_NEVER);
  expect(answer.text.startsWith("Help us improve\n\nWe're free and open source")).toBe(true);
  expect(answer.text).not.toContain("Session recordings");
  expect(posthog).toEqual([]);
});

test("declining on the welcome walk shares nothing and the walk goes on", async ({ page }) => {
  await page.route("/api/profile", (route) => route.fulfill({
    json: { profile: null, scope_configured: false, intent_statement: "" },
  }));
  const usage = await usageServer(page, usageStateFixture("undecided"));
  const posthog = posthogRequests(page);
  await page.goto("/welcome");
  await page.getByRole("button", { name: msg("welcome-intro-begin") }).click();
  await page.getByRole("button", { name: msg("privacy-no-thanks") }).click();
  await expect(page).toHaveURL(/\/profile\/direction\?setup=1$/);
  await expect(page.getByRole("heading", { name: msg("profile-walk-steps-what-kind-of-role-are") })).toBeVisible();
  expect(usage.answers.map((a) => a.answers)).toEqual([
    { usage: false, crashes: false, questions: false },
  ]);
  expect(posthog).toEqual([]);
});

test("an answered install goes straight from the intro to the walk", async ({ page }) => {
  await page.route("/api/profile", (route) => route.fulfill({
    json: { profile: null, scope_configured: false, intent_statement: "" },
  }));
  await usageServer(page, usageStateFixture("declined"));
  await page.goto("/welcome");
  await page.getByRole("button", { name: msg("welcome-intro-begin") }).click();
  await expect(page).toHaveURL(/\/profile\/direction\?setup=1$/);
  await expect(page.getByRole("heading", { name: msg("profile-walk-steps-what-kind-of-role-are") })).toBeVisible();
  await expect(page.getByRole("region", { name: msg("privacy-consent-title") })).toHaveCount(0);
});

const fresh = (page: Page) => mockGet(page, "/api/profile", (route) => route.fulfill({
  json: { profile: null, scope_configured: false, intent_statement: "" },
}));
const WALK = /\/profile\/direction\?setup=1$/;
const firstStep = (page: Page) => page.getByRole("heading", { name: msg("profile-walk-steps-what-kind-of-role-are") });

test("an answer given on the welcome is the shell's too: leaving setup does not ask again", async ({ page }) => {
  await fresh(page);
  const usage = await usageServer(page, usageStateFixture("undecided"));
  // The welcome loaded itself (a reload, a bookmark), so the shell may ask on
  // any screen after it, from the state it read before the answer.
  await page.goto("/welcome");
  await page.getByRole("button", { name: msg("welcome-intro-begin") }).click();
  await page.getByRole("button", { name: msg("privacy-no-thanks") }).click();
  await expect(firstStep(page)).toBeVisible();
  await page.getByRole("button", { name: msg("profile-setup-later") }).click();
  await expect(page).toHaveURL(/\/$/);
  await questionDecided(page);
  await expect(page.getByRole("dialog", { name: msg("privacy-consent-title") })).toHaveCount(0);
  expect(usage.answers.map((a) => a.answers)).toEqual([{ usage: false, crashes: false, questions: false }]);
});

/* The shell reads the sharing state once at startup. A read that answers
   after the welcome's answer is older than it, and never undoes it. */
test("a startup read that answers after the welcome's answer does not ask again", async ({ page }) => {
  await fresh(page);
  const usage = await usageServer(page, usageStateFixture("undecided"));
  // The shell's read is sent before the welcome, whose screen is fetched on
  // demand, can send its own: held, with the state as it was, until the
  // answer is in. The dev server's StrictMode sends it twice and aborts the
  // first, so both are held there.
  const shellReads = uxProfile().mode === "dev" ? 2 : 1;
  let release = () => {};
  const held = new Promise<void>((done) => { release = done; });
  const holding: { request: Request; delivered: Promise<void> }[] = [];
  let reads = 0;
  await page.route("/api/usage", (route) => {
    if (route.request().method() !== "GET" || ++reads > shellReads) return route.fallback();
    const before = usageStateFixture("undecided");
    const delivered = held.then(() => route.fulfill({ json: before })).catch(() => { /* aborted by StrictMode */ });
    holding.push({ request: route.request(), delivered });
    return delivered;
  });
  await page.goto("/welcome");
  await page.getByRole("button", { name: msg("welcome-intro-begin") }).click();
  await page.getByRole("button", { name: msg("privacy-no-thanks") }).click();
  await expect(firstStep(page)).toBeVisible();
  expect(holding, "the shell's read was held").toHaveLength(shellReads);
  release();
  await Promise.all(holding.map((read) => read.delivered));
  // The held read is the one the shell kept, and it was answered.
  const answeredReads = await Promise.all(holding.map((read) => read.request.response()));
  expect(answeredReads.filter((response) => response !== null), "the shell's live read was answered late").toHaveLength(1);
  await page.evaluate(() => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(() => done(null)))));
  await page.getByRole("button", { name: msg("profile-setup-later") }).click();
  await expect(page).toHaveURL(/\/$/);
  await questionDecided(page);
  await expect(page.getByRole("dialog", { name: msg("privacy-consent-title") })).toHaveCount(0);
  expect(usage.answers.map((a) => a.answers)).toEqual([{ usage: false, crashes: false, questions: false }]);
});

test("Back from setup's first step asks again on the answer given, marked, and Enter on it records nothing", async ({ page }) => {
  await fresh(page);
  const usage = await usageServer(page, usageStateFixture("undecided"));
  await page.goto("/welcome");
  await page.getByRole("button", { name: msg("welcome-intro-begin") }).click();
  await page.getByRole("button", { name: msg("privacy-no-thanks") }).click();
  await expect(firstStep(page)).toBeVisible();
  await page.getByLabel(msg("profile-walk-model-leading-a-team")).check();

  await page.getByRole("button", { name: msg("profile-welcome-wizard-back") }).click();
  await expect(page).toHaveURL(/\/welcome$/);
  const question = page.getByRole("region", { name: msg("privacy-consent-title") });
  const no = question.getByRole("button", { name: msg("privacy-no-thanks") });
  const yes = question.getByRole("button", { name: msg("privacy-happy-to-help") });
  await expect(no).toHaveAccessibleDescription(msg("privacy-your-answer"));
  await expect(yes).not.toHaveAccessibleDescription(msg("privacy-your-answer"));
  // Marked by its look too, not only by its caption.
  const edge = (button: typeof no) => button.evaluate((el) => getComputedStyle(el).borderColor);
  expect(await edge(no)).not.toBe(await edge(yes));
  // A mark, not a third answer: the two answers and the way to choose.
  await expect(question.getByRole("button")).toHaveCount(3);
  // The pointer over the answer given leaves its mark: hover moves the fill,
  // never the edge that says which answer it is.
  const marked = await edge(no);
  await no.hover();
  await no.evaluate((el) => Promise.all(el.getAnimations().map((animation) => animation.finished)));
  expect(await edge(no)).toBe(marked);
  // The intro is not played again, and Enter is on the answer given.
  await expect(page.getByRole("button", { name: msg("welcome-intro-begin") })).toHaveCount(0);
  await expect(no).toBeFocused();
  await page.keyboard.press("Enter");

  await expect(page).toHaveURL(WALK);
  await expect(page.getByLabel(msg("profile-walk-model-leading-a-team"))).toBeChecked();
  expect(usage.answers.map((a) => a.answers)).toEqual([{ usage: false, crashes: false, questions: false }]);
});

test("the browser's Back from the walk asks again too, and a changed answer records the words anew", async ({ page }) => {
  await fresh(page);
  const usage = await usageServer(page, usageStateFixture("undecided"));
  await page.goto("/welcome");
  await page.getByRole("button", { name: msg("welcome-intro-begin") }).click();
  await page.getByRole("button", { name: msg("privacy-happy-to-help") }).click();
  await expect(firstStep(page)).toBeVisible();

  await page.goBack();
  const question = page.getByRole("region", { name: msg("privacy-consent-title") });
  await expect(question.getByRole("button", { name: msg("privacy-happy-to-help") })).toHaveAccessibleDescription(msg("privacy-your-answer"));
  // Enter on the marked answer changes nothing, so it has the keyboard.
  await expect(question.getByRole("button", { name: msg("privacy-happy-to-help") })).toBeFocused();
  // Changing the answer: only crash reports now.
  await question.getByRole("button", { name: msg("privacy-choose") }).click();
  for (const kind of [msg("privacy-group-usage"), msg("privacy-group-crashes"), msg("privacy-group-questions")]) {
    await expect(question.getByRole("checkbox", { name: kind })).toBeChecked();
  }
  await question.getByRole("checkbox", { name: msg("privacy-group-usage") }).uncheck();
  await question.getByRole("checkbox", { name: msg("privacy-group-questions") }).uncheck();
  await question.getByRole("button", { name: msg("privacy-happy-to-help") }).click();
  await expect(firstStep(page)).toBeVisible();

  expect(usage.answers.map((a) => a.answers)).toEqual([
    { usage: true, crashes: true, questions: true },
    { usage: false, crashes: true, questions: false },
  ]);
  expect(usage.answers[1].text).toBe(usage.answers[0].text);

  // Asked a third time, it opens on exactly that choice.
  await page.getByRole("button", { name: msg("profile-welcome-wizard-back") }).click();
  await expect(question.getByRole("button", { name: msg("privacy-happy-to-help") })).toHaveAccessibleDescription(msg("privacy-your-answer"));
  await expect(question.getByRole("checkbox", { name: msg("privacy-group-crashes") })).toBeChecked();
  await expect(question.getByRole("checkbox", { name: msg("privacy-group-usage") })).not.toBeChecked();
  await expect(question.getByRole("checkbox", { name: msg("privacy-group-questions") })).not.toBeChecked();
});

test("with sharing switched off on this computer, Back from the walk opens the intro, whose button goes on", async ({ page }) => {
  await fresh(page);
  const usage = await usageServer(page, usageStateFixture("undecided", { blocked_by: "DO_NOT_TRACK" }));
  await page.goto("/welcome");
  await page.getByRole("button", { name: msg("welcome-intro-begin") }).click();
  await expect(firstStep(page)).toBeVisible();
  await page.getByRole("button", { name: msg("profile-welcome-wizard-back") }).click();
  await expect(page).toHaveURL(/\/welcome$/);
  // No bounce straight back to the walk, and no question to ask.
  await expect(page.getByRole("button", { name: msg("welcome-intro-begin") })).toBeVisible();
  await expect(page.getByRole("region", { name: msg("privacy-consent-title") })).toHaveCount(0);
  await page.getByRole("button", { name: msg("welcome-intro-begin") }).click();
  await expect(firstStep(page)).toBeVisible();
  expect(usage.answers).toEqual([]);
});

test("a configured install is asked once; the safe answer has focus and Escape declines", async ({ page }) => {
  await configured(page);
  const usage = await usageServer(page, usageStateFixture("undecided"));
  await page.goto("/");
  const dialog = page.getByRole("dialog", { name: msg("privacy-consent-title") });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("button", { name: msg("privacy-no-thanks") })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect.poll(() => usage.answers.length).toBe(1);
  expect(usage.answers[0].answers).toEqual({ usage: false, crashes: false, questions: false });
});

test("ticking kinds in the dialog shares exactly those, and the dialog fits a phone", async ({ page }) => {
  await configured(page);
  await page.setViewportSize({ width: 375, height: 740 });
  const usage = await usageServer(page, usageStateFixture("undecided"));
  await page.goto("/");
  const dialog = page.getByRole("dialog", { name: msg("privacy-consent-title") });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("Session recordings")).toHaveCount(0);
  await dialog.getByRole("button", { name: msg("privacy-choose") }).click();
  // Clicking the row's sentence ticks its box: the row is the hit target.
  await dialog.getByText(msg("privacy-group-questions-detail")).click();
  await expect(dialog.getByRole("checkbox", { name: msg("privacy-group-questions") })).toBeChecked();
  await expect(dialog.getByRole("checkbox", { name: msg("privacy-group-crashes") })).not.toBeChecked();
  // Nothing is cut off at phone width: no sideways scroll, both answers visible side by side.
  const overflow = await dialog.evaluate((node) => node.scrollWidth - node.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  const decline = await dialog.getByRole("button", { name: msg("privacy-no-thanks") }).boundingBox();
  const share = await dialog.getByRole("button", { name: msg("privacy-happy-to-help") }).boundingBox();
  expect(decline && share && Math.abs(decline.width - share.width)).toBeLessThan(1);
  expect(decline && share && Math.abs(decline.y - share.y)).toBeLessThan(1);
  await dialog.getByRole("button", { name: msg("privacy-happy-to-help") }).click();
  await expect(dialog).toHaveCount(0);
  expect(usage.answers.map((a) => a.answers)).toEqual([{ usage: false, crashes: false, questions: true }]);
});

test("an answered install is not asked", async ({ page }) => {
  await configured(page);
  await usageServer(page, usageStateFixture("shared"));
  // Count the reads that FINISH, not the requests: under the dev server
  // React's StrictMode mounts App twice and the first read is aborted on
  // cleanup, so a request count of 1 holds only against the build. An aborted
  // read fails; the read the app keeps finishes, once, in both modes.
  let finished = 0;
  page.on("requestfinished", (request) => {
    if (new URL(request.url()).pathname === "/api/usage") finished += 1;
  });
  await page.goto("/");
  await expect.poll(() => finished).toBeGreaterThan(0);
  await questionDecided(page);
  await expect(page.getByRole("dialog", { name: msg("privacy-consent-title") })).toHaveCount(0);
  expect(finished, "the sharing state is read once").toBe(1);
});

test("a group widened since it was shared is asked alone", async ({ page }) => {
  await configured(page);
  const state = usageStateFixture("shared");
  state.groups = state.groups.map((group) => (group.group === "crashes" ? { ...group, status: "stale" } : group));
  const usage = await usageServer(page, state);
  await page.goto("/");
  const dialog = page.getByRole("dialog", { name: msg("privacy-consent-title") });
  await expect(dialog.getByText(msg("privacy-group-crashes"))).toBeVisible();
  await expect(dialog.getByText(msg("privacy-group-usage"))).toHaveCount(0);
  // One kind: nothing to choose between.
  await expect(dialog.getByRole("button", { name: msg("privacy-choose") })).toHaveCount(0);
  await dialog.getByRole("button", { name: msg("privacy-happy-to-help") }).click();
  await expect(dialog).toHaveCount(0);
  expect(usage.answers.map((a) => a.answers)).toEqual([{ crashes: true }]);
});

test("Settings › Privacy turns one kind on with the words beside it", async ({ page }) => {
  await configured(page);
  const usage = await usageServer(page, usageStateFixture("declined", { pending_events: 1 }));
  await page.route("/api/usage/preview", (route) => route.fulfill({
    json: { body: { api_key: "phc_test", batch: [{ event: "daily_action", properties: { action: "save_job", count: 3 } }] }, left_out: 0 },
  }));
  await page.goto("/settings/privacy");
  const usageSwitch = page.getByRole("checkbox", { name: msg("privacy-group-usage") });
  await expect(usageSwitch).not.toBeChecked();
  await usageSwitch.click();
  await expect(usageSwitch).toBeChecked();
  expect(usage.answers).toHaveLength(1);
  expect(usage.answers[0].answers).toEqual({ usage: true });
  expect(usage.answers[0].text.split("\n\n")).toEqual(["Help us improve", SAID_USAGE, SAID_NEVER]);
  await page.getByRole("button", { name: msg("privacy-show-next") }).click();
  await expect(page.getByLabel(msg("privacy-next-send"))).toContainText('"action": "save_job"');
});

test.describe("accessibility", () => {
  // As the a11y sweep does: a dialog caught mid fade-in has blended colours.
  test.use({ contextOptions: { reducedMotion: "reduce" } });

test("the question passes axe in both themes", async ({ page }) => {
  await configured(page);
  await usageServer(page, usageStateFixture("undecided"));
  for (const theme of ["light", "dark"] as const) {
    await page.addInitScript((value) => localStorage.setItem("theme", value), theme);
    await page.goto("/");
    await expect(page.getByRole("dialog", { name: msg("privacy-consent-title") })).toBeVisible();
    await page.evaluate(async () => {
      await document.fonts.ready;
      await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
    });
    const { violations } = await new AxeBuilder({ page }).include('[role="dialog"]').analyze();
    const serious = violations.filter((v) => v.impact === "serious" || v.impact === "critical");
    expect(serious.map((v) => `${theme} ${v.id}: ${v.nodes.map((node) => `${node.target.join(" ")} ${node.failureSummary ?? ""}`).join(" | ")}`)).toEqual([]);
  }
});
});
