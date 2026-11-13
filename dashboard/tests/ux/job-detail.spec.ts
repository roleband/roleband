/* The opportunity detail: what the full-screen cover shows, how it is reached,
   and what it writes. The shell is full-screen, so its entry paths (row
   click, /job/:id, company-scoped URL, back/forward) are the contract. */

import type { Locator, Page } from "@playwright/test";
import { msg } from "../../src/test/msg";
import { expect, mockApi, mockGet, test, watchReads } from "./fixtures";
import { applicationCardFixture, applicationDetailFixture, compPackageFixture, jobFixture } from "../../src/test/fixtures";
import { appleJobFixture, comparison, detail, installBoardRoutes, jobFixture2, twoJobList } from "./boardHarness";
import { expectOnTop, pointAndClick, strangersOver } from "./paint";

/* Controls named by what the catalog says, so a copy edit cannot fail a test
   that is not about copy. A stage button carries its days after the stage, and
   the stage menu its posting's title, so both stay prefixes. */
const STAGE_APPLIED = new RegExp(`^${msg("taxonomy-stage-applied")}\\b`);
const STAGE_MENU = new RegExp(`^${msg("applications-stage-menu-label", { title: "" }).trimEnd()}`);
const VIEW_APPLY = new RegExp(msg("role-job-detail-view-apply"), "i");

test.beforeEach(async ({ page }) => {
  await installBoardRoutes(page);
});

test("opening an opportunity shows a full-screen detail that fills the viewport", async ({ page }) => {
  await page.goto("/");

  const mission = page.getByRole("banner", { name: msg("shell-topbar-aria") });
  await expect(mission).toContainText("Radar");
  await expect(mission.locator(".stat-chip").nth(0)).toHaveAttribute("aria-label", msg("shell-stat-open-aria", { count: 1 }));
  await expect(mission.locator(".stat-chip").nth(1)).toHaveAttribute("aria-label", "1 new in the last 2 days");
  await expect(mission.getByRole("status", { name: /Last scan/ })).toContainText("Last scan");
  await expect(page.getByRole("main")).toContainText("2 roles");
  await expect(page.getByRole("status", { name: /Last scan/ })).toContainText(msg("shell-freshness-checked", { age: msg("format-age-hours", { count: 2 }) }));
  await expect(page.getByText("Staff Product Manager, API")).toBeVisible();
  // The row's pay is the base: the fixture posts no base range, so its estimate.
  await expect(page.locator(`[data-job-id="${jobFixture.id}"] .comp`)).toHaveText(/^\$400K /);

  await page.getByText("Staff Product Manager, API").click();

  const panel = detail(page);
  await expect(panel).toBeVisible();
  await expect(panel.getByRole("heading", { name: "Staff Product Manager, API" })).toBeVisible();
  await expect(panel).toContainText("Lead API product strategy.");
  await expect(panel.getByRole("link", { name: VIEW_APPLY })).toHaveAttribute("href", jobFixture.url);

  // Full-screen: the detail covers the whole viewport, not a narrow side panel.
  const viewport = page.viewportSize()!;
  const box = await panel.boundingBox();
  expect(box!.width).toBeGreaterThan(viewport.width - 2);
  expect(box!.height).toBeGreaterThan(viewport.height - 2);
});

test("an open role cover leaves one h1 and an inert page behind it", async ({ page }) => {
  // Fail-first: the list stayed in the accessibility tree under the cover,
  // so the document had two h1s and a virtual cursor read the list.
  await page.goto("/");
  await page.getByText("Staff Product Manager, API").click();
  const panel = detail(page);
  await expect(panel).toBeVisible();

  const reachable = () => page.locator("h1").evaluateAll((hs) => hs.filter((h) => !h.closest("[inert]")).length);
  await expect.poll(reachable).toBe(1);
  await expect(page.locator(".workspace")).toHaveAttribute("inert", "");
  await expect(page.locator(".nav-rail")).toHaveAttribute("inert", "");
  await expect(panel).not.toHaveAttribute("inert", "");

  await page.keyboard.press("Escape");
  await expect(panel).toBeHidden();
  await expect(page.locator(".workspace")).not.toHaveAttribute("inert", "");
  await expect(page.locator(".nav-rail")).not.toHaveAttribute("inert", "");
});

// Sources publish a run of cities in one string, then each again on its own:
// "San Francisco, CA | New York City, NY" and then "New York City, NY" a
// second time.
test("a posting that names a city twice lists each place once", async ({ page }) => {
  await mockGet(page, "/api/jobs/101", (route) => route.fulfill({ json: {
    ...jobFixture, locations: ["San Francisco, CA | New York City, NY", "New York City, NY"],
  } }));
  await page.goto("/job/101");

  const meta = detail(page).locator(".job-meta");
  await expect(meta.getByText("San Francisco, CA", { exact: true })).toHaveCount(1);
  await expect(meta.getByText("New York City, NY", { exact: true })).toHaveCount(1);
  await expect(meta).not.toContainText("|");
});

// The place line already says the country, and the region follows from it:
// only the metro area is news.
test("the place tags add only what the place line does not say", async ({ page }) => {
  await mockGet(page, "/api/jobs/101", (route) => route.fulfill({ json: {
    ...jobFixture,
    locations: ["Sunnyvale, CA, USA"],
    location_groups: ["silicon_valley", "united_states", "north_america", "city_5400075"],
  } }));
  await page.goto("/job/101");

  const meta = detail(page).locator(".job-meta");
  await expect(meta.getByText("Sunnyvale, CA, USA", { exact: true })).toBeVisible();
  await expect(meta.getByText("Silicon Valley", { exact: true })).toBeVisible();
  await expect(meta.getByText("United States", { exact: true })).toHaveCount(0);
  await expect(meta.getByText("North America", { exact: true })).toHaveCount(0);
});

// A board writes one office several ways beside bare countries; the server
// sends the places once each, and the line reads that, never the raw strings.
test("the place line reads the server's tidied places over the source's own strings", async ({ page }) => {
  await mockGet(page, "/api/jobs/101", (route) => route.fulfill({ json: {
    ...jobFixture,
    locations: ["GB", "Dublin, D, IE", "United Kingdom, Multiple Locations, Multiple Locations", "Ireland, Dublin, Dublin"],
    location_groups: ["ireland", "uk", "europe"],
    places: ["Dublin, Ireland", "United Kingdom"],
  } }));
  await page.goto("/job/101");

  const meta = detail(page).locator(".job-meta");
  await expect(meta.getByText("Dublin, Ireland", { exact: true })).toBeVisible();
  await expect(meta.getByText("United Kingdom", { exact: true })).toBeVisible();
  await expect(meta).not.toContainText("Multiple Locations");
  await expect(meta).not.toContainText("Dublin, D, IE");
  await expect(meta).not.toContainText("GB");
});

test("Apple detail preserves source sections and Pay & Benefits", async ({ page }) => {
  await page.goto("/job/303");

  const panel = detail(page);
  await expect(panel.getByRole("heading", { name: "Summary" })).toBeVisible();
  await expect(panel.getByRole("heading", { name: "Minimum Qualifications" })).toBeVisible();
  await expect(panel.getByRole("heading", { name: "Pay & Benefits" })).toBeVisible();
  await expect(panel.getByText(/\$250,800 and \$376,300/)).toBeVisible();
  await expect(panel.getByText("10+ years of product management experience")).toBeVisible();
  await expect(panel.getByText("Legacy fallback should not replace structured sections.")).toHaveCount(0);
});

const readyRequirements = {
  state: "ready",
  extractor_version: "test",
  qualifications: [],
  required_years: null,
  skills: [
    {
      concept_id: 1,
      slug: "python",
      facet: "technology",
      category: "Languages",
      importance_band: "core",
      importance_score: 1,
      confidence: "high",
      modality: "required",
      evidence: [],
    },
  ],
};

// The description is the screen's long read, so it is set for reading: the
// reading size of the posting's step, the text colour of the heading above it
// (not the muted one), across the column under the pay panel, edge to edge
// with it. The role requirements panel is off the posting.
//
// The measuring tests below open the company-scoped URL. A short /job/:id
// rewrites itself once the job loads, which remounts the whole detail, so a
// one-shot measurement taken after the first paint can land on nodes the
// remount has already detached: `boundingBox()` answers null and a query
// finds nothing.
const READ_PX = 17;
/** How long the first posting a cover turns to may take to show. The Docker
 *  WebKit draws a view transition in software and holds the page for seconds
 *  over its first one (after which the app gives it no more). */
const FIRST_TURN = { timeout: 20_000 };
for (const [width, read] of [[1440, READ_PX], [1600, 18]] as const) {
  test(`the description is set for reading at ${width}px, under the pay panel`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await mockGet(page, "/api/jobs/303", (route) =>
      route.fulfill({ json: { ...appleJobFixture, requirements: readyRequirements } }),
    );
    await page.goto("/company/apple/job/303");

    const panel = detail(page);
    const card = panel.locator(".comp-panel");
    await expect(card).toBeVisible();
    await expect(panel.locator(".req-panel"), "no requirements panel, even for a posting that has them").toHaveCount(0);
    const cardBox = (await card.boundingBox())!;
    const ink = await panel.locator(".jd-hero h1").evaluate((el) => getComputedStyle(el).color);

    for (const heading of ["Summary", "Minimum Qualifications"]) {
      const section = panel.locator(".jd-section").filter({ has: page.getByRole("heading", { name: heading }) });
      const box = (await section.boundingBox())!;
      expect(Math.abs(box.x - cardBox.x), `${heading} left edge`).toBeLessThanOrEqual(1);
      expect(Math.abs(box.width - cardBox.width), `${heading} spans the column`).toBeLessThanOrEqual(1);
      const text = section.locator("p, li").first();
      expect(await text.evaluate((el) => [getComputedStyle(el).fontSize, getComputedStyle(el).color])).toEqual([`${read}px`, ink]);
    }
  });
}

test("a plain-text description is set for reading too", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockGet(page, "/api/jobs/101", (route) =>
    route.fulfill({ json: { ...jobFixture, requirements: readyRequirements } }),
  );
  await page.goto("/company/openai/job/101");

  const panel = detail(page);
  const card = panel.locator(".comp-panel");
  const text = panel.locator(".jd-fallback");
  await expect(card).toBeVisible();
  await expect(text).toContainText("Lead API product strategy.");
  const cardBox = (await card.boundingBox())!;
  const box = (await text.boundingBox())!;
  expect(Math.abs(box.x - cardBox.x)).toBeLessThanOrEqual(1);
  expect(Math.abs(box.width - cardBox.width), "spans the column").toBeLessThanOrEqual(1);
  expect(await text.evaluate((el) => getComputedStyle(el).fontSize)).toBe(`${READ_PX}px`);
});

/* A section's text keeps its shape: a short line ending in a colon is a
   sub-heading, a run of unfinished one-line paragraphs is a list, and prose
   stays prose (features/job-detail/descriptionShape.ts). */
test("a section's sub-headings and lists are drawn as headings and lists", async ({ page }) => {
  await mockGet(page, "/api/jobs/303", (route) => route.fulfill({ json: { ...appleJobFixture, description_sections: [
    { key: "the_role", title: "The role", content: [
      "This role looks across forty offices.", "A typical day:", "Run a portfolio of programs",
      "Map one process end to end", "Coach two program managers", "We decide in writing.",
      "Team Leadership", "Hire and develop the engineers on site. Set clear expectations.",
    ].join("\n\n") },
  ] } }));
  await page.goto("/company/apple/job/303");
  const section = detail(page).locator(".jd-section");
  await expect(section.getByRole("heading", { level: 3, name: "A typical day" })).toBeVisible();
  await expect(section.getByRole("listitem")).toHaveText(["Run a portfolio of programs", "Map one process end to end", "Coach two program managers"]);
  // A title with no colon, standing before whole sentences, is a sub-heading too.
  await expect(section.getByRole("heading", { level: 3, name: "Team Leadership" })).toBeVisible();
  await expect(section.locator("p")).toHaveText([
    "This role looks across forty offices.", "We decide in writing.",
    "Hire and develop the engineers on site. Set clear expectations.",
  ]);
});

// Ragged right, words whole: justified lines stretch the spaces of a short
// list item and break words at the line's end, and both slow reading down.
const descriptionSetting = (page: import("@playwright/test").Page) =>
  detail(page).locator(".jd-section p, .jd-section li").evaluateAll((els) =>
    els.map((el) => {
      const s = getComputedStyle(el);
      return { align: s.textAlign, hyphens: s.hyphens || s.getPropertyValue("-webkit-hyphens") };
    }),
  );

for (const [name, size] of [["a wide screen", { width: 1440, height: 900 }], ["a phone", { width: 375, height: 812 }]] as const) {
  test(`the description is left-aligned and breaks no word on ${name}`, async ({ page }) => {
    await page.setViewportSize(size);
    await page.goto("/company/apple/job/303");
    await expect(detail(page).getByRole("heading", { name: "Summary" })).toBeVisible();

    const settings = await descriptionSetting(page);
    expect(settings.length).toBeGreaterThan(2);
    for (const setting of settings) expect(setting).toEqual({ align: "start", hyphens: "manual" });
  });
}

test("a role with no twins never asks for them", async ({ page }) => {
  const twins = watchReads(page, "GET", "/api/jobs/101/twins");
  const placeSet = watchReads(page, "GET", "/api/jobs/101/place-set");
  await page.goto("/job/101");
  await expect(page.getByText("View & apply")).toBeVisible();
  // Its sibling section asks as the page opens, so by its answer the deck would have asked too.
  await expect.poll(() => placeSet.answered).toBeGreaterThan(0);
  expect(twins.started).toBe(0);
  await expect(page.getByRole("button", { name: /Has a related role/ })).toHaveCount(0);
});

test("a confirmed twin opens as a paper stack and compares full descriptions", async ({ page }) => {
  await page.route("/api/jobs/101", (route) => route.fulfill({ json: { ...jobFixture, twin_count: 1 } }));
  await page.route("/api/jobs/101/twins", (route) => route.fulfill({ json: {
    job_id: 101,
    size: 3,
    direct_count: 1,
    members: [
      { job: jobFixture, direct: false, link: null },
      { job: jobFixture2, direct: true, link: { proposal_kind: "twin", id: 8 } },
      { job: appleJobFixture, direct: false, link: null },
    ],
  } }));

  await page.goto("/job/101");
  await page.getByRole("button", { name: /Has a related role/ }).click();
  await expect(page.getByText("Principal Engineer, Platform")).toBeVisible();
  await expect(page.getByText(/Head of Product, Global AI Learning Platform/)).toBeVisible();
  await expect(page.getByText(/not directly related/)).toBeVisible();

  /* One primary per surface. Job detail's is "View & apply" — the
     one thing that page exists for — so opening this disclosure must not put a
     second filled button beside it. A rank rule of "primary = commits state"
     cannot express this: neither of these two commits anything. */
  const primaries = await page.locator(".ui-btn-primary:visible").allInnerTexts();
  expect(
    primaries.map((t) => t.trim()),
    "more than one primary is visible on Job detail",
  ).toEqual(["View & apply"]);

  await page.getByRole("button", { name: "Compare with related roles" }).click();
  await expect(page).toHaveURL(/\/compare$/);
  /* Compare folds each description pair behind its own line, so the
     comparison is one click in, and each region is named for the ROLE it reads
     against the baseline rather than all sharing one name. */
  /* The comparison covers the role page it opened from. Each
     twin's description sits under its role, and what only one posting says
     is on screen at once — no baseline, nothing to unfold. */
  const cover = comparison(page);
  await expect(cover.locator(".cmp-prose").filter({ hasText: "Lead API product strategy." })).toHaveCount(1);
  await expect(cover.locator(".cmp-prose").filter({ hasText: "Own core platform reliability." })).toHaveCount(1);
});

test("each opportunity's URL nests it under its company", async ({ page }) => {
  await page.goto("/");

  // A position is a sub-resource of its company: /company/<slug>/job/<id>.
  await page.getByText("Staff Product Manager, API").click();
  await expect(page).toHaveURL(/\/company\/openai\/job\/101$/);
  await expect(detail(page).getByRole("heading", { name: "Staff Product Manager, API" })).toBeVisible();

  await page.getByRole("button", { name: "Back" }).click();
  await expect(page).toHaveURL(/\/$/);

  await page.getByText("Principal Engineer, Platform").click();
  await expect(page).toHaveURL(/\/company\/openai\/job\/202$/);
  await expect(detail(page).getByRole("heading", { name: "Principal Engineer, Platform" })).toBeVisible();
});

test("a short /job/:id link canonicalizes to the company-scoped URL and reloads", async ({ page }) => {
  await page.goto("/job/202");

  // The flat /job/:id link still resolves, then rewrites itself to the nested form.
  await expect(page).toHaveURL(/\/company\/openai\/job\/202$/);
  const panel = detail(page);
  await expect(panel.getByRole("heading", { name: "Principal Engineer, Platform" })).toBeVisible();
  await expect(panel.getByRole("link", { name: VIEW_APPLY })).toHaveAttribute("href", jobFixture2.url);

  // Refresh on the canonical URL keeps the same opportunity.
  await page.reload();
  await expect(page).toHaveURL(/\/company\/openai\/job\/202$/);
  await expect(detail(page).getByRole("heading", { name: "Principal Engineer, Platform" })).toBeVisible();

  // From a direct link there is no in-app history, so Back returns to the board.
  await page.getByRole("button", { name: "Back" }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("main")).toContainText("2 roles");
});

// Rewriting the URL is not a new page: the role drawn from the first URL is the
// one still on screen, not a second copy drawn after a reload of the detail.
for (const entry of ["/job/202", "/company/not-openai/job/202"]) {
  test(`${entry} rewrites its URL without drawing the role twice`, async ({ page }) => {
    await page.addInitScript(() => {
      const drawn = new Set<Element>();
      new MutationObserver(() => {
        for (const title of document.querySelectorAll(".jd-hero h1")) drawn.add(title);
      }).observe(document, { childList: true, subtree: true });
      (window as unknown as { roleTitlesDrawn: () => number }).roleTitlesDrawn = () => drawn.size;
    });
    const drawn = () => page.evaluate(() => (window as unknown as { roleTitlesDrawn: () => number }).roleTitlesDrawn());

    await page.goto(entry);
    await expect(page).toHaveURL(/\/company\/openai\/job\/202$/);
    await expect(detail(page).getByRole("heading", { name: "Principal Engineer, Platform" })).toBeVisible();
    // Past every fetch a remount would make again.
    await page.waitForLoadState("networkidle");
    expect(await drawn()).toBe(1);
  });
}

test("browser back and forward move between the board and an opportunity", async ({ page }) => {
  await page.goto("/");
  await page.getByText("Staff Product Manager, API").click();
  await expect(page).toHaveURL(/\/company\/openai\/job\/101$/);
  await expect(detail(page)).toBeVisible();

  await page.goBack();
  await expect(page).toHaveURL(/\/$/);
  await expect(detail(page)).toHaveCount(0);
  await expect(page.getByRole("main")).toContainText("2 roles");

  await page.goForward();
  await expect(page).toHaveURL(/\/company\/openai\/job\/101$/);
  await expect(detail(page).getByRole("heading", { name: "Staff Product Manager, API" })).toBeVisible();
});

/* ---- one scroll ---------------------------------------------------------- *
 *
 * The Board scrolls the way Settings > Companies scrolls: `.main`
 * is the ONE scroller, the hero slides away like any page content, the
 * toolbar docks at the top through the shared `.app-toolbar` recipe, and the
 * column head and the filter register pin beneath it at the toolbar's
 * measured height. A page of roles is rendered IN FULL in the flow — no inner
 * scroll windows anywhere — and the list wears the register's ledger
 * treatment (no floating-card frame), which is what makes rows sliding under
 * an opaque pinned band drawable at all.
 *
 * The register renders as the left rail from 1360px; below that the toolbar
 * carries a "Filters · N" opener over the same component.
 */

/* The bar holds one control for where the person stands with the role. Off
   the pipeline it is the star; once saved, the star's place holds the
   pipeline's own stage button, and the side column gains a Pipeline section:
   the stage, its days, and what waits, in plain words. The stage is changed
   in the bar and read in the section. Nothing about the pipeline shows
   before the role is in it. */
const DAY = 86_400_000;
const tomorrowNoon = () => {
  const d = new Date();
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() + 1, 12).toISOString();
};
const appliedPursuit = {
  id: 10, job_id: 101, stage: "applied", priority: 3, notes: null, next_action: "Email the recruiter",
  next_action_due: null, created_at: "2026-10-20T09:00:00Z", updated_at: "2026-10-29T09:00:00Z",
};

test("a save that fails reads the posting back, and shows the stage the role reached elsewhere", async ({ page }) => {
  // Another window moves the role to Applied while this posting shows it off
  // the pipeline; this window's save then fails.
  let movedElsewhere = false;
  await mockGet(page, "/api/jobs/101", (route) => route.fulfill({ json: movedElsewhere
    ? { ...jobFixture, is_favorite: false, pursuit: appliedPursuit }
    : { ...jobFixture, is_favorite: false, pursuit: null } }));
  await mockGet(page, "/api/applications/101", (route) => (movedElsewhere
    ? route.fulfill({ json: applicationDetailFixture({
      application: applicationCardFixture({ pursuit_id: 10, stage: "applied", starred: false, stage_since: new Date(Date.now() - 2 * DAY).toISOString() }),
    }) })
    : route.fulfill({ status: 404, json: { detail: "not on the board" } })));
  await mockApi(page, "PUT", "/api/jobs/101/favorite", (route) => {
    movedElsewhere = true;
    return route.fulfill({ status: 500, json: { detail: "unavailable" } });
  });
  await page.goto("/company/openai/job/101");
  const bar = detail(page).locator(".cover-bar");
  await bar.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Couldn't save this role" })).toBeVisible();
  await expect(bar.getByRole("button", { name: "Applied", exact: true }), "where the role stands now").toBeVisible();
  await expect(bar.getByRole("button", { name: "Save", exact: true })).toHaveCount(0);
});

test("a role off the pipeline shows the star alone, and saving turns it into the stage in its place", async ({ page }) => {
  let saved = false;
  await mockApi(page, "PUT", "/api/jobs/101/favorite", (route) => {
    saved = true;
    return route.fulfill({ json: { job_id: 101, is_favorite: true } });
  });
  await mockGet(page, "/api/applications/101", (route) => saved
    ? route.fulfill({ json: applicationDetailFixture({
      application: applicationCardFixture({ stage: "saved", stage_since: new Date().toISOString() }),
      stages_reached: [{ stage: "saved", at: new Date().toISOString() }],
    }) })
    : route.fulfill({ status: 404, json: { detail: { code: "application-not-found" } } }));
  await page.goto("/company/openai/job/101");
  const panel = detail(page);
  await expect(panel.getByRole("heading", { name: "Staff Product Manager, API" })).toBeVisible();

  await expect(panel.getByText("Your progress")).toHaveCount(0);
  await expect(panel.locator(".jd-aside .section-title", { hasText: msg("applications-posting-row") })).toHaveCount(0);
  await expect(panel.getByRole("link", { name: VIEW_APPLY })).toHaveClass(/ui-btn-primary/);

  await panel.getByRole("button", { name: msg("jobs-save"), pressed: false }).click();
  // Saved just now: the stage alone, with no count of days.
  await expect(panel.getByRole("button", { name: "Considering", exact: true })).toBeVisible();
  await expect(panel.getByRole("button", { name: msg("jobs-save") }), "the stage takes the star's place").toHaveCount(0);
  const facts = panel.locator("dl.jd-pipeline-facts");
  await expect(facts.locator("dd").first()).toHaveText(msg("taxonomy-stage-saved"));
  await expect(facts).toContainText(msg("applications-posting-since-today"));
  // Nothing waits yet: no row says so.
  await expect(facts.getByText(msg("applications-posting-next-step"), { exact: true })).toHaveCount(0);
  await expect(facts.getByText(msg("applications-posting-interview"), { exact: true })).toHaveCount(0);
  // Still deciding: applying stays the action.
  await expect(panel.getByRole("link", { name: VIEW_APPLY })).toHaveClass(/ui-btn-primary/);
});

test("an applied role names its stage in the bar, and its days and what is due in the Pipeline section", async ({ page }) => {
  await mockGet(page, "/api/jobs/101", (route) => route.fulfill({ json: { ...jobFixture, is_favorite: true, pursuit: appliedPursuit } }));
  await mockGet(page, "/api/applications/101", (route) => route.fulfill({ json: applicationDetailFixture({
    application: applicationCardFixture({
      pursuit_id: 10, stage: "applied", stage_since: new Date(Date.now() - 12 * DAY).toISOString(),
      next_action: "Email the recruiter", next_action_due: tomorrowNoon(),
    }),
  }) }));
  await page.goto("/company/openai/job/101");
  const panel = detail(page);
  const bar = panel.locator(".cover-bar");

  await expect(bar.getByRole("button", { name: "Applied", exact: true })).toBeVisible();
  await expect(bar.getByText(/\d+d\b|days/), "the bar holds the stage, never its age").toHaveCount(0);
  const due = msg("applications-posting-due-day", { offset: 1, date: "" });
  await expect(bar.getByRole("link", { name: VIEW_APPLY })).toHaveCount(0);
  const view = bar.getByRole("link", { name: msg("role-job-detail-view-posting") });
  await expect(view).toHaveAttribute("href", jobFixture.url);
  await expect(view).not.toHaveClass(/ui-btn-primary/);
  const facts = panel.locator("dl.jd-pipeline-facts");
  const value = (term: string) => facts.locator("dt", { hasText: new RegExp(`^${term}$`) }).locator("xpath=following-sibling::dd[1]");
  // The stage is read here, in the row's own ink, and changed in the bar.
  const stage = value(msg("applications-posting-stage"));
  await expect(stage).toHaveText(msg("taxonomy-stage-applied"));
  await expect(facts.getByRole("link")).toHaveCount(0);
  const twelveDays = msg("applications-fact-days-value", { days: 12 });
  await expect(value(msg("applications-fact-days"))).toContainText(twelveDays);
  // The step and the day it is due are two rows of plain words: no pill.
  await expect(value(msg("applications-posting-next-step"))).toHaveText("Email the recruiter");
  await expect(value(msg("applications-posting-due"))).toHaveText(due);
  await expect(facts.locator(".ui-badge")).toHaveCount(0);
  const ink = (row: Locator) => row.evaluate((el) => getComputedStyle(el).color);
  const plain = await ink(value(msg("applications-fact-days")));
  expect(await ink(stage), "the stage is not coloured").toBe(plain);
  expect(await ink(value(msg("applications-posting-due"))), "a date still to come is not coloured").toBe(plain);
  // The bar holds controls only: the date is read once, in the section.
  await expect(bar.getByText(due)).toHaveCount(0);

  // Every row is one line high, the one with the history's clock included:
  // a control taller than the text must not push its row apart from the rest.
  const heights = await facts.locator("dd").evaluateAll((rows) => rows.map((row) => Math.round(row.getBoundingClientRect().height)));
  expect(heights.length).toBe(4);
  expect(new Set(heights).size, `row heights ${heights.join(", ")}`).toBe(1);

  // The way to the application stands on the section's heading line, at its
  // far end, and nowhere in the rows.
  const open = panel.locator(".jd-aside").getByRole("link", { name: msg("applications-posting-open") });
  await expect(open).toHaveAttribute("href", "/pipeline/101");
  const heading = (await panel.locator(".jd-aside .section-title", { hasText: msg("applications-posting-row") }).boundingBox())!;
  const link = (await open.boundingBox())!;
  const column = (await panel.locator(".jd-aside").boundingBox())!;
  expect(link.y, "on the heading's line").toBeLessThan(heading.y + heading.height);
  expect(link.y + link.height, "on the heading's line").toBeGreaterThan(heading.y);
  expect(link.x, "after the heading").toBeGreaterThanOrEqual(heading.x + heading.width);
  expect(Math.abs(link.x + link.width - (column.x + column.width)), "at the line's far end").toBeLessThanOrEqual(1);
  expect((await facts.locator("dt").first().boundingBox())!.y, "above the rows").toBeGreaterThan(link.y + link.height - 1);

  // The clock stands right after the days it explains, and says which history it opens.
  const clock = facts.getByRole("button", { name: msg("applications-posting-history-title") });
  await expect(clock).toHaveText("");
  const days = (await facts.getByText(twelveDays).boundingBox())!;
  const mark = (await clock.boundingBox())!;
  expect(mark.x, "after the figure").toBeGreaterThanOrEqual(days.x + days.width);
  expect(mark.x - (days.x + days.width), "and beside it").toBeLessThanOrEqual(12);
  await clock.click();
  const history = page.getByRole("dialog", { name: msg("applications-posting-history-title") });
  await expect(history.getByRole("listitem").last()).toHaveText(
    `${msg("applications-posting-history-today")}${msg("applications-posting-history-now", { stage: "Applied", days: 12 })}`,
  );
  await expectOnTop(history.getByText(msg("applications-posting-history-title")), "the application history");
});

/* The side column is the person's own facts first, then the posting's: where
   the application stands, the Details, then similar roles. The radar's guess
   at a posting's world is not shown: stored with the posting, it reaches no
   one until it has something to say. */
test("the side column reads Pipeline, Details, then More like this, and shows no guess at the role's world", async ({ page }) => {
  let relevance = "relevant";
  await mockGet(page, "/api/jobs/101", (route) => route.fulfill({ json: {
    ...jobFixture, is_favorite: true, pursuit: appliedPursuit,
    relevance_review: {
      domain: relevance === "uncertain" ? null : "payments_fintech", relevance, confidence: 0.63,
      rationale: "Nearest world anchor: 'Payments & Fintech' (cosine 0.30, margin 0.020 over 'Customer Support & Service').",
      tracked_worlds: ["ai_ml"], prompt_version: "relevance_review/emb-v1",
      provider: "builtin", model_id: "lightonai/DenseOn", reviewed_at: "2026-08-07T12:00:00Z",
    },
  } }));
  await mockGet(page, "/api/applications/101", (route) => route.fulfill({ json: applicationDetailFixture({
    application: applicationCardFixture({ pursuit_id: 10, stage: "applied", stage_since: new Date(Date.now() - 3 * DAY).toISOString() }),
  }) }));
  await mockGet(page, "/api/jobs/101/similar**", (route) => route.fulfill({ json: {
    scope: new URL(route.request().url()).searchParams.get("scope"),
    items: [{ ...jobFixture, id: 900, title: "A similar role", score: 0.9 }],
  } }));
  await page.goto("/company/openai/job/101");
  const column = detail(page).locator(".jd-aside");
  for (relevance of ["relevant", "irrelevant", "uncertain"]) {
    await page.reload();
    await expect(column.locator(".similar-row").first()).toBeVisible();
    expect(await column.locator(".section-title").allTextContents(), `a ${relevance} review`).toEqual([
      msg("applications-posting-row"), msg("role-job-detail-details"), msg("role-job-detail-more-like-this"),
    ]);
    for (const internal of [/Payments/, /cosine/i, /margin/i, /anchor/i, /DenseOn/, /builtin/]) {
      await expect(column, `a ${relevance} review`).not.toContainText(internal);
    }
  }
});

/* Sections are told apart before their rows are read: a hairline opens each
   one after the first, with more room above it than between two rows, and the
   first stands flush with the top of the column. */
test("each side-column section after the first opens with a hairline and room above it", async ({ page }) => {
  await mockGet(page, "/api/jobs/101", (route) => route.fulfill({ json: { ...jobFixture, is_favorite: true, pursuit: appliedPursuit } }));
  await mockGet(page, "/api/applications/101", (route) => route.fulfill({ json: applicationDetailFixture({
    application: applicationCardFixture({ pursuit_id: 10, stage: "applied", stage_since: new Date(Date.now() - 3 * DAY).toISOString() }),
  }) }));
  await page.goto("/company/openai/job/101");
  const column = detail(page).locator(".jd-aside");
  await expect(column.locator("dl.jd-pipeline-facts")).toBeVisible();
  const heads = await column.locator(".section-title").evaluateAll((titles) => titles.map((title) => {
    const style = getComputedStyle(title);
    return { rule: parseFloat(style.borderTopWidth), above: parseFloat(style.marginTop) + parseFloat(style.paddingTop) };
  }));
  const rowGap = await column.locator("dl.kv").first().evaluate((list) => parseFloat(getComputedStyle(list).rowGap));
  expect(heads.length).toBeGreaterThanOrEqual(2);
  expect(heads[0], "the first section starts the column").toEqual({ rule: 0, above: 0 });
  for (const head of heads.slice(1)) {
    expect(head.rule).toBeGreaterThan(0);
    expect(head.above, "more room than between two rows").toBeGreaterThan(rowGap * 2);
  }
});

test("the stage button's star is the radar's saved gold, at a live stage and after an ending", async ({ page }) => {
  let ended = false;
  await mockGet(page, "/api/jobs/101", (route) => route.fulfill({ json: { ...jobFixture, is_favorite: true, pursuit: appliedPursuit } }));
  await mockGet(page, "/api/applications/101", (route) => route.fulfill({ json: applicationDetailFixture({
    application: applicationCardFixture(ended
      ? { pursuit_id: 10, stage: "rejected", ended_at_stage: "applied", stage_since: new Date().toISOString() }
      : { pursuit_id: 10, stage: "applied", stage_since: new Date(Date.now() - 12 * DAY).toISOString() }),
  }) }));
  await page.goto("/company/openai/job/101");
  const stage = detail(page).locator(".cover-bar .jd-stage");
  await expect(stage).toContainText("Applied");
  // The colour the radar paints a saved star, resolved in this theme.
  const gold = await page.evaluate(() => {
    const probe = document.createElement("span");
    probe.style.color = "var(--app-chosen-text)";
    document.body.append(probe);
    const colour = getComputedStyle(probe).color;
    probe.remove();
    return colour;
  });
  const colours = () => stage.evaluate((button) => ({
    star: getComputedStyle(button.querySelector("svg")!).color,
    words: getComputedStyle(button).color,
  }));

  const live = await colours();
  expect(live.star).toBe(gold);
  expect(live.words, "only the star is gold; the stage's words keep the bar's ink").not.toBe(gold);

  ended = true;
  await page.reload();
  await expect(stage).toHaveAttribute("data-ended", "");
  // The button's colour eases to the ending's, so its words are read once settled.
  await expect.poll(async () => (await colours()).words, "an ending quiets the words").not.toBe(live.words);
  expect((await colours()).star, "never the star").toBe(gold);
});

/* The side column stays in view while the description scrolls: where the
   person stands with the role, and the role's facts, are read beside any part
   of a long posting. The page has one scroll, and the column none of its own:
   it keeps its first rows under the bar, and the last rows of a column taller
   than the window come into view at the page's end. In one column it follows
   the description. */
const longPosting = {
  ...appleJobFixture,
  comp_package: compPackageFixture(),
  is_favorite: true,
  pursuit: { ...appliedPursuit, job_id: 303 },
  description_sections: [
    ...appleJobFixture.description_sections,
    { key: "responsibilities", title: "Responsibilities", content: Array.from({ length: 30 }, (_, i) =>
      `Paragraph ${i + 1}. You will set the direction for a platform that many teams build on, and explain what it leaves out to the people who depend on it.`).join("\n\n") },
  ],
};
async function openLongPosting(page: Page, size: { width: number; height: number }) {
  await page.setViewportSize(size);
  await mockGet(page, "/api/jobs/303", (route) => route.fulfill({ json: longPosting }));
  await mockGet(page, "/api/applications/303", (route) => route.fulfill({ json: applicationDetailFixture({
    application: applicationCardFixture({ job_id: 303, pursuit_id: 10, stage: "applied", company: "apple", stage_since: new Date(Date.now() - 3 * DAY).toISOString() }),
  }) }));
  await mockGet(page, "/api/jobs/303/similar**", (route) => route.fulfill({ json: {
    scope: "cross", items: [1, 2, 3].map((n) => ({ ...jobFixture, id: 900 + n, title: `Principal Product Manager, Platform ${n}`, score: 0.9 })),
  } }));
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/company/apple/job/303");
  const panel = detail(page);
  await expect(panel.getByRole("heading", { name: "Responsibilities" })).toBeVisible();
  await expect(panel.locator(".similar-row")).toHaveCount(6);
  return {
    column: panel.locator(".jd-aside"),
    scroll: panel.locator(".cover-scroll"),
    pipeline: panel.locator(".jd-aside .section-title").first(),
    lastRow: panel.locator(".similar-row").last(),
  };
}
/** How far under the bar the column stops: the page's own top inset. */
const STUCK = 40;
/** Scrolls the posting and waits for what follows its scroll (the pay copy,
 *  the role in the bar): drawn on the scroll event, fired with the next frame.
 *  Under reduced motion a change of style still takes a transition of a
 *  frame, which is finished here. */
const scrollPosting = (scroll: Locator, top: number) => scroll.evaluate(async (box, y) => {
  box.scrollTop = y;
  await new Promise<void>((done) => requestAnimationFrame(() => requestAnimationFrame(() => done())));
  for (const animation of document.getAnimations()) animation.finish();
}, top);

test("the side column stays in view while a long description scrolls", async ({ page }) => {
  const { column, scroll, pipeline, lastRow } = await openLongPosting(page, { width: 1440, height: 1000 });
  const card = (await detail(page).locator(".comp-panel").boundingBox())!;
  const atRest = (await column.boundingBox())!;
  expect(atRest.y, "at the top it stands beside the pay panel").toBeCloseTo(card.y, 0);

  await scrollPosting(scroll, 1500);
  const box = (await scroll.boundingBox())!;
  const stuck = (await column.boundingBox())!;
  expect(stuck.y - box.y, "stopped under the bar").toBeCloseTo(STUCK, 0);
  await expect(pipeline).toBeInViewport({ ratio: 1 });
  // Its More like this rows have folded away while the posting is read.
  await expect(lastRow).toBeHidden();
  await expect(column.locator("dl.kv").first()).toBeInViewport({ ratio: 1 });
  // Fail-first: a column that scrolls with the page is 1500px above the window here.
  await expect(detail(page).getByText("Paragraph 12.")).toBeInViewport();
});

test("a side column taller than the window keeps its first rows in view, and its last rows come at the end of the page", async ({ page }) => {
  const { column, scroll, pipeline, lastRow } = await openLongPosting(page, { width: 1440, height: 560 });
  const atRest = (await column.boundingBox())!;
  const box = (await scroll.boundingBox())!;
  expect(atRest.height, "taller than its room").toBeGreaterThan(box.height - 2 * STUCK);
  // Fail-first: a column with a scroll of its own is clipped to its room.
  expect(await column.evaluate((el) => [getComputedStyle(el).overflowY, el.scrollHeight - el.clientHeight])).toEqual(["visible", 0]);

  await scrollPosting(scroll, 1500);
  // More like this folds while the posting is read; opened again, the column is its full length.
  await column.getByRole("button", { name: msg("role-job-detail-more-like-this") }).click();
  await expect(lastRow).toBeVisible();
  const stuck = (await column.boundingBox())!;
  expect(stuck.y - box.y, "stopped under the bar").toBeCloseTo(STUCK, 0);
  expect(stuck.height, "whole").toBeGreaterThanOrEqual(atRest.height);
  await expect(pipeline).toBeInViewport({ ratio: 1 });
  await expect(lastRow).not.toBeInViewport();
  await expect(detail(page).getByText("Paragraph 12.")).toBeInViewport();

  // The one scroll reaches the column's last row: at the page's end the column leaves with the text.
  await scrollPosting(scroll, 100000);
  await expect(lastRow).toBeInViewport({ ratio: 1 });
});

/* A long read has its own ramp: the title a clear step above the section
   headings, the headings a step above the text. Sections are parted by room
   alone: the heading marks the break, and a rule over it would say it twice. */
test("section headings outrank the text by a step, and sections are parted by room, not rules", async ({ page }) => {
  await openLongPosting(page, { width: 1440, height: 1000 });
  const panel = detail(page);
  const size = (one: Locator) => one.evaluate((el) => parseFloat(getComputedStyle(el).fontSize));
  const heading = panel.locator(".jd-section-minimum_qualifications h2");
  const text = panel.locator(".jd-section-summary p").last();
  expect((await size(heading)) / (await size(text)), "a heading a step above the text").toBeGreaterThanOrEqual(1.15);
  expect((await size(panel.locator(".jd-hero h1"))) / (await size(heading)), "the title a step above its headings")
    .toBeGreaterThanOrEqual(1.2);

  const rules = await panel.locator(".jd-section:not(.jd-section-pay_and_benefits)")
    .evaluateAll((all) => all.map((one) => getComputedStyle(one).borderTopWidth));
  expect(rules.length).toBeGreaterThan(2);
  expect([...new Set(rules)], "no rule over any section").toEqual(["0px"]);

  // The room above a heading's words: at least two lines of the text.
  const words = await heading.evaluate((el) => {
    const range = document.createRange();
    range.selectNodeContents(el);
    return range.getBoundingClientRect().top;
  });
  const above = (await text.boundingBox())!;
  const line = await text.evaluate((el) => parseFloat(getComputedStyle(el).lineHeight));
  expect(words - (above.y + above.height)).toBeGreaterThanOrEqual(2 * line);
});

/* While a section is read its heading stays at the top of the reading column,
   and the bar carries the role once the posting's own heading has left, at
   the heading's left edge. */
test("a section's heading stays at the top of the column, and the role rises into the bar", async ({ page }) => {
  const { scroll } = await openLongPosting(page, { width: 1440, height: 1000 });
  const panel = detail(page);
  const role = panel.locator(".jd-bar-role");
  const heading = panel.getByRole("heading", { name: "Responsibilities" });
  await expect(role).not.toHaveAttribute("data-shown", "");
  await expect.poll(() => role.evaluate((el) => getComputedStyle(el).opacity)).toBe("0");
  await expect(role, "a copy for the eye: the heading is the one read out").toHaveAttribute("aria-hidden", "true");

  await scrollPosting(scroll, 1500);
  const box = (await scroll.boundingBox())!;
  expect((await heading.boundingBox())!.y, "stuck at the top of the scroll box").toBeCloseTo(box.y, 0);
  await expect(panel.getByText("Paragraph 12.")).toBeInViewport();
  // Stuck, it stands on the canvas, solid: nothing passing beneath shows
  // through it, blurred or not.
  await expect(heading).toHaveAttribute("data-stuck", "");
  const ground = await heading.evaluate((el) => {
    const style = getComputedStyle(el);
    const probe = document.createElement("i");
    probe.style.color = "var(--app-canvas)";
    el.append(probe);
    const canvas = getComputedStyle(probe).color;
    probe.remove();
    return {
      colour: style.backgroundColor,
      canvas,
      blur: style.backdropFilter || style.getPropertyValue("-webkit-backdrop-filter") || "none",
      edge: style.boxShadow,
      layers: el.querySelectorAll("[aria-hidden]").length,
    };
  });
  expect(ground.colour, "the canvas itself, solid").toBe(ground.canvas);
  expect(ground.colour).not.toBe("rgba(0, 0, 0, 0)");
  expect(ground.blur, "no blur of what passes beneath").toBe("none");
  // A line passing under it goes under an edge: a hairline at its foot.
  expect(ground.edge, "a hairline at its foot").toContain(" 0px 1px 0px");
  expect(ground.layers, "no layer drawn behind the words").toBe(0);
  await expect(role).toHaveAttribute("data-shown", "");
  await expect(role.locator(".jd-bar-title")).toHaveText(longPosting.title);
  const title = (await panel.locator(".jd-hero h1").boundingBox())!;
  expect((await role.locator(".jd-bar-title").boundingBox())!.x, "at the heading's left edge").toBeCloseTo(title.x, 0);

  await scrollPosting(scroll, 0);
  await expect(role).not.toHaveAttribute("data-shown", "");
  // In its place a heading draws no ground: nothing lies over its section's first line.
  await expect(heading).not.toHaveAttribute("data-stuck", "");
  expect(await heading.evaluate((el) => {
    const style = getComputedStyle(el);
    return [style.backgroundColor, style.boxShadow];
  })).toEqual(["rgba(0, 0, 0, 0)", "none"]);
});

/* The pay panel leads the page. As its last part leaves, its small copy grows
   at the top of the side column, with the scroll and back with it; it says
   what the panel says. */
test("the pay panel's small copy grows above Pipeline as the panel leaves, and goes when it returns", async ({ page }) => {
  const { column, scroll, pipeline } = await openLongPosting(page, { width: 1440, height: 1000 });
  const panel = detail(page);
  const dock = column.locator(".jd-dock");
  const height = async () => (await dock.boundingBox())!.height;
  expect(await height(), "nothing at the top of the page").toBe(0);
  await expect(dock).toHaveAttribute("aria-hidden", "true");
  const gap = async () => (await pipeline.boundingBox())!.y - (await column.boundingBox())!.y;
  const before = await gap();

  const leaves = await scroll.evaluate((el) => {
    const card = el.querySelector(".pkg-panel")!.getBoundingClientRect();
    return card.bottom - el.getBoundingClientRect().top;
  });
  // Under reduced motion (how the posting was opened) the copy does not grow: it is absent, then whole.
  await scrollPosting(scroll, leaves - 85);
  expect(await height(), "reduced motion: nothing part way").toBe(0);
  await scrollPosting(scroll, leaves + 200);
  const full = await height();
  expect(full).toBeGreaterThan(40);
  expect(await gap(), "Pipeline moved down by the copy").toBeCloseTo(before + full, 0);
  await expect(dock.locator(".pkg-mini .big")).toHaveText(await panel.locator(".pkg-panel .big").innerText());
  await expect(dock.locator(".pkg-mini-eyebrow")).toHaveText(await panel.locator(".pkg-panel .pkg-eyebrow").innerText());
  expect((await dock.boundingBox())!.y - (await scroll.boundingBox())!.y, "in view, under the bar").toBeCloseTo(STUCK, 0);

  await scrollPosting(scroll, 0);
  expect(await height()).toBe(0);
  expect(await gap()).toBeCloseTo(before, 0);
  // With motion allowed it follows the scroll: part way while the panel's last part leaves.
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.reload();
  await expect(panel.getByRole("heading", { name: "Responsibilities" })).toBeVisible();
  await scrollPosting(scroll, leaves - 85);
  const half = await height();
  expect(half, "part way").toBeGreaterThan(0);
  expect(half).toBeLessThan(full);
  await scrollPosting(scroll, leaves + 200);
  expect(await height()).toBeCloseTo(full, 0);
});

/* A posting with no pay figure says so where the panel stands, and that
   stays there: nothing docks, because there is nothing to keep in view. */
test("a posting with no pay figure docks nothing above Pipeline", async ({ page }) => {
  await mockGet(page, "/api/jobs/303", (route) => route.fulfill({ json: { ...longPosting, comp_package: compPackageFixture({ estimate: null }) } }));
  await mockGet(page, "/api/applications/303", (route) => route.fulfill({ json: applicationDetailFixture({
    application: applicationCardFixture({ job_id: 303, pursuit_id: 10, stage: "applied", company: "apple" }),
  }) }));
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/company/apple/job/303");
  const panel = detail(page);
  await expect(panel.getByRole("heading", { name: "Responsibilities" })).toBeVisible();
  const unknown = panel.getByTestId("pkg-unknown");
  await expect(unknown.locator(".pkg-eyebrow")).toHaveText(msg("role-job-comp-panel-estimated-total-comp"));
  await expect(unknown.locator(".big, .pkg-bar"), "no figure, no stand-in for one, no bar").toHaveCount(0);
  const scroll = panel.locator(".cover-scroll");
  const column = panel.locator(".jd-aside");
  await scrollPosting(scroll, 1500);
  expect((await column.locator(".jd-dock").boundingBox())!.height).toBe(0);
  await expect(column.locator(".pkg-mini")).toHaveCount(0);
  await expect(column.locator(".section-title").first(), "Pipeline leads the column").toHaveText(msg("applications-posting-row"));
  expect((await column.boundingBox())!.y - (await scroll.boundingBox())!.y, "under the bar").toBeCloseTo(STUCK, 0);
});

/* Stuck, a section's heading stands level with the first line of the side
   column: the two columns open on one line. */
test("a stuck section heading is level with the side column's first line", async ({ page }) => {
  const { column, scroll } = await openLongPosting(page, { width: 1440, height: 1000 });
  await scrollPosting(scroll, 1500);
  const middle = (locator: Locator) => locator.evaluate((el) => {
    // The words only, not the heading's padded box.
    const range = document.createRange();
    range.selectNodeContents(el);
    const box = range.getBoundingClientRect();
    return (box.top + box.bottom) / 2;
  });
  const heading = await middle(detail(page).getByRole("heading", { name: "Responsibilities" }));
  const kicker = await middle(column.locator(".pkg-mini-eyebrow"));
  expect(Math.abs(heading - kicker), "the heading's words and the column's first kicker").toBeLessThanOrEqual(1.5);
});

/* Opened from a list, a posting knows its place there: the bar steps to the
   rows on either side, J and K do the same, and Back still returns to the
   list. Opened by its link it has no list, and no pager. */
test("a posting opened from the board steps to the next row and back, and Back returns to the board", async ({ page }) => {
  await mockGet(page, "/api/jobs?**", (route) => route.fulfill({ json: twoJobList }));
  await page.goto("/");
  await page.getByText(jobFixture.title).click();
  const panel = detail(page);
  const pager = panel.getByRole("group", { name: msg("role-job-detail-pager") });
  const previous = pager.getByRole("button", { name: msg("role-job-detail-pager-previous") });
  const next = pager.getByRole("button", { name: msg("role-job-detail-pager-next") });
  await expect(pager).toContainText(msg("role-job-detail-pager-place", { place: 1, count: 2 }));
  await expect(previous, "nothing before the first row").toHaveAttribute("aria-disabled", "true");

  await next.click();
  await expect(page).toHaveURL(/\/company\/[^/]+\/job\/202$/);
  await expect(panel.getByRole("heading", { level: 1, name: jobFixture2.title })).toBeVisible(FIRST_TURN);
  await expect(pager).toContainText(msg("role-job-detail-pager-place", { place: 2, count: 2 }));
  await expect(next, "nothing after the last row").toHaveAttribute("aria-disabled", "true");

  await page.keyboard.press("k");
  await expect(page).toHaveURL(/\/job\/101$/);
  await expect(pager).toContainText(msg("role-job-detail-pager-place", { place: 1, count: 2 }));
  await page.keyboard.press("j");
  await expect(page).toHaveURL(/\/job\/202$/);

  // Each step replaced the entry: one Back is the board, with the cover gone.
  await panel.getByRole("button", { name: msg("role-job-detail-back-2") }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(panel).toHaveCount(0);
});

/* The read ends on the way on: under the employer's text, the next posting in
   the list, named, which opens it as J does. The last row of the list has
   nothing after it, and a posting opened by its link has no list. */
test("a posting opened from the board ends on the next one, which it opens; the last row and a link end on nothing", async ({ page }) => {
  await mockGet(page, "/api/jobs?**", (route) => route.fulfill({ json: twoJobList }));
  await page.goto("/");
  await page.getByText(jobFixture.title).click();
  const panel = detail(page);
  const end = panel.locator(".jd-end");
  const onward = end.getByRole("button");
  await expect(onward).toContainText(msg("role-job-detail-next-posting"));
  await expect(onward).toContainText(jobFixture2.title);
  await expect(onward).toContainText(msg("role-job-detail-pager-place", { place: 2, count: 2 }));
  await expect(onward).toHaveAttribute("aria-keyshortcuts", "J");
  const text = (await panel.locator(".jd-main > .jd-sections, .jd-main > .jd, .jd-main > .jd-empty").last().boundingBox())!;
  expect((await end.boundingBox())!.y, "after the employer's text").toBeGreaterThan(text.y + text.height);

  await onward.click();
  await expect(page).toHaveURL(/\/company\/[^/]+\/job\/202$/);
  await expect(panel.getByRole("heading", { level: 1, name: jobFixture2.title })).toBeVisible(FIRST_TURN);
  await expect(panel.locator(".jd-end"), "the list's last row").toHaveCount(0);

  await page.goto(`/job/${jobFixture.id}`);
  await expect(panel.locator(".jd-hero h1")).toHaveText(jobFixture.title);
  await expect(panel.locator(".jd-end"), "no list, no next").toHaveCount(0);
});

/* Stepping to another posting turns the posting inside a cover that stays
   open. While the next one loads the one on show stays, for the eye only;
   the screen is never emptied to a loading line, the bar keeps its controls,
   and the new posting opens at its top. */
test("the next posting turns in place: one cover, no loading line, the old posting stays until the new one is ready", async ({ page }) => {
  await mockGet(page, "/api/jobs?**", (route) => route.fulfill({ json: twoJobList }));
  let release = () => {};
  const held = new Promise<void>((resolve) => { release = resolve; });
  await mockGet(page, "/api/jobs/202", async (route) => {
    await held;
    await route.fulfill({ json: { ...jobFixture2, description_text: "Second posting.\n\n".repeat(80) } });
  });
  await mockGet(page, "/api/jobs/101", (route) =>
    route.fulfill({ json: { ...jobFixture, description_text: "First posting.\n\n".repeat(80) } }));
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await page.getByText(jobFixture.title).click();
  const panel = detail(page);
  const title = panel.locator(".jd-hero h1");
  await expect(title).toHaveText(jobFixture.title);

  const cover = panel.locator(".cover");
  const scroll = panel.locator(".cover-scroll");
  await cover.evaluate((el: HTMLElement) => { el.dataset.opened = "once"; });
  await page.evaluate(() => {
    const seen = window as unknown as { loadingLines: number };
    seen.loadingLines = 0;
    new MutationObserver(() => {
      if (document.querySelector(".cover .loading")) seen.loadingLines += 1;
    }).observe(document.body, { childList: true, subtree: true });
  });
  await scroll.evaluate((el) => { el.scrollTop = 500; });
  const apply = panel.getByRole("link", { name: VIEW_APPLY });
  await expect(apply).toHaveAttribute("href", jobFixture.url);

  const pager = panel.getByRole("group", { name: msg("role-job-detail-pager") });
  const waiting = panel.locator(".jd-waiting");
  await expect(waiting, "nothing is on its way").toHaveCount(0);
  await pager.getByRole("button", { name: msg("role-job-detail-pager-next") }).click();
  // The step is acknowledged at once, in the bar; the posting waits for its data.
  await expect(pager).toContainText(msg("role-job-detail-pager-place", { place: 2, count: 2 }));
  await expect(title, "the posting on show stays").toHaveText(jobFixture.title);
  await expect(panel.locator(".jd-container"), "for the eye only").toHaveAttribute("inert", "");
  await expect(panel.locator(".jd-bar-actions"), "its controls take no input").toHaveAttribute("inert", "");
  expect(await scroll.evaluate((el) => el.scrollTop), "and stays where it was read to").toBe(500);
  // A wait past a quick load's moment shows a line along the bar's foot.
  expect(await waiting.evaluate((el) => getComputedStyle(el).animationDelay), "never for a quick load").toBe("0.2s");
  await expect.poll(() => waiting.evaluate((el) => getComputedStyle(el).opacity)).toBe("1");
  const bar = (await panel.locator(".cover-bar").boundingBox())!;
  const line = (await waiting.boundingBox())!;
  expect(line.width, "the bar's width").toBeCloseTo(bar.width, 0);
  expect(line.y + line.height, "at its foot").toBeCloseTo(bar.y + bar.height, 0);

  release();
  await expect(title).toHaveText(jobFixture2.title, FIRST_TURN);
  await expect(waiting, "gone once the posting has come").toHaveCount(0);
  await expect(panel.locator(".jd-container")).not.toHaveAttribute("inert", "");
  await expect(panel.getByRole("link", { name: VIEW_APPLY })).toHaveAttribute("href", jobFixture2.url);
  await expect.poll(() => scroll.evaluate((el) => el.scrollTop), { message: "the new posting opens at its top" }).toBe(0);
  await expect(cover, "the same cover, never opened again").toHaveAttribute("data-opened", "once");
  expect(await page.evaluate(() => (window as unknown as { loadingLines: number }).loadingLines)).toBe(0);
  // The turn leaves nothing behind it: a name left on the reading area would cancel the next one.
  await expect(page.locator("html")).not.toHaveAttribute("data-posting-turn");
  await expect.poll(() => scroll.evaluate((el: HTMLElement) => el.style.getPropertyValue("view-transition-name"))).toBe("");
});

/* The turn itself, where the browser has view transitions: the reading area
   alone is drawn apart, the new posting comes in the way the list runs, and
   under reduced motion the posting changes with no motion at all. */
test("a step along the list turns the reading area that way; reduced motion turns nothing", async ({ page, browserName }) => {
  test.skip(browserName !== "chromium", "the Docker WebKit is slow over its first turn, and the app gives it no second");
  await mockGet(page, "/api/jobs?**", (route) => route.fulfill({ json: twoJobList }));
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await page.getByText(jobFixture.title).click();
  const panel = detail(page);
  const title = panel.locator(".jd-hero h1");
  await expect(title).toHaveText(jobFixture.title);

  // Long enough to be read while it runs.
  await page.addStyleTag({ content: "::view-transition-new(posting) { animation-duration: 20s !important; }" });
  const turning = () => page.evaluate(() => {
    const running = document.getAnimations().filter((one) => {
      const effect = one.effect as KeyframeEffect | null;
      return effect?.pseudoElement?.startsWith("::view-transition") ?? false;
    });
    const named = (name: string) => running.some((one) => (one.effect as KeyframeEffect).pseudoElement === name);
    return {
      way: document.documentElement.dataset.postingTurn ?? null,
      readingArea: named("::view-transition-new(posting)"),
      names: [...document.querySelectorAll<HTMLElement>("*")].filter((el) => el.style.getPropertyValue("view-transition-name")).map((el) => el.className),
    };
  });
  const finish = () => page.evaluate(() => document.getAnimations().forEach((one) => one.finish()));

  const pager = panel.getByRole("group", { name: msg("role-job-detail-pager") });
  await pager.getByRole("button", { name: msg("role-job-detail-pager-next") }).click();
  await expect.poll(turning).toEqual({ way: "next", readingArea: true, names: ["cover-scroll"] });
  await expect(title, "the new posting is what comes in").toHaveText(jobFixture2.title);
  await finish();
  await expect.poll(turning).toEqual({ way: null, readingArea: false, names: [] });

  await page.keyboard.press("k");
  await expect.poll(turning).toEqual({ way: "previous", readingArea: true, names: ["cover-scroll"] });
  await finish();
  await expect(title).toHaveText(jobFixture.title);
  await expect.poll(turning).toEqual({ way: null, readingArea: false, names: [] });

  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.keyboard.press("j");
  await expect(title).toHaveText(jobFixture2.title);
  expect(await turning(), "no turn was started").toEqual({ way: null, readingArea: false, names: [] });
});

/* A posting that is the page itself (reached by its link) has nothing under
   it: a link on it turns the page to the next posting in the same cover, and
   Back, by the bar or the browser, returns to the first where it was left. */
test("from a posting reached by its link, a similar role takes its place in the same cover, and Back returns to it", async ({ page }) => {
  await mockGet(page, "/api/jobs/101", (route) =>
    route.fulfill({ json: { ...jobFixture, description_text: "First posting.\n\n".repeat(80) } }));
  await mockGet(page, "/api/jobs/101/similar**", (route) => route.fulfill({ json: {
    scope: new URL(route.request().url()).searchParams.get("scope"),
    items: [{ ...jobFixture2, score: 0.9 }],
  } }));
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/company/openai/job/101");
  const panel = detail(page);
  const title = panel.locator(".jd-hero h1");
  await expect(title).toHaveText(jobFixture.title);
  const cover = page.locator(".cover");
  const scroll = page.locator(".cover-scroll");
  await cover.evaluate((el: HTMLElement) => { el.dataset.opened = "once"; });
  await scroll.evaluate((el) => { el.scrollTop = 400; });

  // Clicked where it stands: a pointer would first scroll the row into view,
  // and move the place the first posting is left at.
  await panel.locator(".similar-row").first().dispatchEvent("click");
  await expect(page).toHaveURL(/\/company\/[^/]+\/job\/202$/);
  await expect(title).toHaveText(jobFixture2.title, FIRST_TURN);
  // Still the page, in the cover it opened in: nothing was stacked on it.
  await expect(page.getByRole("main", { name: /^Role:/ })).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.locator(".cover")).toHaveCount(1);
  await expect(cover).toHaveAttribute("data-opened", "once");
  await expect.poll(() => scroll.evaluate((el) => el.scrollTop), { message: "the new posting opens at its top" }).toBe(0);

  // The bar's Back is the first posting, not the board, and where it was left.
  await panel.getByRole("button", { name: msg("role-job-detail-back-2") }).click();
  await expect(page).toHaveURL(/\/company\/[^/]+\/job\/101$/);
  await expect(title).toHaveText(jobFixture.title, FIRST_TURN);
  await expect.poll(() => scroll.evaluate((el) => el.scrollTop), { message: "where the first posting was left" }).toBe(400);
  await expect(cover).toHaveAttribute("data-opened", "once");

  // From there Back has no posting behind it: the board.
  await panel.getByRole("button", { name: msg("role-job-detail-back-2") }).click();
  await expect(page).toHaveURL(/\/$/);
});

/* An arrow that cannot act now still takes focus, so the ring the keyboard
   draws around it must stand clear of the count it sits beside and of the
   hairline at the group's end. */
test("the pager's focus ring clears the count and the hairline, on either arrow", async ({ page }) => {
  await mockGet(page, "/api/jobs?**", (route) => route.fulfill({ json: twoJobList }));
  await page.goto("/");
  await page.getByText(jobFixture.title).click();
  const pager = detail(page).getByRole("group", { name: msg("role-job-detail-pager") });
  await expect(pager).toBeVisible();

  const clearance = (side: "first" | "last") => pager.evaluate((group: HTMLElement, which) => {
    const arrows = [...group.querySelectorAll<HTMLElement>(".ui-btn")];
    const arrow = which === "first" ? arrows[0] : arrows[arrows.length - 1];
    arrow.focus();
    const style = getComputedStyle(arrow);
    const ring = parseFloat(style.outlineWidth) + parseFloat(style.outlineOffset);
    const drawn = arrow.getBoundingClientRect();
    const count = group.querySelector(".jd-pager-place")!.getBoundingClientRect();
    const whole = group.getBoundingClientRect();
    return {
      ring,
      // The ring's near edge to the count, and the group's own end to the ring.
      toCount: Math.round(which === "first" ? count.left - (drawn.right + ring) : (drawn.left - ring) - count.right),
      toRule: Math.round(whole.right - (drawn.right + ring)),
    };
  }, side);

  for (const side of ["first", "last"] as const) {
    const seen = await clearance(side);
    expect(seen.ring, `${side} arrow draws a ring`).toBeGreaterThan(0);
    expect(seen.toCount, `${side} arrow's ring clears the count`).toBeGreaterThan(0);
    expect(seen.toRule, `${side} arrow's ring clears the hairline`).toBeGreaterThan(0);
  }
});

test("a posting opened by its link has no pager", async ({ page }) => {
  await page.goto("/company/openai/job/101");
  await expect(detail(page).getByRole("heading", { level: 1 })).toBeVisible();
  await expect(detail(page).getByRole("group", { name: msg("role-job-detail-pager") })).toHaveCount(0);
});

/* More like this folds to its heading, for a column of the role's own facts.
   The choice is this browser's, and holds for the next posting opened. */
test("More like this folds to its heading, and the next posting opens folded", async ({ page }) => {
  const { column } = await openLongPosting(page, { width: 1440, height: 1000 });
  const panel = detail(page);
  const fold = column.getByRole("button", { name: msg("role-job-detail-more-like-this") });
  await expect(fold).toHaveAttribute("aria-expanded", "true");
  const open = (await column.boundingBox())!;
  const target = (await fold.boundingBox())!;
  expect(target.width, "the whole heading line").toBeCloseTo(open.width, 0);
  // It paints no box of its own, at rest or under a pointer.
  await fold.hover();
  expect(await fold.evaluate((el) => [getComputedStyle(el).backgroundColor, getComputedStyle(el).borderTopWidth])).toEqual(["rgba(0, 0, 0, 0)", "0px"]);
  // The pointer target reaches past the words' own line, above and below.
  await page.mouse.click(open.x + 4, target.y - 6);
  await expect(fold).toHaveAttribute("aria-expanded", "false");
  await page.mouse.click(open.x + 4, target.y + target.height + 6);
  await expect(fold).toHaveAttribute("aria-expanded", "true");
  const chevron = (await fold.locator("svg").boundingBox())!;
  expect(chevron.x + chevron.width, "the chevron at the line's end").toBeCloseTo(open.x + open.width, 0);
  // The empty stretch between the words and the chevron folds it too.
  await page.mouse.click(open.x + open.width / 2, target.y + target.height / 2);
  await expect(fold).toHaveAttribute("aria-expanded", "false");
  await page.mouse.click(open.x + open.width / 2, target.y + target.height / 2);
  await expect(fold).toHaveAttribute("aria-expanded", "true");

  await fold.focus();
  await page.keyboard.press("Enter");
  await expect(fold).toHaveAttribute("aria-expanded", "false");
  await expect(fold).toBeFocused();
  await expect(panel.locator(".similar-row").first()).toBeHidden();
  await expect(panel.locator(".similar-label").first()).toBeHidden();
  await page.keyboard.press("Tab");
  expect(await page.evaluate(() => !!document.activeElement?.closest(".similar-fold")), "folded rows take no focus").toBe(false);
  await fold.focus();
  await expect(fold).toBeVisible();
  expect((await column.boundingBox())!.height, "shorter by its rows").toBeLessThan(open.height - 100);
  // The rest of the column is as it was.
  await expect(column.locator("dl.kv").first()).toBeVisible();

  await page.reload();
  await expect(panel.getByRole("heading", { name: "Responsibilities" })).toBeVisible();
  const again = panel.locator(".jd-aside").getByRole("button", { name: msg("role-job-detail-more-like-this") });
  await expect(again).toHaveAttribute("aria-expanded", "false");
  await expect(panel.locator(".similar-row").first()).toBeHidden();

  await again.click();
  await expect(again).toHaveAttribute("aria-expanded", "true");
  await expect(panel.locator(".similar-row").first()).toBeVisible();
  await expect(panel.locator(".similar-row")).toHaveCount(6);
});

/* More like this is for choosing where to go next: open at the top of a
   posting, folded while it is read, open again back at the top. Opened while
   reading it stays open, and none of that changes the choice the browser keeps. */
test("More like this folds while the posting is read and opens again at the top", async ({ page }) => {
  const { column, scroll } = await openLongPosting(page, { width: 1440, height: 1000 });
  const fold = column.getByRole("button", { name: msg("role-job-detail-more-like-this") });
  const rows = column.locator(".similar-row");
  const open = (await column.boundingBox())!.height;
  await expect(rows.first()).toBeVisible();

  await scrollPosting(scroll, 1500);
  await expect(fold).toHaveAttribute("aria-expanded", "false");
  await expect(rows.first()).toBeHidden();
  await expect(fold).toBeVisible();
  await expect.poll(async () => (await column.boundingBox())!.height, "shorter by its rows").toBeLessThan(open - 100);
  // The text did not move when the column changed.
  expect(await scroll.evaluate((el) => el.scrollTop)).toBe(1500);

  // Opened while reading, it stays open down the page.
  await fold.click();
  await expect(rows.first()).toBeVisible();
  await scrollPosting(scroll, 2200);
  await expect(fold).toHaveAttribute("aria-expanded", "true");
  await fold.click();
  await expect(rows.first()).toBeHidden();

  await scrollPosting(scroll, 0);
  await expect(fold).toHaveAttribute("aria-expanded", "true");
  await expect(rows.first()).toBeVisible();
  // Folding by the scroll is not the person's choice: the next visit opens it.
  expect(await page.evaluate(() => localStorage.getItem("roleband.posting-similar-folded"))).toBeNull();
});

test("in one column the side column follows the description and scrolls with the page", async ({ page }) => {
  const { column, scroll } = await openLongPosting(page, { width: 800, height: 900 });
  const text = (await detail(page).locator(".jd-sections").boundingBox())!;
  const below = (await column.boundingBox())!;
  expect(below.y, "under the description").toBeGreaterThanOrEqual(text.y + text.height);
  expect(await column.evaluate((el) => getComputedStyle(el).position)).toBe("static");
  await scroll.evaluate((el) => { el.scrollTop = 600; });
  expect((await column.boundingBox())!.y, "moves with the page").toBeCloseTo(below.y - 600, 0);
});

/* The form states its own size (15% larger than the screen, plain on a phone):
   opened from a posting, it is the size it is in the pipeline. */
for (const [name, size, zoom] of [["a laptop", { width: 1440, height: 900 }, 1.15], ["a phone", { width: 375, height: 812 }, 1]] as const) {
  test(`the interview form opened from a posting is the pipeline's size on ${name}`, async ({ page }) => {
    await page.setViewportSize(size);
    await mockGet(page, "/api/jobs/101", (route) => route.fulfill({ json: { ...jobFixture, is_favorite: true, pursuit: appliedPursuit } }));
    await mockGet(page, "/api/applications/101", (route) => route.fulfill({ json: applicationDetailFixture() }));
    await page.goto("/company/openai/job/101");
    await detail(page).getByRole("button", { name: STAGE_APPLIED }).click();
    await page.getByRole("dialog", { name: STAGE_MENU })
      .getByRole("button", { name: new RegExp(msg("taxonomy-stage-interviewing")) }).click();
    const form = page.getByRole("dialog", { name: msg("applications-interview-title") });
    await expect(form).toBeVisible();
    await expect.poll(() => form.evaluate((el) => el.getAnimations().every((one) => one.playState === "finished"))).toBe(true);
    const drawn = await form.evaluate((el: HTMLElement) => el.getBoundingClientRect().width / el.offsetWidth);
    expect(drawn).toBeCloseTo(zoom, 2);
  });
}

test("moving to Interviewing from the posting asks for the interview first, over the cover", async ({ page }) => {
  const writes: unknown[] = [];
  await mockApi(page, "PUT", "/api/jobs/101/pursuit", (route) => {
    writes.push(route.request().postDataJSON());
    return route.fulfill({ json: { pursuit: { ...appliedPursuit, stage: "interviewing" } } });
  });
  await mockGet(page, "/api/jobs/101", (route) => route.fulfill({ json: { ...jobFixture, is_favorite: true, pursuit: appliedPursuit } }));
  await mockGet(page, "/api/applications/101", (route) => route.fulfill({ json: applicationDetailFixture() }));
  await page.goto("/company/openai/job/101");
  const panel = detail(page);

  await panel.getByRole("button", { name: STAGE_APPLIED }).click();
  await page.getByRole("dialog", { name: STAGE_MENU }).getByRole("button", { name: new RegExp(msg("taxonomy-stage-interviewing")) }).click();
  const form = page.getByRole("dialog", { name: msg("applications-interview-title") });
  await expect(form).toBeVisible();
  await expectOnTop(form.getByRole("heading", { name: msg("applications-interview-title") }), "the interview form");
  expect(writes, "no move before the interview's date").toEqual([]);
  await form.getByRole("button", { name: msg("applications-interview-cancel") }).click();
  await expect(form).toHaveCount(0);
  await expect(panel.getByRole("button", { name: STAGE_APPLIED })).toBeVisible();
  expect(writes).toEqual([]);
});

/* A Details row is shown when the posting states the fact. A posting that
   names no team, or only its employer's own name, and does not say where the
   work happens has neither row: an empty row reads as a missing fact. */
test("Details shows the team and the workplace only when the posting states them", async ({ page }) => {
  let stated: Record<string, unknown> = {};
  await mockGet(page, "/api/jobs/101", (route) => route.fulfill({ json: { ...jobFixture, ...stated } }));
  const terms = () => detail(page).locator(".jd-aside dl.kv dt").allTextContents();
  const [team, workplace, listed, status] = [
    msg("role-job-detail-team"), msg("role-job-detail-workplace"), msg("role-listing-age-listed-for"), msg("role-job-detail-status"),
  ];

  await page.goto("/company/openai/job/101");
  const details = detail(page).locator(".jd-aside dl.kv");
  await expect(details.getByText("API", { exact: true })).toBeVisible();
  await expect(details.getByText(msg("taxonomy-workplace-hybrid"), { exact: true })).toBeVisible();
  expect(await terms()).toEqual([team, workplace, listed, status]);

  // The employer's own name in the team field, and no workplace stated.
  stated = { team: "OpenAI", department: null, workplace_type: "unknown" };
  await page.reload();
  await expect(details.getByText(listed, { exact: true })).toBeVisible();
  expect(await terms(), "the age and the status are always said").toEqual([listed, status]);
  await expect(details.getByText("—")).toHaveCount(0);

  // A department stands in for a missing team.
  stated = { team: null, department: "Product", workplace_type: "remote" };
  await page.reload();
  await expect(details.getByText("Product", { exact: true })).toBeVisible();
  await expect(details.getByText(msg("taxonomy-workplace-remote"), { exact: true })).toBeVisible();
  expect(await terms()).toEqual([team, workplace, listed, status]);
});

/* What applying asks, read from the posting's own page. Absent until
   read: a form we never read is not a form that asks nothing. */
test("Details says what applying asks once the posting page has been read", async ({ page }) => {
  await page.goto("/company/openai/job/101");
  await expect(detail(page).getByRole("heading", { name: jobFixture.title })).toBeVisible();
  await expect(detail(page).locator("dl.kv").getByText("To apply", { exact: true })).toHaveCount(0);

  await page.route("/api/jobs/101", (route) => route.fulfill({ json: {
    ...jobFixture,
    application_form: { required: 9, written: 1, choices: 8, asks_expected_pay: true, read_at: "2026-09-28T12:00:00Z" },
  } }));
  await page.reload();
  const details = detail(page).locator("dl.kv");
  await expect(details.getByText("To apply", { exact: true })).toBeVisible();
  const asks = [
    msg("role-apply-ask-questions", { count: 9 }),
    msg("role-apply-ask-written-answers", { count: 1 }),
    msg("role-apply-ask-asks-your-expected-pay"),
  ].join(", ");
  await expect(details.getByText(asks, { exact: true })).toBeVisible();
});

/* Opening a posting whose form is unread asks for it once,
   after the page is shown, and the row appears when the answer arrives. A
   posting the server marks unreadable is never asked about. */
test("opening an unread posting reads what applying asks, once", async ({ page }) => {
  const reads: string[] = [];
  const form = { required: 5, written: 1, choices: 2, asks_expected_pay: false, read_at: "2026-09-29T09:00:00Z" };
  let stored = false;
  await page.route("/api/jobs/101/posting-page", (route) => {
    reads.push(route.request().method());
    stored = true;
    return route.fulfill({ json: { outcome: "read", application_form: form } });
  });
  // As the server answers: unread until the read, then the form and no flag.
  // The detail is read again after a read, since the page may state pay:
  // twice in all, counted as answered (dev StrictMode re-issues the first).
  const detailReads = watchReads(page, "GET", "/api/jobs/101");
  await page.route("/api/jobs/101", (route) => route.fulfill({ json: stored
    ? { ...jobFixture, application_form: form, application_form_readable: false }
    : { ...jobFixture, application_form: null, application_form_readable: true } }));
  await page.goto("/company/openai/job/101");
  const details = detail(page).locator("dl.kv");
  await expect(details.getByText("5 questions, 1 written answer", { exact: true })).toBeVisible();
  await expect.poll(() => detailReads.answered).toBe(2);
  expect(reads).toEqual(["POST"]);

  // A posting the server marks unreadable is never asked about. Absence is
  // asserted once the page has gone quiet, not at first paint, when the
  // effect that would ask may not have run yet.
  await page.unroute("/api/jobs/101");
  await page.route("/api/jobs/101", (route) => route.fulfill({ json: {
    ...jobFixture, application_form: null, application_form_readable: false,
  } }));
  await page.reload();
  await expect(detail(page).getByRole("heading", { name: jobFixture.title })).toBeVisible();
  await page.waitForLoadState("networkidle");
  await expect(details.getByText("To apply", { exact: true })).toHaveCount(0);
  expect(reads).toEqual(["POST"]);
});

/* One age in Details, with where it counts from, in place of separate Posted,
   First seen and Listed for; the history opens on demand, is read once, and
   marks the start. */
test("Details says one age with its basis, and the history opens on demand", async ({ page }) => {
  const reads = watchReads(page, "GET", "/api/jobs/101/history");
  const event = { from_at: null, to_at: null, field: null, count: null, job_id: null, req_id: null, title: null, until: null, link: null };
  await page.route("/api/jobs/101", (route) => route.fulfill({ json: {
    ...jobFixture, listed_since: "2026-04-12T00:00:00Z", listed_days: 170, listed_basis: "employer",
  } }));
  await page.route("/api/jobs/101/history", (route) => route.fulfill({ json: {
    headline: { since: "2026-04-12T00:00:00Z", days: 170, basis: "employer" },
    role: null,
    events: [
      { ...event, at: "2026-04-12T00:00:00Z", kind: "employer_published" },
      { ...event, at: "2026-07-23T00:00:00Z", kind: "first_seen" },
      { ...event, at: "2026-09-02T00:00:00Z", kind: "redated", from_at: "2026-04-12T00:00:00Z", to_at: "2026-09-02T00:00:00Z" },
    ],
    unconfirmed: [],
  } }));
  await page.goto("/company/openai/job/101");
  const details = detail(page).locator("dl.kv");
  await expect(details.getByText("170 days", { exact: true })).toBeVisible();
  await expect(details.getByText(/the employer's date|^since /)).toHaveCount(0);
  for (const gone of ["Posted", "First seen"]) await expect(details.getByText(gone, { exact: true })).toHaveCount(0);
  expect(reads.started).toBe(0);

  await details.getByRole("button", { name: msg("role-listing-age-listing-history") }).click();
  const panel = page.getByRole("dialog", { name: "Posting history" });
  const events = panel.getByRole("list", { name: "Events" });
  await expect(events).toContainText(`${msg("role-listing-age-published-by-the-employer")} · ${msg("role-listing-age-the-start")}`);
  await expect(events).toContainText(/Employer changed its date to .* · not counted from here/);
  await expect.poll(() => reads.answered).toBe(1);
});

/* The history opens in the side column it belongs to, edge to edge with it:
   under its button where it fits, above it where it does not, and on screen
   either way; it may cover what follows. */
async function openListingHistory(page: Page) {
  const event = { from_at: null, to_at: null, field: null, count: null, job_id: null, req_id: null, title: null, until: null, link: null };
  await page.route("/api/jobs/101/history", (route) => route.fulfill({ json: {
    headline: { since: "2026-10-24T00:00:00Z", days: 9, basis: "sighting" },
    role: null,
    events: [
      { ...event, at: "2026-10-24T00:00:00Z", kind: "first_seen" },
      { ...event, at: "2026-11-02T00:00:00Z", kind: "last_seen" },
    ],
    unconfirmed: [],
  } }));
  await page.goto("/company/openai/job/101");
  const cover = detail(page);
  const button = cover.locator("dl.kv").getByRole("button", { name: msg("role-listing-age-listing-history") });
  await button.click();
  const dialog = page.getByRole("dialog", { name: "Posting history" });
  await expect(dialog.getByRole("list", { name: "Events" })).toBeVisible();
  const panel = dialog.locator(".ui-popover-inner");
  // The pop-in scales the panel; measure where it settles.
  await panel.evaluate((el) => Promise.all(el.getAnimations().map((a) => a.finished)));
  return {
    panel,
    column: (await cover.locator(".jd-aside").boundingBox())!,
    opener: (await button.boundingBox())!,
  };
}

const bottomOf = async (panel: Locator) => {
  const box = (await panel.boundingBox())!;
  return box.y + box.height;
};

test("the listing history opens across the side column, under its button", async ({ page, isMobile }) => {
  test.skip(isMobile, "a phone's History button sits at the screen's bottom edge; the next test covers it");
  const { panel, column, opener } = await openListingHistory(page);
  await expect.poll(async () => (await panel.boundingBox())!.y).toBeGreaterThan(opener.y + opener.height);
  const box = (await panel.boundingBox())!;
  expect(Math.abs(box.x - column.x), "left edge on the column's").toBeLessThanOrEqual(1);
  expect(Math.abs(box.x + box.width - (column.x + column.width)), "right edge on the column's").toBeLessThanOrEqual(1);
  expect(box.y + box.height, "on screen").toBeLessThanOrEqual(page.viewportSize()!.height);
});

/* The job page scrolls only a little on a phone, so its History button sits
   at the screen's bottom edge with no room for the history under it. */
test("on a phone the listing history opens above its button, on screen", async ({ page, isMobile }) => {
  test.skip(!isMobile, "phone-height layout");
  const { panel, column, opener } = await openListingHistory(page);
  await expect.poll(() => bottomOf(panel), { message: "the history never covers its button" }).toBeLessThanOrEqual(opener.y);
  const box = (await panel.boundingBox())!;
  expect(opener.y + opener.height + box.height, "no room under the button").toBeGreaterThan(page.viewportSize()!.height);
  expect(Math.abs(box.x - column.x), "left edge on the column's").toBeLessThanOrEqual(1);
  expect(Math.abs(box.x + box.width - (column.x + column.width)), "right edge on the column's").toBeLessThanOrEqual(1);
  expect(box.y, "on screen").toBeGreaterThanOrEqual(0);
});

/* A posting showing two of three standing signs says which, and
   states its own limit. One sign, or none, says nothing at all. The
   screen states ONE age, in Details, from the employer's earlier date; the
   standing section names the sign without repeating the figure. */
test("a posting with two standing signs names them, and one without says nothing", async ({ page }) => {
  await page.route("/api/jobs/101", (route) => route.fulfill({ json: {
    ...jobFixture,
    days_open: 62,
    listed_since: "2026-04-30T00:00:00Z",
    listed_days: 150,
    posting_reality: {
      level: "possible", met: ["long_open", "relisted"], criteria_total: 3, listings: 3,
    },
  } }));
  await page.goto("/company/openai/job/101");
  const standing = detail(page).getByRole("region", { name: "May be an always-open posting" });
  await expect(standing).toBeVisible();
  await expect(standing).toContainText("Listed for a long time");
  const details = detail(page).locator("dl.kv");
  await expect(details.getByText("Listed for", { exact: true })).toBeVisible();
  await expect(details.getByText("150 days", { exact: true })).toBeVisible();
  await expect(detail(page).getByText("Days open")).toHaveCount(0);
  await expect(detail(page).getByText("62 days")).toHaveCount(0);
  await expect(standing).toContainText("Reposted 3 times");
  await expect(standing).toContainText("2 of 3 signs");

  await page.unroute("/api/jobs/101");
  await page.route("/api/jobs/101", (route) => route.fulfill({ json: {
    ...jobFixture,
    posting_reality: {
      level: "none", met: ["long_open"], criteria_total: 3, listings: 1,
    },
  } }));
  await page.reload();
  await expect(detail(page).getByRole("heading", { name: jobFixture.title })).toBeVisible();
  await expect(detail(page).getByRole("region", { name: "May be an always-open posting" })).toHaveCount(0);
});


/* Opened from a list, the detail covers a page that stays MOUNTED underneath.
   As a bare <section> (no dialog role, no aria-modal, no focus capture, no
   trap, no restore, no scroll lock) a keyboard user lands on the covered row,
   tabs through every control of a page they cannot see to reach "View & apply", and gets
   nothing back on close. Reached by a direct link
   there is nothing underneath, and it must NOT claim to be a dialog. */
test("opened over a list, the detail is a modal dialog that owns focus", async ({ page }) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  await page.goto("/");
  const row = page.getByRole("article").first();
  await row.getByRole("heading").click();

  const dialog = page.getByRole("dialog", { name: /^Role:/ });
  await expect(dialog).toBeVisible();
  await expect(dialog).toHaveAttribute("aria-modal", "true");

  // The page behind is locked, so the cover does not scroll a list nobody sees.
  await expect(page.locator("body")).toHaveCSS("overflow", "hidden");

  // Focus moved INTO the cover, and stays there however long you tab.
  await expect(dialog).toContainText("View & apply");
  for (let i = 0; i < 40; i += 1) {
    await page.keyboard.press("Tab");
    // WebKit's Tab skips buttons and can step out; the overlay brings focus
    // back one task later (ui/Overlay, which covers use), so
    // focus is judged once that task has run, as palette.spec does.
    await page.evaluate(() => new Promise<void>((resolve) => setTimeout(resolve, 0)));
    const inside = await dialog.evaluate((el) => el.contains(document.activeElement));
    expect(inside, `focus left the dialog after ${i + 1} tabs`).toBe(true);
  }

  // And it comes back to the row that opened it.
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  const restored = await row.evaluate((el) => el.contains(document.activeElement));
  expect(restored, "focus was not restored to the opening row").toBe(true);
});

test("reached by a direct link, the detail is the page, not a dialog", async ({ page }) => {
  await page.goto("/company/google/job/101");
  // The page's one main landmark (a cover reached by URL IS the page).
  await expect(page.getByRole("main", { name: /^Role:/ })).toBeVisible();
  await expect(page.getByRole("main")).toHaveCount(1);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  // Nothing is covered, so nothing is locked.
  await expect(page.locator("body")).not.toHaveCSS("overflow", "hidden");
});

/* Similar positions: two categories, three rows each, visibly two blocks.
   More rows, at body size under small labels, read as one wall. Each
   category's caption is quieter than the section's kicker above it. The
   source is answered with FIVE per scope on purpose: the cap must hold on
   the page even when the request's `limit` is ignored. */
test("similar positions show at most three per category, fetched as three, and the categories are set apart", async ({ page }) => {
  const similar = (scope: string) =>
    Array.from({ length: 5 }, (_, i) => ({
      ...jobFixture,
      id: (scope === "within" ? 900 : 950) + i,
      company: scope === "within" ? "openai" : "anthropic",
      title: `${scope === "within" ? "Same" : "Other"} similar role ${i + 1}`,
      score: 0.9 - i * 0.05,
    }));
  const requested: string[] = [];
  await page.route("/api/jobs/101/similar**", (route) => {
    const url = new URL(route.request().url());
    requested.push(url.search);
    return route.fulfill({ json: { scope: url.searchParams.get("scope"), items: similar(url.searchParams.get("scope")!) } });
  });

  await page.goto("/job/101");
  const panel = detail(page);
  const groups = panel.locator(".similar-group");
  await expect(groups).toHaveCount(2);
  await expect(groups.nth(0)).toContainText("Other companies");
  await expect(groups.nth(1)).toContainText("Same company · OpenAI");
  await expect(groups.nth(0).locator(".similar-row")).toHaveCount(3);
  await expect(groups.nth(1).locator(".similar-row")).toHaveCount(3);
  await expect(panel.getByText("Other similar role 4")).toHaveCount(0);
  await expect(panel.getByText("Same similar role 4")).toHaveCount(0);

  // Fetched as three, per scope: nothing is requested only to be hidden.
  // (The COUNT of requests is not asserted: dev StrictMode doubles every
  // mount, so the same pair is issued more than once there.)
  expect(requested.length).toBeGreaterThanOrEqual(2);
  for (const scope of ["within", "cross"]) expect(requested).toContain(`?scope=${scope}&limit=3`);
  for (const query of requested) expect(query).toMatch(/(\?|&)limit=3(&|$)/);

  // Set apart on the page, not only in the DOM: the second category opens
  // with a hairline (the first stands under the section's own), and a
  // category's head and its rows are on different type steps, with the rows
  // stepped below the body size of the prose.
  const metrics = await groups.nth(1).evaluate((group) => {
    const px = (el: Element | null, prop: string) => parseFloat(getComputedStyle(el!).getPropertyValue(prop));
    const head = group.querySelector(".similar-label");
    return {
      hairline: px(group, "border-top-width"),
      head: px(head, "font-size"),
      headCase: getComputedStyle(head!).textTransform,
      headWeight: px(head, "font-weight"),
      row: px(group.querySelector(".mj-title"), "font-size"),
      rowWeight: px(group.querySelector(".mj-title"), "font-weight"),
      body: parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--app-type-body")),
    };
  });
  expect(metrics.hairline).toBeGreaterThan(0);
  expect(metrics.head).not.toBe(metrics.row);
  expect(metrics.row).toBeLessThan(metrics.body);
  // The caption never outranks what it captions, nor the kicker over it.
  expect(metrics.head).toBeLessThan(metrics.row);
  expect(metrics.headWeight).toBeLessThan(metrics.rowWeight);
  expect(metrics.headCase).toBe("none");
  expect(await groups.nth(0).evaluate((group) => parseFloat(getComputedStyle(group).borderTopWidth)),
    "one line between the section's kicker and its first category, not two").toBe(0);
});

/* The eyebrow modifier's cascade.
 *
 * `.req-eyebrow` changes ONE property of the shared `.eyebrow` recipe: it is a
 * single-declaration modifier worn beside the shared class, which means it
 * wins on SOURCE ORDER at equal specificity, and
 * source order here spans two sheets: `.eyebrow` is in the always-loaded
 * `design/surfaces.css`, `.req-eyebrow` arrives in the job-detail route chunk.
 * That is precisely the shape not to reason about
 * ("specificity is relative, so relocating one silently inverts it"), so it is
 * measured in a browser instead: the eyebrow must paint the ACTION ink, and
 * must not have fallen back to the shared faint.
 */
test("the requirements eyebrow keeps its ink after folding into the shared recipe", async ({ page }) => {
  test.skip(true, "The role requirements panel is off the posting while its worth there is decided (JobDetail SHOW_REQUIREMENTS).");
  // The board harness's job carries no requirements, so the panel that owns
  // this eyebrow never mounts. Give it one.
  await page.route("/api/jobs/101", (route) =>
    route.fulfill({
      json: {
        ...jobFixture,
        requirements: {
          state: "ready",
          extractor_version: "test",
          qualifications: [],
          required_years: null,
          skills: [
            {
              concept_id: 1,
              slug: "python",
              facet: "technology",
              category: "Languages",
              importance_band: "core",
              importance_score: 1,
              confidence: "high",
              modality: "required",
              evidence: [],
            },
          ],
        },
      },
    }),
  );
  await page.goto("/");
  await page.getByRole("article").first().click();

  const eyebrow = page.getByText("Role requirements", { exact: true });
  await expect(eyebrow).toBeVisible();
  // It wears both: the shared recipe and the one-property modifier.
  await expect(eyebrow).toHaveClass(/(^|\s)eyebrow(\s|$)/);
  await expect(eyebrow).toHaveClass(/(^|\s)req-eyebrow(\s|$)/);

  const paint = await eyebrow.evaluate((el) => {
    const s = getComputedStyle(el);
    const root = getComputedStyle(document.documentElement);
    const probe = (token: string) => {
      const d = document.createElement("span");
      d.style.color = `var(${token})`;
      document.body.append(d);
      const v = getComputedStyle(d).color;
      d.remove();
      return v;
    };
    return {
      color: s.color,
      action: probe("--app-action-text"),
      faint: probe("--app-text-faint"),
      transform: s.textTransform,
      family: s.fontFamily,
      rootOk: Boolean(root),
    };
  });

  // The modifier won: action ink, not the shared faint it would inherit if the
  // cascade had gone the other way.
  expect(paint.color).toBe(paint.action);
  expect(paint.color).not.toBe(paint.faint);
  // And the shared recipe is still doing its half of the job.
  expect(paint.transform).toBe("uppercase");
  expect(paint.family).toMatch(/Plex Mono/i);
});

/* Picking for comparison while reading. With only Back, the star and "View &
   apply" on the cover, and the twin deck as the only compare entry, a reader
   who decides while reading has to close, find the row again and hit its
   icon. The selection is server state, so
   a pick made here is still standing when the cover closes — and the beacon
   that would say so does not raise until the second role, which is why the
   cover states the waiting half itself. */

test("a role is picked for comparison while reading it, and the pick is still standing on return", async ({ page }) => {
  await page.goto("/");
  await page.getByText("Staff Product Manager, API").click();

  const panel = detail(page);
  const toggle = panel.getByRole("button", { name: "Compare", exact: true });
  await expect(toggle).toHaveAttribute("aria-pressed", "false");
  // Nothing is claimed about a selection that does not exist yet.
  await expect(panel.getByText(/in compare/i)).toHaveCount(0);

  await toggle.click();
  await expect(panel.getByRole("button", { name: "In compare", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  // The waiting half, said where the gesture was made — and no promise of a
  // comparison that cannot be read yet.
  await expect(panel.getByText("1 in compare · pick one more")).toBeVisible();
  await expect(panel.getByRole("button", { name: /Compare 1 position/ })).toHaveCount(0);

  await page.getByRole("button", { name: "Back" }).click();
  await expect(page).toHaveURL(/\/$/);

  // Back on the board the role is already selected, waiting for its other half.
  const first = page.getByRole("article").filter({ hasText: "Staff Product Manager, API" });
  await expect(first.getByRole("button", { name: msg("jobs-compare") })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(page.getByRole("button", { name: /in compare/ })).toHaveCount(0);

  // The second role raises the beacon, exactly as if both had been picked here.
  const second = page.getByRole("article").filter({ hasText: "Principal Engineer, Platform" });
  await second.getByRole("button", { name: msg("jobs-compare") }).click();
  await expect(page.getByRole("button", { name: "2 in compare. Compare 2 roles" })).toBeVisible();
});

test("the second role picked while reading offers the comparison from the cover", async ({ page }) => {
  await page.goto("/");
  const first = page.getByRole("article").filter({ hasText: "Staff Product Manager, API" });
  await first.getByRole("button", { name: msg("jobs-compare") }).click();

  await page.getByText("Principal Engineer, Platform").click();
  const panel = detail(page);
  // The standing selection is stated even for a role that is not in it.
  await expect(panel.getByText("1 in compare · pick one more")).toBeVisible();

  await panel.getByRole("button", { name: "Compare", exact: true }).click();
  await expect(panel.getByRole("button", { name: "In compare", exact: true })).toBeVisible();
  await expect(panel.getByText("1 in compare · pick one more")).toHaveCount(0);

  const onward = panel.getByRole("button", { name: "Compare 2 roles" });
  await expect(onward).toBeVisible();
  await onward.click();
  await expect(page).toHaveURL(/\/compare$/);
  await expect(comparison(page)).toContainText("Comparing 2 roles");
});

test("the pick survives a reload of the cover itself", async ({ page }) => {
  // The gesture writes through to the store, not to the tab: a selection held
  // only in memory is lost on reload, and a cover reached by a direct link is
  // the case that would lose it silently.
  await page.goto("/job/202");
  const panel = detail(page);
  await panel.getByRole("button", { name: "Compare", exact: true }).click();
  await expect(panel.getByRole("button", { name: "In compare", exact: true })).toBeVisible();

  await page.reload();
  await expect(detail(page).getByRole("button", { name: "In compare", exact: true })).toBeVisible();
});

/* The cover's other occupant, on its failure path. A save that the
   server refuses rolls the star back and says so in a toast. Opened over a
   list, a toast rendered UNDER the cover would leave the star dark again with
   nothing on screen saying why. Both halves, as on the comparison: painted where it sits
   and reachable by a pointer there, and on the cover's Tab ring.

   The helper returns once the failure is ON SCREEN. The notice exists only
   after the server answers, and the cover reads its Tab ring at the keypress,
   so a Shift+Tab pressed before the notice arrives rightly goes round the
   cover alone, and the Tab-ring test would race it. The refusal also arrives a beat after the click, as a real
   server's does, so a helper that stops waiting fails every run, not some.
   */
async function openFailingSave(page: import("./fixtures").Page) {
  await page.route("/api/jobs/*/favorite", async (route) => {
    await new Promise((settle) => setTimeout(settle, 250));
    await route.fulfill({ status: 500, json: { detail: "unavailable" } });
  });
  await page.goto("/");
  await page.getByRole("article").first().getByRole("heading").click();
  const cover = page.getByRole("dialog", { name: /^Role:/ });
  await expect(cover).toHaveAttribute("aria-modal", "true");
  await expect.poll(() => strangersOver(cover)).toEqual([]);
  await cover.getByRole("button", { name: "Save", exact: true }).click();
  const toast = page.getByRole("status").filter({ hasText: "Couldn't save this role" });
  const close = toast.getByRole("button", { name: "Dismiss" });
  await expect(close).toBeVisible();
  return { cover, toast, close };
}

test("a failed save inside the cover is painted on top, and a pointer there clears it", async ({ page }) => {
  const { toast, close } = await openFailingSave(page);
  await expectOnTop(toast.getByText("Couldn't save this role"), "the failure notice");
  await expectOnTop(close, "its Dismiss");
  await pointAndClick(page, close);
  await expect(toast).toHaveCount(0);
});

test("a failed save inside the cover is on the cover's Tab ring", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === "mobile", "Tab order is a keyboard flow; a phone has no Tab key.");
  const { cover, toast, close } = await openFailingSave(page);
  await cover.getByRole("button", { name: "Back" }).focus();
  await page.keyboard.press("Shift+Tab");
  await expect(close).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(toast).toHaveCount(0);
});

/* A role RoleBand has dropped (removed after it stopped being listed) is
   said as that, with no Try again that cannot help; any other failure keeps
   Try again. Neither names the API or the service. */
test("a role that is gone says so, and a failed load offers Try again in the person's words", async ({ page }) => {
  await page.route("/api/jobs/9999", (route) => route.fulfill({ status: 404, json: { detail: "job not found" } }));
  await page.goto("/job/9999");
  const gone = page.getByRole("alert");
  await expect(gone).toContainText("Couldn't load this role");
  await expect(gone).toContainText("This role no longer exists.");
  await expect(gone.getByRole("button", { name: "Try again" })).toHaveCount(0);
  await expect(page.getByText(/API|service/)).toHaveCount(0);

  await page.route("/api/jobs/9998", (route) => route.fulfill({ status: 500, json: { detail: "boom" } }));
  await page.goto("/job/9998");
  const failed = page.getByRole("alert");
  await expect(failed).toContainText("Couldn't get it just now.");
  await expect(failed.getByRole("button", { name: "Try again" })).toBeVisible();
  await expect(page.getByText(/API|service/)).toHaveCount(0);
});
