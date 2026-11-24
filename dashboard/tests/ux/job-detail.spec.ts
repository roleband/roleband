/* The opportunity detail: what the full-screen cover shows, how it is reached,
   and what it writes. The shell is full-screen, so its entry paths (row
   click, /job/:id, company-scoped URL, back/forward) are the contract. */

import type { Locator, Page } from "@playwright/test";
import { msg } from "../../src/test/msg";
import { expect, mockApi, mockGet, test, viewChoices, watchReads } from "./fixtures";
import { applicationCardFixture, applicationDetailFixture, compPackageFixture, jobFixture, stepFixture } from "../../src/test/fixtures";
import { appleJobFixture, comparison, detail, installBoardRoutes, jobFixture2, twoJobList } from "./boardHarness";
import { expectOnTop, pointAndClick, strangersOver } from "./paint";

/* Controls named by what the catalog says, so a copy edit cannot fail a test
   that is not about copy. A stage button carries its days after the stage, and
   the stage menu its posting's title, so both stay prefixes. */
const STAGE_APPLIED = new RegExp(`^${msg("taxonomy-stage-applied")}\\b`);
const STAGE_MENU = new RegExp(`^${msg("applications-stage-menu-label", { title: "" }).trimEnd()}`);
const VIEW_APPLY = new RegExp(`^${msg("role-job-detail-view-apply")}$`, "i");

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
      // A package with a figure: a posting with none draws no pay panel to measure against.
      route.fulfill({ json: { ...appleJobFixture, comp_package: compPackageFixture(), requirements: readyRequirements } }),
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
    route.fulfill({ json: { ...jobFixture, comp_package: compPackageFixture(), requirements: readyRequirements } }),
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
  await expect(page.getByRole("link", { name: "Apply", exact: true })).toBeVisible();
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

  /* One primary per surface. Job detail's is "Apply" — the
     one thing that page exists for — so opening this disclosure must not put a
     second filled button beside it. A rank rule of "primary = commits state"
     cannot express this: neither of these two commits anything. */
  const primaries = await page.locator(".ui-btn-primary:visible").allInnerTexts();
  expect(
    primaries.map((t) => t.trim()),
    "more than one primary is visible on Job detail",
  ).toEqual(["Apply"]);

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
  // Applied, the employer's page is no longer the action: the bar offers no link.
  await expect(bar.getByRole("link")).toHaveCount(0);
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

  // Every row is one line high, the ones with the priority's button and the
  // history's clock included: a control taller than the text must not push
  // its row apart from the rest.
  const heights = await facts.locator("dd").evaluateAll((rows) => rows.map((row) => Math.round(row.getBoundingClientRect().height)));
  expect(heights.length).toBe(5);
  expect(new Set(heights).size, `row heights ${heights.join(", ")}`).toBe(1);
  // The priority's word stands at the other values' edge.
  const word = await value(msg("applications-fact-priority")).evaluate((dd) => {
    const range = document.createRange();
    range.selectNodeContents(dd.querySelector("button")!);
    return range.getBoundingClientRect().left - dd.getBoundingClientRect().left;
  });
  expect(word, "the mark and the word start at the row's edge").toBeLessThanOrEqual(1);

  // The section leads nowhere: the Workspace is a tab of this same screen.
  await expect(panel.locator(".jd-aside").getByRole("link")).toHaveCount(0);
  await expect(panel.getByRole("tab", { name: msg("role-job-detail-tab-workspace") })).toBeVisible();

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
    probe.style.color = "var(--app-chosen-mark)";
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
/** The long posting, of a role in the pipeline unless `inPipeline` is false:
 *  then it reads as any posting on the Radar, with no tabs. */
async function openLongPosting(page: Page, size: { width: number; height: number }, { inPipeline = true } = {}) {
  await page.setViewportSize(size);
  await mockGet(page, "/api/jobs/303", (route) => route.fulfill({
    json: inPipeline ? longPosting : { ...longPosting, is_favorite: false, pursuit: null },
  }));
  if (inPipeline) {
    await mockGet(page, "/api/applications/303", (route) => route.fulfill({ json: applicationDetailFixture({
      application: applicationCardFixture({ job_id: 303, pursuit_id: 10, stage: "applied", company: "apple", stage_since: new Date(Date.now() - 3 * DAY).toISOString() }),
    }) }));
  }
  await mockGet(page, "/api/jobs/303/similar**", (route) => route.fulfill({ json: {
    scope: "cross", items: [1, 2, 3].map((n) => ({ ...jobFixture, id: 900 + n, title: `Principal Product Manager, Platform ${n}`, score: 0.9 })),
  } }));
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/company/apple/job/303");
  const panel = detail(page);
  await expect(panel.getByRole("heading", { name: "Responsibilities" })).toBeVisible();
  await expect(panel.locator(".similar-row")).toHaveCount(6);
  const tabs = panel.locator(".jd-tabs");
  await expect(tabs).toHaveCount(inPipeline ? 1 : 0);
  return {
    column: panel.locator(".jd-aside"),
    scroll: panel.locator(".cover-scroll"),
    pipeline: panel.locator(".jd-aside .section-title").first(),
    lastRow: panel.locator(".similar-row").last(),
    /** How tall the tabs held under the bar are; what else is held stops under them. */
    held: inPipeline ? (await tabs.boundingBox())!.height : 0,
  };
}
/** How far under the bar, or the tabs, the column stops: the page's own top inset. */
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
  const { column, scroll, pipeline, lastRow, held } = await openLongPosting(page, { width: 1440, height: 1000 });
  const card = (await detail(page).locator(".comp-panel").boundingBox())!;
  const atRest = (await column.boundingBox())!;
  expect(atRest.y, "at the top it stands beside the pay panel").toBeCloseTo(card.y, 0);

  await scrollPosting(scroll, 1500);
  const box = (await scroll.boundingBox())!;
  const stuck = (await column.boundingBox())!;
  expect(stuck.y - box.y, "stopped under the tabs").toBeCloseTo(held + STUCK, 0);
  await expect(pipeline).toBeInViewport({ ratio: 1 });
  // Its More like this rows have folded away while the posting is read.
  await expect(lastRow).toBeHidden();
  await expect(column.locator("dl.kv").first()).toBeInViewport({ ratio: 1 });
  // Fail-first: a column that scrolls with the page is 1500px above the window here.
  await expect(detail(page).getByText("Paragraph 12.")).toBeInViewport();
});

test("a side column taller than the window keeps its first rows in view, and its last rows come at the end of the page", async ({ page }) => {
  const { column, scroll, pipeline, lastRow, held } = await openLongPosting(page, { width: 1440, height: 560 });
  const atRest = (await column.boundingBox())!;
  const box = (await scroll.boundingBox())!;
  expect(atRest.height, "taller than its room").toBeGreaterThan(box.height - held - 2 * STUCK);
  // Fail-first: a column with a scroll of its own is clipped to its room.
  expect(await column.evaluate((el) => [getComputedStyle(el).overflowY, el.scrollHeight - el.clientHeight])).toEqual(["visible", 0]);

  await scrollPosting(scroll, 1500);
  // More like this folds while the posting is read; opened again, the column is its full length.
  // Its button is one of the rows below the window's edge here, so it is pressed
  // where it stands: a pointer click would first scroll the page to its end.
  const more = column.getByRole("button", { name: msg("role-job-detail-more-like-this") });
  await expect(more).not.toBeInViewport();
  await more.dispatchEvent("click");
  await expect(lastRow).toBeVisible();
  expect(Math.abs((await scroll.evaluate((el) => el.scrollTop)) - 1500), "the page stays where it was read").toBeLessThanOrEqual(1);
  const stuck = (await column.boundingBox())!;
  expect(stuck.y - box.y, "stopped under the tabs").toBeCloseTo(held + STUCK, 0);
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
  const { scroll, held } = await openLongPosting(page, { width: 1440, height: 1000 });
  const panel = detail(page);
  const role = panel.locator(".jd-bar-role");
  const heading = panel.getByRole("heading", { name: "Responsibilities" });
  await expect(role).not.toHaveAttribute("data-shown", "");
  await expect.poll(() => role.evaluate((el) => getComputedStyle(el).opacity)).toBe("0");
  await expect(role, "a copy for the eye: the heading is the one read out").toHaveAttribute("aria-hidden", "true");

  await scrollPosting(scroll, 1500);
  const box = (await scroll.boundingBox())!;
  expect((await heading.boundingBox())!.y, "stuck under the tabs at the top of the scroll box").toBeCloseTo(box.y + held, 0);
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
  await expect.poll(() => heading.evaluate((el) => {
    const style = getComputedStyle(el);
    return [style.backgroundColor, style.boxShadow];
  })).toEqual(["rgba(0, 0, 0, 0)", "none"]);
});

/* The pay panel leads the page. As its last part leaves, its small copy grows
   at the top of the side column, with the scroll and back with it; it says
   what the panel says. */
test("the pay panel's small copy grows above Pipeline as the panel leaves, and goes when it returns", async ({ page }) => {
  const { column, scroll, pipeline, held } = await openLongPosting(page, { width: 1440, height: 1000 });
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
  expect((await dock.boundingBox())!.y - (await scroll.boundingBox())!.y, "in view, under the tabs").toBeCloseTo(held + STUCK, 0);

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

/* A posting with no pay figure and no estimate draws no pay panel, and nothing
   docks, because there is nothing to keep in view. */
test("a posting with no pay figure docks nothing above Pipeline", async ({ page }) => {
  await mockGet(page, "/api/jobs/303", (route) => route.fulfill({ json: {
    ...longPosting, comp_package: compPackageFixture({ state: "none_stated", estimate: null }),
  } }));
  await mockGet(page, "/api/applications/303", (route) => route.fulfill({ json: applicationDetailFixture({
    application: applicationCardFixture({ job_id: 303, pursuit_id: 10, stage: "applied", company: "apple" }),
  }) }));
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/company/apple/job/303");
  const panel = detail(page);
  await expect(panel.getByRole("heading", { name: "Responsibilities" })).toBeVisible();
  await expect(panel.locator(".comp-panel"), "no pay panel").toHaveCount(0);
  await expect(panel.getByText(/no pay|no range/i), "no line about the posting's pay").toHaveCount(0);
  const scroll = panel.locator(".cover-scroll");
  const column = panel.locator(".jd-aside");
  await scrollPosting(scroll, 1500);
  expect((await column.locator(".jd-dock").boundingBox())!.height).toBe(0);
  await expect(column.locator(".pkg-mini")).toHaveCount(0);
  await expect(column.locator(".section-title").first(), "Pipeline leads the column").toHaveText(msg("applications-posting-row"));
  const held = (await panel.locator(".jd-tabs").boundingBox())!.height;
  expect((await column.boundingBox())!.y - (await scroll.boundingBox())!.y, "under the tabs").toBeCloseTo(held + STUCK, 0);
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

/* A role outside the pipeline reads as any posting on the Radar: one view,
   the hero's foot line, and what is held stops under the bar. */
test("a role outside the pipeline has no tabs, and its headings and side column stop under the bar", async ({ page }) => {
  const { column, scroll } = await openLongPosting(page, { width: 1440, height: 1000 }, { inPipeline: false });
  const panel = detail(page);
  await expect(panel.getByRole("tablist")).toHaveCount(0);
  expect(await panel.locator(".jd-hero").evaluate((el) => getComputedStyle(el).borderBottomWidth), "the hero's line").toBe("1px");
  // Reached by its link, Back goes to the Radar and says so.
  await expect(panel.getByRole("button", { name: msg("role-job-detail-back-to", { view: msg("shell-nav-radar") }) }))
    .toHaveText(msg("shell-nav-radar"));
  await scrollPosting(scroll, 1500);
  const box = (await scroll.boundingBox())!;
  expect((await panel.getByRole("heading", { name: "Responsibilities" }).boundingBox())!.y, "at the box's top edge").toBeCloseTo(box.y, 0);
  expect((await column.boundingBox())!.y - box.y).toBeCloseTo(STUCK, 0);
});

/* A role in the pipeline reads in two tabs under its title. They take the
   hero's foot line without moving the title, and once scrolled to they are
   held under the bar with room above their words. */
test("a role in the pipeline holds its tabs under the bar, with room above them, and its title does not move", async ({ page }) => {
  const outside = await openLongPosting(page, { width: 1440, height: 1000 }, { inPipeline: false });
  const titleOutside = (await detail(page).locator(".jd-hero h1").boundingBox())!.y;
  // The top of the hero's foot line, where the tabs' words take its place.
  const lineOutside = await detail(page).locator(".jd-hero").evaluate((el) =>
    el.getBoundingClientRect().bottom - parseFloat(getComputedStyle(el).borderBottomWidth));
  expect(outside.held).toBe(0);
  await page.unrouteAll({ behavior: "ignoreErrors" });
  await installBoardRoutes(page);

  const { scroll, held } = await openLongPosting(page, { width: 1440, height: 1000 });
  const panel = detail(page);
  const tabs = panel.locator(".jd-tabs");
  expect((await panel.locator(".jd-hero h1").boundingBox())!.y, "the title stands where it did").toBeCloseTo(titleOutside, 0);
  const room = await tabs.evaluate((el) => parseFloat(getComputedStyle(el).paddingTop));
  expect(room, "room above the tabs' words").toBeGreaterThan(0);
  expect((await panel.getByRole("tablist").boundingBox())!.y, "the tabs' words start where the hero's line was").toBeCloseTo(lineOutside, 0);
  await expect(panel.getByRole("tab", { name: msg("role-job-detail-tab-posting") }), "opened by its link: the posting")
    .toHaveAttribute("aria-selected", "true");
  expect(await tabs.evaluate((el) => getComputedStyle(el).backgroundColor), "in their place, no ground over the hero's")
    .toBe("rgba(0, 0, 0, 0)");

  await scrollPosting(scroll, 1500);
  const box = (await scroll.boundingBox())!;
  const at = (await tabs.boundingBox())!;
  expect(at.y, "held at the top of the box, under the bar").toBeCloseTo(box.y, 0);
  expect(at.height).toBe(held);
  const words = (await panel.getByRole("tablist").boundingBox())!;
  expect(words.y - box.y, "room between the bar's edge and the tabs").toBeCloseTo(room, 0);
  await expect.poll(() => tabs.evaluate((el) => getComputedStyle(el).backgroundColor), "solid, so the text passes under it")
    .not.toBe("rgba(0, 0, 0, 0)");
});

test("switching tabs while they are held opens the other one from its start, with the tabs still held", async ({ page }) => {
  await mockGet(page, "/api/applications/303/activity", (route) => route.fulfill({ json: { items: [] } }));
  const { scroll } = await openLongPosting(page, { width: 1440, height: 1000 });
  const panel = detail(page);
  const tabs = panel.locator(".jd-tabs");
  const box = (await scroll.boundingBox())!;
  // Where the tabs stand unheld: the scroll at which they reach the box's top.
  const natural = (await tabs.boundingBox())!.y - box.y;

  // Above that line, a switch leaves the page where it is.
  await panel.getByRole("tab", { name: msg("role-job-detail-tab-workspace") }).click();
  await expect(page).toHaveURL(/\?tab=workspace$/);
  expect(await scroll.evaluate((el) => el.scrollTop)).toBe(0);
  await panel.getByRole("tab", { name: msg("role-job-detail-tab-posting") }).click();
  await expect(page).toHaveURL(/\?tab=posting$/);
  // The address changes before the posting is drawn: scrolled any sooner, the
  // short Workspace would still stand and the page could not go down.
  await expect(panel.getByRole("heading", { name: "Responsibilities" })).toBeVisible();

  await scrollPosting(scroll, 1500);
  expect(await scroll.evaluate((el) => el.scrollTop), "read past the tabs").toBeGreaterThan(natural);
  await panel.getByRole("tab", { name: msg("role-job-detail-tab-workspace") }).click();
  await expect(panel.locator(".app-ws")).toBeVisible();
  // Within a pixel: a phone's scroll lands on whole device pixels.
  await expect.poll(async () => Math.abs((await scroll.evaluate((el) => el.scrollTop)) - natural), "the Workspace from its start").toBeLessThanOrEqual(1);
  expect((await tabs.boundingBox())!.y, "still held").toBeCloseTo(box.y, 0);

  await scrollPosting(scroll, 1500);
  await panel.getByRole("tab", { name: msg("role-job-detail-tab-posting") }).click();
  await expect.poll(async () => Math.abs((await scroll.evaluate((el) => el.scrollTop)) - natural), "the posting from its start").toBeLessThanOrEqual(1);
  expect((await tabs.boundingBox())!.y).toBeCloseTo(box.y, 0);
  await expect(panel.locator(".pkg-panel")).toBeInViewport();
});

/** The long posting's Workspace, its application as `card` says and its
 *  activity as `items` holds. */
async function openWorkspace(
  page: Page,
  { card = {}, items = [], done = [], size = { width: 1440, height: 1000 } }: {
    card?: Parameters<typeof applicationCardFixture>[0];
    items?: unknown[];
    done?: ReturnType<typeof stepFixture>[];
    size?: { width: number; height: number };
  } = {},
) {
  await mockGet(page, "/api/applications/303/activity", (route) => route.fulfill({ json: { items } }));
  await openLongPosting(page, size);
  await mockGet(page, "/api/applications/303", (route) => route.fulfill({ json: applicationDetailFixture({
    application: applicationCardFixture({
      job_id: 303, pursuit_id: 10, stage: "applied", company: "apple", stage_since: new Date(Date.now() - 3 * DAY).toISOString(),
      ...card,
    }),
    done_steps: done,
  }) }));
  await page.goto("/company/apple/job/303?tab=workspace");
  const panel = detail(page);
  await expect(panel.locator(".app-ws")).toBeVisible();
  return { panel, column: panel.locator(".jd-aside"), scroll: panel.locator(".cover-scroll") };
}

/* A role opened on its Workspace with little in it yet scrolls as a posting
   does: to the end, the tabs are held under the bar, not left with the hero's
   last line at the top. */
test("a short Workspace still scrolls its tabs up under the bar, in any window height", async ({ page }) => {
  const { panel, scroll } = await openWorkspace(page);
  const tabs = panel.locator(".jd-tabs");
  for (const height of [1000, 1300]) {
    await page.setViewportSize({ width: 1440, height });
    const box = (await scroll.boundingBox())!;
    // Fail-first: what the Workspace holds is shorter than the room under the tabs.
    const content = await panel.locator(".jd-main").evaluate((el) => el.scrollHeight);
    expect(content, "a short Workspace").toBeLessThan(box.height - (await tabs.boundingBox())!.height);
    // The room is measured again once the window has changed: scrolled to the
    // end after that, the tabs are held.
    await expect.poll(async () => {
      await scrollPosting(scroll, 100000);
      return (await tabs.boundingBox())!.y - box.y;
    }, `held at ${height}`).toBeCloseTo(0, 0);
    await expect(tabs).toHaveAttribute("data-stuck", "");
    await scrollPosting(scroll, 0);
  }
});

/* The room under the tabs is measured from where they stand unheld, under the
   hero. Measured from where they are held, far down a posting, the columns
   would keep the height of all that was scrolled past, and a shorter tab
   would end on blank space. */
test("a window resized far down a posting leaves the columns no taller than the window", async ({ page }) => {
  const { panel, scroll } = await openWorkspace(page);
  await panel.getByRole("tab", { name: msg("role-job-detail-tab-posting") }).click();
  const grid = panel.locator(".jd-grid");
  const minHeight = () => grid.evaluate((el) => Number.parseFloat(el.style.minHeight));
  await scrollPosting(scroll, 3000);
  // Fail-first: the columns start far above the held tabs.
  const scrolledPast = (await panel.locator(".jd-tabs").boundingBox())!.y - (await grid.boundingBox())!.y;
  expect(scrolledPast, "scrolled far past where the tabs stand unheld").toBeGreaterThan(500);
  const before = await minHeight();

  await page.setViewportSize({ width: 1440, height: 900 });
  await expect.poll(minHeight, "measured again for the new window").not.toBe(before);
  expect(await minHeight()).toBeLessThan(await scroll.evaluate((el) => el.clientHeight));
});

/* Held, the tabs' band ends inside the page's wash, which brightens toward the
   window's top right. Its ground is the page's own, so where it ends no edge
   shows: the pixel just inside its right end and the one just outside match. */
for (const theme of ["dark", "light"] as const) {
  test(`held tabs end on the page's wash with no edge (${theme})`, async ({ page }) => {
    await page.addInitScript((value) => localStorage.setItem("theme", value), theme);
    const { panel, scroll } = await openWorkspace(page);
    await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
    const tabs = panel.locator(".jd-tabs");
    await expect.poll(async () => {
      await scrollPosting(scroll, 100000);
      return tabs.getAttribute("data-stuck");
    }).toBe("");
    const band = (await tabs.boundingBox())!;
    const right = Math.floor(band.x + band.width);
    expect(right, "the band ends inside the window").toBeLessThan(page.viewportSize()!.width - 8);
    // Mid-height: clear of the tab words at the left and the hairline at the foot.
    const y = Math.floor(band.y + band.height / 2);
    const [inside, , , , outside] = await pixels(page, await page.screenshot({ clip: { x: right - 3, y, width: 5, height: 1 }, scale: "css" }));
    const canvas = await page.evaluate(() => {
      const probe = document.createElement("i");
      probe.style.color = "var(--app-canvas)";
      document.body.append(probe);
      const [r, g, b] = getComputedStyle(probe).color.match(/\d+/g)!.map(Number);
      probe.remove();
      return [r, g, b] as Rgb;
    });
    // Fail-first: here the wash differs from the base colour, so a band
    // filled with the base colour alone would show its edge.
    expect(distance(outside, canvas), "the wash is visible where the band ends").toBeGreaterThan(3);
    expect(distance(inside, outside), `inside ${inside} vs outside ${outside}`).toBeLessThanOrEqual(2);
  });
}

type Rgb = [number, number, number];

/** Decodes a screenshot in the page and returns each pixel's sRGB channels. */
async function pixels(page: Page, png: Buffer): Promise<Rgb[]> {
  return page.evaluate(async (bytes) => {
    const bitmap = await createImageBitmap(new Blob([new Uint8Array(bytes)], { type: "image/png" }));
    const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
    const context = canvas.getContext("2d")!;
    context.drawImage(bitmap, 0, 0);
    const { data } = context.getImageData(0, 0, bitmap.width, bitmap.height);
    const out: [number, number, number][] = [];
    for (let i = 0; i < data.length; i += 4) out.push([data[i], data[i + 1], data[i + 2]]);
    return out;
  }, [...png]);
}

/** The largest per-channel difference between two colours. */
const distance = (a: Rgb, b: Rgb) => Math.max(...a.map((c, i) => Math.abs(c - b[i])));

/** True when two boxes share any area. */
const overlaps =(a: { x: number; y: number; width: number; height: number }, b: typeof a) =>
  a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height;

test("on the Workspace the side column keeps where the role stands, with no posted pay or posting facts", async ({ page }) => {
  const { panel, column } = await openWorkspace(page, { card: { next_action: "Email the recruiter", next_action_due: tomorrowNoon() } });
  await expect(column.locator(".jd-pipeline-facts")).toBeVisible();
  await expect(column.locator(".jd-dock"), "the posted pay is the posting's").toHaveCount(0);
  await expect(column.getByText(msg("role-job-detail-details"), { exact: true }), "the posting's Details stay on its tab").toHaveCount(0);
  await expect(column.locator(".similar-row")).toHaveCount(0);
  await expect(panel.locator(".pkg-panel")).toHaveCount(0);
  await expect(panel.locator(".jd-main").getByText("Email the recruiter")).toBeVisible();
  const terms = await column.locator("dl.jd-pipeline-facts dt").allTextContents();
  expect(terms).not.toContain(msg("applications-posting-next-step"));
  expect(terms).not.toContain(msg("applications-posting-due"));
  expect(terms).toContain(msg("applications-fact-priority"));

  // Back on the posting, its pay and Details return.
  await panel.getByRole("tab", { name: msg("role-job-detail-tab-posting") }).click();
  await expect(panel.locator(".pkg-panel")).toBeVisible();
  await expect(column.locator(".jd-dock")).toHaveCount(1);
  await expect(column.getByText(msg("role-job-detail-details"), { exact: true })).toBeVisible();
});

const LONG_STEP = `Ask Mo for an ${"introduction".repeat(6)} before the panel, and who else joins the system design round`;

test("a long next step wraps in its own column: nothing paints over its day or its edit button", async ({ page }) => {
  const { panel } = await openWorkspace(page, { card: { next_action: LONG_STEP, next_action_due: tomorrowNoon() } });
  const step = panel.locator(".app-ws-step");
  const words = (await step.locator(".app-ws-step-words").boundingBox())!;
  const due = (await step.locator(".app-due").boundingBox())!;
  const edit = (await step.getByRole("button", { name: msg("applications-ws-next-edit", { step: LONG_STEP }) }).boundingBox())!;
  const lines = await step.locator(".app-ws-step-words").evaluate((el) => Math.round(el.getBoundingClientRect().height / parseFloat(getComputedStyle(el).lineHeight)));
  expect(lines, "the step wraps").toBeGreaterThan(1);
  // The words' own box, and what they paint: nothing reaches past it.
  expect(await step.locator(".app-ws-step-words").evaluate((el) => el.scrollWidth <= el.clientWidth + 1), "no word runs out of its column").toBe(true);
  expect(overlaps(words, due), "the words and the day").toBe(false);
  expect(overlaps(words, edit), "the words and the edit button").toBe(false);
  // The day and the button stay level with the first line.
  expect(due.y + due.height / 2).toBeCloseTo(words.y + (edit.height / 2), -1);
});

test("writing a next step grows its field with the text, with the day and Save step on the line below", async ({ page }) => {
  const { panel } = await openWorkspace(page);
  const field = panel.getByRole("textbox", { name: msg("applications-ws-next-add") });
  const oneLine = (await field.boundingBox())!.height;
  await field.fill(LONG_STEP);
  await expect.poll(async () => (await field.boundingBox())!.height, "the field grows").toBeGreaterThan(oneLine * 1.5);
  expect(await field.evaluate((el) => el.scrollHeight <= el.clientHeight + 1), "every line of it in view").toBe(true);
  const box = (await field.boundingBox())!;
  const day = (await panel.getByLabel(msg("applications-ws-next-due")).boundingBox())!;
  const save = (await panel.getByRole("button", { name: msg("applications-next-save") }).boundingBox())!;
  expect(day.y, "the day is below the words").toBeGreaterThanOrEqual(box.y + box.height);
  expect(save.y, "Save step is below the words").toBeGreaterThanOrEqual(box.y + box.height);
});

/* A step's day is the app's own field: any part of it, and the word Due
   beside it, opens the month the interview form picks its day from. */
test("a click anywhere on a step's day field opens the month, and a day picked shows in it", async ({ page, isMobile }) => {
  test.skip(isMobile, "phones are not supported");
  const { panel } = await openWorkspace(page);
  await panel.getByRole("textbox", { name: msg("applications-ws-next-add") }).fill("Send the portfolio");
  await expect(panel.locator('input[type="date"]')).toHaveCount(0);
  const field = panel.getByRole("button", { name: new RegExp(`^${msg("applications-ws-next-due")} `) });
  const month = page.getByRole("dialog", { name: msg("applications-ws-next-due") });
  const box = (await field.boundingBox())!;
  // Its icon, its words and its chevron, then the label before it.
  const spots: [string, () => Promise<void>][] = [
    ["the icon", () => field.click({ position: { x: 10, y: box.height / 2 } })],
    ["the words", () => field.click({ position: { x: box.width / 2, y: box.height / 2 } })],
    ["the chevron", () => field.click({ position: { x: box.width - 9, y: box.height / 2 } })],
    ["the label", () => panel.locator("label", { hasText: msg("applications-ws-next-due") }).click()],
  ];
  for (const [spot, click] of spots) {
    await click();
    await expect(month, `${spot} opens the month`).toBeVisible();
    await expect(month.locator(".app-daypicker .app-month-grid")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(month).toBeHidden();
  }
  await field.click();
  const picked = month.locator(".app-month-day:not([data-outside])").nth(14);
  const name = (await picked.getAttribute("aria-label"))!;
  await picked.click();
  await expect(month).toBeHidden();
  // The field writes the day as the month names it.
  await expect(field).toHaveText(name);
});

/** Where a field's words start, from the page's left. */
const textStart = (field: Locator) =>
  field.evaluate((el) => el.getBoundingClientRect().left + parseFloat(getComputedStyle(el).paddingLeft) + parseFloat(getComputedStyle(el).borderLeftWidth));

test("the notes keep their words off the field's edge, at the comment field's inset", async ({ page }) => {
  const { panel } = await openWorkspace(page);
  const notes = panel.getByRole("textbox", { name: msg("applications-notes-label") });
  await notes.focus();
  const room = await notes.evaluate((el) => {
    const style = getComputedStyle(el);
    return { top: parseFloat(style.paddingTop), left: parseFloat(style.paddingLeft), radius: parseFloat(style.borderTopLeftRadius) };
  });
  expect(room.top, "room above the first line").toBeGreaterThanOrEqual(8);
  expect(room.left, "room before the words").toBeGreaterThanOrEqual(room.radius);
  // The page is a field like the comment's: its words start where the comment's do.
  const comment = panel.getByRole("textbox", { name: msg("applications-comment-label") });
  expect(await textStart(notes)).toBeCloseTo(await textStart(comment), 0);
});

/* Every field in the Workspace is a field like any other: its ring is drawn
   over its own edge, and the field, ring and all, stands inside its card's
   content edges. A ring outside the edge doubles the frame; a field reaching
   into the card's padding looks misplaced. */
test("each Workspace field rings on its own edge and stays inside its card", async ({ page }) => {
  const { panel } = await openWorkspace(page);
  await panel.getByRole("textbox", { name: msg("applications-ws-next-add") }).fill("Send the portfolio");
  // Which content edges a field stands on: the next step's field starts past
  // the ticks' column, where the steps' words start.
  const nextStep = panel.getByRole("textbox", { name: msg("applications-ws-next-add") });
  const fields: [string, Locator, { start: boolean; end: boolean }][] = [
    ["notes", panel.getByRole("textbox", { name: msg("applications-notes-label") }), { start: true, end: true }],
    ["next step", nextStep, { start: false, end: true }],
    ["step day", panel.getByRole("button", { name: new RegExp(`^${msg("applications-ws-next-due")} `) }), { start: false, end: false }],
    ["comment", panel.getByRole("textbox", { name: msg("applications-comment-label") }), { start: true, end: true }],
  ];
  for (const [name, field, flush] of fields) {
    // A click on the day opens its month, which takes the keyboard: the day
    // field is reached the way the keyboard reaches it, from the words.
    if (name === "step day") {
      await nextStep.click();
      await page.keyboard.press("Tab");
      await expect(field).toBeFocused();
    } else {
      await field.click();
    }
    const ring = await field.evaluate(async (el) => {
      // Under reduced motion every change of style is a short transition:
      // reading the style starts it, and the ring is read once it has landed.
      getComputedStyle(el).outlineOffset;
      await Promise.all(el.getAnimations().map((animation) => animation.finished.catch(() => {})));
      const style = getComputedStyle(el);
      const width = parseFloat(style.outlineWidth);
      const offset = parseFloat(style.outlineOffset);
      const reach = Math.max(0, offset + width);
      const box = el.getBoundingClientRect();
      const card = el.closest(".app-ws-card")!;
      const cardStyle = getComputedStyle(card);
      const edge = card.getBoundingClientRect();
      const left = edge.left + parseFloat(cardStyle.borderLeftWidth) + parseFloat(cardStyle.paddingLeft);
      const right = edge.right - parseFloat(cardStyle.borderRightWidth) - parseFloat(cardStyle.paddingRight);
      return {
        style: style.outlineStyle,
        width,
        offset,
        border: parseFloat(style.borderTopWidth),
        before: box.left - reach - left,
        after: right - (box.right + reach),
      };
    });
    expect(ring.style, `${name}: the ring`).toBe("solid");
    expect(ring.width, `${name}: the ring's width`).toBeGreaterThanOrEqual(2);
    expect(ring.offset, `${name}: the ring is over the field's edge`).toBeLessThanOrEqual(-ring.border);
    expect(ring.before, `${name}: inside the card's left content edge`).toBeGreaterThanOrEqual(-0.5);
    expect(ring.after, `${name}: inside the card's right content edge`).toBeGreaterThanOrEqual(-0.5);
    if (flush.start) expect(ring.before, `${name}: on the card's left content edge`).toBeLessThanOrEqual(0.5);
    if (flush.end) expect(ring.after, `${name}: on the card's right content edge`).toBeLessThanOrEqual(0.5);
  }
});

/* The line that adds a step stands at the steps' own level: a plus in the
   ticks' column and the field where the words are. Set in under the last
   step, it would read as part of that step. */
test("the line that adds a step is a row of the list, level with the steps", async ({ page }) => {
  const { panel } = await openWorkspace(page, { card: { next_action: "Email the recruiter", next_action_due: tomorrowNoon() } });
  const steps = panel.locator(".app-ws-steps");
  const tick = (await steps.getByRole("button", { name: msg("applications-upnext-done-label", { step: "Email the recruiter" }) }).boundingBox())!;
  const words = (await steps.locator(".app-ws-step-words").first().boundingBox())!;
  const plus = (await steps.locator(".app-ws-step-plus").boundingBox())!;
  const field = panel.getByRole("textbox", { name: msg("applications-ws-next-add") });
  const box = (await field.boundingBox())!;
  expect(Math.abs(plus.x - tick.x), "the plus stands in the ticks' column").toBeLessThanOrEqual(0.5);
  expect(Math.abs(plus.width - tick.width), "as wide as a tick").toBeLessThanOrEqual(0.5);
  expect(Math.abs(box.x - words.x), "the field starts where the steps' words do").toBeLessThanOrEqual(0.5);
  expect(Math.abs(plus.y + plus.height / 2 - (box.y + box.height / 2)), "the plus is level with the field").toBeLessThanOrEqual(1);
  // The plus is the field's label: a click on it is a click into the field.
  await steps.locator(".app-ws-step-plus").click();
  await expect(field).toBeFocused();
});

/** Typing pauses save the notes: each save is answered with the notes it
 *  sent, so a slow run stays on the page. */
const answerNotesSaves = (page: Page) => mockApi(page, "PUT", "/api/jobs/303/pursuit", (route) => route.fulfill({
  json: { pursuit: { ...appliedPursuit, job_id: 303, notes: route.request().postDataJSON().notes } },
}));

test("the notes' headings step down in size from the first level to the third, all above the text", async ({ page }) => {
  await answerNotesSaves(page);
  const { panel } = await openWorkspace(page);
  const notes = panel.getByRole("textbox", { name: msg("applications-notes-label") });
  await notes.click();
  await page.keyboard.type("# One");
  await page.keyboard.press("Enter");
  await page.keyboard.type("## Two");
  await page.keyboard.press("Enter");
  await page.keyboard.type("### Three");
  await page.keyboard.press("Enter");
  await page.keyboard.type("Plain words with `code` in them");
  const size = (selector: string) => notes.locator(selector).first().evaluate((el) => parseFloat(getComputedStyle(el).fontSize));
  const [h1, h2, h3, text, code] = [await size("h1"), await size("h2"), await size("h3"), await size("p"), await size("code")];
  expect(h1).toBeGreaterThan(h2);
  expect(h2).toBeGreaterThan(h3);
  expect(h3).toBeGreaterThan(text);
  // Inline code is set apart by its face, not its size alone.
  const face = await notes.locator("code").evaluate((el) => getComputedStyle(el).fontFamily);
  const textFace = await notes.locator("p").first().evaluate((el) => getComputedStyle(el).fontFamily);
  expect(face).not.toBe(textFace);
  expect(code).toBeLessThanOrEqual(text);
});

/* Selected words show a bar of styles over them, as in Google Docs and
   Notion: it stands clear of the words, its buttons keep the selection, and
   ⌘K over them links them while ⌘K anywhere else is still the palette. */
test("selected words show a bar over them that styles and links them, and ⌘K elsewhere is still the palette", async ({ page, isMobile }) => {
  test.skip(isMobile, "phones are not supported");
  const saves: string[] = [];
  await mockApi(page, "PUT", "/api/jobs/303/pursuit", (route) => {
    const { notes: written } = route.request().postDataJSON();
    saves.push(written);
    return route.fulfill({ json: { pursuit: { ...appliedPursuit, job_id: 303, notes: written } } });
  });
  const { panel } = await openWorkspace(page);
  const notes = panel.getByRole("textbox", { name: msg("applications-notes-label") });
  const bar = page.getByRole("toolbar", { name: msg("applications-notes-bar") });
  await notes.click();
  await page.keyboard.type("Ask Sam about the team");
  await expect(bar, "a caret alone selects nothing to style").toHaveCount(0);

  await notes.getByText("Ask Sam about the team").dblclick({ position: { x: 40, y: 8 } });
  await expect(bar).toBeVisible();
  await expect(bar).toBeInViewport();
  const word = await page.evaluate(() => getSelection()!.toString());
  expect(word).toBe("Sam");
  // Above the words, not over them.
  const words = (await page.evaluate(() => getSelection()!.getRangeAt(0).getBoundingClientRect().toJSON())) as DOMRect;
  const barBox = (await bar.boundingBox())!;
  expect(barBox.y + barBox.height).toBeLessThanOrEqual(words.y);

  await bar.getByRole("button", { name: msg("applications-notes-style-bold") }).click();
  await expect(bar.getByRole("button", { name: msg("applications-notes-style-bold") })).toHaveAttribute("aria-pressed", "true");
  expect(await page.evaluate(() => getSelection()!.toString()), "the words stay selected").toBe("Sam");
  await expect.poll(() => saves.at(-1)).toMatch(/^Ask \*\*Sam\*\* about the team/);

  const palette = page.getByRole("dialog", { name: "Command palette" });
  await page.keyboard.press("ControlOrMeta+k");
  const field = bar.getByRole("textbox", { name: msg("applications-notes-link-field") });
  await expect(field).toBeFocused();
  await expect(palette).toHaveCount(0);
  await field.fill("careers.example.com/team");
  await field.press("Enter");
  await expect(notes).toBeFocused();
  await expect.poll(() => saves.at(-1)).toMatch(/^Ask \[\*\*Sam\*\*\]\(https:\/\/careers\.example\.com\/team\) about the team/);

  // Escape lets go of the words; the role stays open.
  await page.keyboard.press("Escape");
  await expect(bar).toHaveCount(0);
  await expect(notes).toBeVisible();
  await expect(page).toHaveURL(/\/job\/303/);

  // With nothing selected, ⌘K is the palette's, from the page as anywhere.
  await page.keyboard.press("ControlOrMeta+k");
  await expect(palette).toBeVisible();
});

/* The guide promises that each mark it lists, typed at the start of a line,
   makes its block: every row is typed into the page and checked. */
test("each mark the formatting guide lists makes its block at the start of a line", async ({ page, isMobile }) => {
  test.skip(isMobile, "phones are not supported");
  await answerNotesSaves(page);
  const { panel } = await openWorkspace(page);
  await panel.getByRole("button", { name: msg("applications-notes-help") }).click();
  const guide = page.getByRole("dialog", { name: msg("applications-notes-help-title") });
  await expect(guide).toBeVisible();
  await expect(guide).toBeInViewport();
  const rows = await guide.locator("dl").first().locator(":scope > div").evaluateAll((divs) =>
    divs.map((row) => [row.querySelector("dt")!.textContent ?? "", row.querySelector("dd")!.textContent ?? ""] as const));
  const made: Record<string, string> = {
    [msg("applications-notes-block-heading", { level: 1 })]: "h1",
    [msg("applications-notes-block-heading", { level: 2 })]: "h2",
    [msg("applications-notes-block-heading", { level: 3 })]: "h3",
    [msg("applications-notes-block-bullets")]: "ul:not([data-type]) > li",
    [msg("applications-notes-block-numbers")]: "ol > li",
    [msg("applications-notes-block-checklist")]: "ul[data-type='taskList'] > li",
    [msg("applications-notes-block-quote")]: "blockquote",
    [msg("applications-notes-block-divider")]: "hr",
  };
  expect(rows.map(([name]) => name).sort()).toEqual(Object.keys(made).sort());
  await page.keyboard.press("Escape");
  await expect(guide).toHaveCount(0);

  const notes = panel.getByRole("textbox", { name: msg("applications-notes-label") });
  await notes.click();
  for (const [name, mark] of rows) {
    // Two Enters leave whatever block the last line made, for plain text.
    await page.keyboard.press("Enter");
    await page.keyboard.press("Enter");
    const words = `Made by ${mark}`;
    await page.keyboard.type(made[name] === "hr" ? mark : `${mark} ${words}`);
    const block = notes.locator(made[name]);
    if (made[name] === "hr") await expect(block, name).toHaveCount(1);
    else await expect(block.filter({ hasText: words }), name).toHaveCount(1);
  }
});

test("done steps fold under the open ones and read as done when opened", async ({ page }) => {
  const done = [
    stepFixture({ id: 31, text: "Call the recruiter", done_at: new Date(Date.now() - DAY).toISOString() }),
    stepFixture({ id: 32, text: "Tailor the CV", done_at: new Date(Date.now() - 3 * DAY).toISOString() }),
  ];
  const { panel } = await openWorkspace(page, { card: { next_action: "Email the recruiter", next_action_due: tomorrowNoon() }, done });
  const toggle = panel.getByRole("button", { name: msg("applications-ws-next-done-fold", { count: 2 }) });
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await expect(panel.getByText("Call the recruiter")).toHaveCount(0);
  await toggle.click();
  const words = panel.locator(".app-ws-done .app-ws-step-words");
  await expect(words).toHaveText(["Call the recruiter", "Tailor the CV"]);
  const open = panel.locator(".app-ws-step-list").first().locator(".app-ws-step-words").first();
  const look = async (el: Locator) => el.evaluate((node) => ({ line: getComputedStyle(node).textDecorationLine, color: getComputedStyle(node).color }));
  const doneLook = await look(words.first());
  const openLook = await look(open);
  expect(doneLook.line, "a done step is struck through").toContain("line-through");
  expect(openLook.line, "an open step is not").not.toContain("line-through");
  expect(doneLook.color, "a done step is in the quiet ink").not.toBe(openLook.color);
  // The done tick shows its check at rest; the open one is empty until pointed at.
  const tick = (step: string) => panel.getByRole("button", { name: msg("applications-upnext-done-label", { step }) });
  const check = (button: Locator) => button.evaluate((el) => getComputedStyle(el).color);
  expect(await check(tick("Call the recruiter"))).not.toBe("rgba(0, 0, 0, 0)");
  expect(await check(tick("Email the recruiter"))).toBe("rgba(0, 0, 0, 0)");
  // Under the pointer, a done tick keeps its ticked paint.
  const paint = (button: Locator) => button.evaluate((el) => {
    const style = getComputedStyle(el);
    return [style.backgroundColor, style.borderColor, style.color];
  });
  const atRest = await paint(tick("Call the recruiter"));
  await tick("Call the recruiter").hover();
  await page.evaluate(() => { for (const animation of document.getAnimations()) animation.finish(); });
  expect(await paint(tick("Call the recruiter"))).toEqual(atRest);
});

test("a / in the notes offers the blocks by name in reach of the pointer, and a picked checklist is saved as Markdown", async ({ page, isMobile }) => {
  test.skip(isMobile, "phones are not supported: there the keyboard covers the menu");
  await answerNotesSaves(page);
  const { panel } = await openWorkspace(page);
  const notes = panel.getByRole("textbox", { name: msg("applications-notes-label") });
  await notes.click();
  await page.keyboard.type("/");
  const menu = page.getByRole("listbox", { name: msg("applications-notes-blocks") });
  await expect(menu).toBeVisible();
  await expect(menu).toBeInViewport();
  await expect(menu.getByRole("option")).toHaveCount(9);
  // The role is a dialog over the page: the menu takes the pointer all the same.
  const saved = page.waitForRequest((request) => request.method() === "PUT" && request.url().endsWith("/api/jobs/303/pursuit"));
  await menu.getByRole("option", { name: new RegExp(`^${msg("applications-notes-block-checklist")}`) }).click();
  await expect(menu).toHaveCount(0);
  await page.keyboard.type("Ask about the team");
  const box = notes.getByRole("checkbox", { name: msg("applications-notes-check", { line: "Ask about the team", checked: "no" }) });
  await expect(box).toBeVisible();
  // The box stands on its line's first line, not above it.
  const line = (await notes.getByText("Ask about the team", { exact: true }).boundingBox())!;
  const tick = (await box.boundingBox())!;
  expect(tick.x + tick.width, "the box sits before its words").toBeLessThanOrEqual(line.x);
  expect(Math.abs(tick.y + tick.height / 2 - (line.y + line.height / 2)), "on the same line").toBeLessThan(line.height / 2);
  // Markdown's own marks make a block too.
  await page.keyboard.press("Enter");
  await page.keyboard.press("Enter");
  await page.keyboard.type("## Questions");
  await expect(notes.getByRole("heading", { level: 2, name: "Questions" })).toBeVisible();
  expect(JSON.parse((await saved).postData() ?? "{}").notes).toMatch(/^- \[ \] Ask about the team/);
});

test("the activity shows under the rows, and a month's divider holds under the tabs while its month passes", async ({ page }) => {
  const now = Date.now();
  const items = Array.from({ length: 60 }, (_, n) => ({
    kind: "comment", id: 2000 + n, created_at: new Date(now - n * DAY).toISOString(), actor: "user", source: "app",
    body: `Note ${n}: what the recruiter said, and what to send before the next round.`, edited_at: null,
  }));
  const { panel, scroll } = await openWorkspace(page, { items, size: { width: 1440, height: 900 } });
  const feed = panel.getByRole("region", { name: msg("applications-feed-title") });
  // One stream: no switch between kinds of entry.
  await expect(feed.locator("button[aria-pressed]")).toHaveCount(0);
  await expect(feed.getByRole("textbox", { name: msg("applications-comment-label") })).toBeVisible();

  const first = feed.locator(".app-feed-month").first();
  const divider = first.locator(".app-feed-divider");
  // Scroll until the first month's entries pass under the tabs.
  const reach = await first.evaluate((el) => el.getBoundingClientRect().top + el.getBoundingClientRect().height / 2);
  const top = (await scroll.boundingBox())!.y;
  await scrollPosting(scroll, await scroll.evaluate((el) => el.scrollTop) + reach - top);
  const tabs = (await panel.locator(".jd-tabs").boundingBox())!;
  const held = (await divider.boundingBox())!;
  expect(held.y, "under the tabs, not under the bar").toBeCloseTo(tabs.y + tabs.height, 0);
  await expect(divider).toBeInViewport();
});

test("a role in the pipeline opened from the Radar reads on its posting tab, and Back names the Radar", async ({ page }) => {
  await mockGet(page, "/api/jobs/101", (route) => route.fulfill({ json: { ...jobFixture, is_favorite: true, pursuit: appliedPursuit } }));
  await mockGet(page, "/api/applications/101", (route) => route.fulfill({ json: applicationDetailFixture({
    application: applicationCardFixture({ pursuit_id: 10, stage: "applied", stage_since: new Date(Date.now() - 2 * DAY).toISOString() }),
  }) }));
  await page.goto("/");
  await page.getByText("Staff Product Manager, API").click();
  const panel = detail(page);
  await expect(panel.getByRole("tab", { name: msg("role-job-detail-tab-posting") })).toHaveAttribute("aria-selected", "true");
  await expect(page).not.toHaveURL(/tab=/);
  await expect(panel.getByRole("button", { name: /in the list/i }), "the posting has no stepping").toHaveCount(0);
  const back = panel.getByRole("button", { name: msg("role-job-detail-back-to", { view: msg("shell-nav-radar") }) });
  await expect(back).toHaveText(msg("shell-nav-radar"));
  await back.click();
  await expect(panel).toHaveCount(0);
  await expect(page).toHaveURL(/\/$/);
});

/* Opened from a list, a posting stays one posting: nothing in the bar steps
   to the rows around it, J and K do nothing on it, and Back returns to the
   list. */
test("a posting opened from the board has no way to step to another row, and Back returns to the board", async ({ page }) => {
  await mockGet(page, "/api/jobs?**", (route) => route.fulfill({ json: twoJobList }));
  await page.goto("/");
  await page.getByText(jobFixture.title).click();
  const panel = detail(page);
  await expect(page).toHaveURL(/\/company\/[^/]+\/job\/101$/);
  await expect(panel.getByRole("heading", { level: 1, name: jobFixture.title })).toBeVisible();
  await expect(panel.getByRole("group", { name: /place in the list/i }), "no pager in the bar").toHaveCount(0);
  await expect(panel.getByRole("button", { name: /(next|previous) in the list/i })).toHaveCount(0);
  await expect(panel.locator(".jd-pager")).toHaveCount(0);

  await page.keyboard.press("j");
  await page.keyboard.press("k");
  await expect(page, "J and K stay on this posting").toHaveURL(/\/job\/101$/);
  await expect(panel.getByRole("heading", { level: 1, name: jobFixture.title })).toBeVisible();

  await panel.getByRole("button", { name: msg("role-job-detail-back-2") }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(panel).toHaveCount(0);
});

/* The read ends on the way on: under the employer's text, a suggestion to
   apply. Following it saves the role, then shows the pipeline list in a new
   tab once the save has landed, so the list it loads holds the role. */
const APPLY = msg("role-job-detail-apply-title");

/** Serves the new tab a stand-in for the pipeline list, so the tab's own app
 *  never boots, and calls `seen` when the tab asks for it. */
async function standInList(page: Page, seen: () => void = () => {}) {
  await page.context().route("**/pipeline/list", (route) => {
    seen();
    return route.fulfill({ contentType: "text/html", body: "<!doctype html><title>list</title>" });
  });
}

test("a posting ends on applying: the link saves the role, then opens the pipeline list in a new tab", async ({ page }) => {
  const order: string[] = [];
  await mockApi(page, "PUT", "/api/jobs/101/favorite", async (route) => {
    // Slower than a tab opening, so a tab sent to the list at the click fails.
    await new Promise((settle) => setTimeout(settle, 400));
    order.push("saved");
    await route.fulfill({ json: { job_id: 101, is_favorite: true } });
  });
  await page.goto("/company/openai/job/101");
  const panel = detail(page);
  const end = panel.locator(".jd-end");
  const onward = end.getByRole("link", { name: new RegExp(APPLY) });
  await expect(onward).toContainText(msg("role-job-detail-apply-kicker"));
  await expect(onward).toContainText(msg("role-job-detail-apply-meta", { choice: "no" }));
  const text = (await panel.locator(".jd-main > .jd-sections, .jd-main > .jd, .jd-main > .jd-empty").last().boundingBox())!;
  expect((await end.boundingBox())!.y, "after the employer's text").toBeGreaterThan(text.y + text.height);

  await standInList(page, () => order.push("list"));
  const popupOpened = page.waitForEvent("popup");
  await onward.click();
  const tab = await popupOpened;
  await tab.waitForURL(/\/pipeline\/list$/);
  expect(order, "the list loads only once the save landed").toEqual(["saved", "list"]);
  expect(await tab.evaluate(() => window.opener), "the new tab has no hold on this one").toBeNull();
  await expect(page, "the posting stays open here").toHaveURL(/\/job\/101$/);
  await expect(panel.getByRole("button", { name: msg("jobs-save") }), "the role is saved").toHaveCount(0);
  await expect(onward).toContainText(msg("role-job-detail-apply-meta", { choice: "yes" }));
  await tab.close();
});

test("a failed save keeps the person on the posting: the new tab closes and the failure is said", async ({ page }) => {
  await mockApi(page, "PUT", "/api/jobs/101/favorite", (route) => route.fulfill({ status: 500, json: { detail: "unavailable" } }));
  await page.goto("/company/openai/job/101");
  const popupOpened = page.waitForEvent("popup");
  await detail(page).locator(".jd-end").getByRole("link", { name: new RegExp(APPLY) }).click();
  const tab = await popupOpened;
  await expect.poll(() => tab.isClosed(), { message: "the blank tab goes away" }).toBe(true);
  await expect(page.getByRole("status").filter({
    hasText: msg("role-job-detail-could-not-unsave-this-role", { choice: "yes" }),
  })).toBeVisible();
});

test("a middle click on the onward link saves the role before the list opens, as a click does", async ({ page }) => {
  const order: string[] = [];
  await mockApi(page, "PUT", "/api/jobs/101/favorite", async (route) => {
    await new Promise((settle) => setTimeout(settle, 400));
    order.push("saved");
    await route.fulfill({ json: { job_id: 101, is_favorite: true } });
  });
  await page.goto("/company/openai/job/101");
  const panel = detail(page);
  const onward = panel.locator(".jd-end").getByRole("link", { name: new RegExp(APPLY) });
  await standInList(page, () => order.push("list"));
  const popupOpened = page.waitForEvent("popup");
  await onward.click({ button: "middle" });
  const tab = await popupOpened;
  await tab.waitForURL(/\/pipeline\/list$/);
  expect(order, "the list loads only once the save landed").toEqual(["saved", "list"]);
  await expect(page, "the posting stays open here").toHaveURL(/\/job\/101$/);
  await expect(onward).toContainText(msg("role-job-detail-apply-meta", { choice: "yes" }));
  await tab.close();
});

test("a saved role's link opens the list without writing again; an applied role ends on nothing", async ({ page }) => {
  let writes = 0;
  await mockApi(page, "PUT", "/api/jobs/101/favorite", (route) => {
    writes += 1;
    return route.fulfill({ json: { job_id: 101, is_favorite: true } });
  });
  let pursuit: typeof appliedPursuit | null = null;
  await mockGet(page, "/api/jobs/101", (route) => route.fulfill({ json: { ...jobFixture, is_favorite: true, pursuit } }));
  await page.goto("/company/openai/job/101");
  const panel = detail(page);
  const onward = panel.locator(".jd-end").getByRole("link", { name: new RegExp(APPLY) });
  await expect(onward).toContainText(msg("role-job-detail-apply-meta", { choice: "yes" }));
  await expect(onward).toHaveAttribute("href", "/pipeline/list");
  await expect(onward).toHaveAttribute("target", "_blank");
  const popupOpened = page.waitForEvent("popup");
  await standInList(page);
  await onward.click();
  const tab = await popupOpened;
  await tab.waitForURL(/\/pipeline\/list$/);
  expect(writes, "already saved: no second write").toBe(0);
  await tab.close();

  pursuit = appliedPursuit;
  await page.goto("/job/101");
  await expect(panel.locator(".jd-hero h1")).toHaveText(jobFixture.title);
  await expect(panel.locator(".jd-end"), "applied: nothing to suggest").toHaveCount(0);
});

/** The roles the posting `id` lists under More like this: just `to`. */
async function mockSimilarTo(page: Page, id: number, to: object) {
  await mockGet(page, `/api/jobs/${id}/similar**`, (route) => route.fulfill({ json: {
    scope: new URL(route.request().url()).searchParams.get("scope"),
    items: [{ ...to, score: 0.9 }],
  } }));
}

/* Following a link to another posting turns the posting inside a cover that
   stays open. While the next one loads the one on show stays, for the eye only;
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
  await mockSimilarTo(page, 101, jobFixture2);
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

  const waiting = panel.locator(".jd-waiting");
  await expect(waiting, "nothing is on its way").toHaveCount(0);
  // Clicked where it stands: a pointer would first scroll the row into view,
  // and move the place the first posting is read to.
  await panel.locator(".similar-row").first().dispatchEvent("click");
  await expect(page).toHaveURL(/\/job\/202$/);
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
   alone is drawn apart, the new posting rises in, and
   under reduced motion the posting changes with no motion at all. */
test("a link to another posting turns the reading area; reduced motion turns nothing", async ({ page, browserName }) => {
  test.skip(browserName !== "chromium", "the Docker WebKit is slow over its first turn, and the app gives it no second");
  await mockGet(page, "/api/jobs?**", (route) => route.fulfill({ json: twoJobList }));
  await mockSimilarTo(page, 101, jobFixture2);
  await mockSimilarTo(page, 202, jobFixture);
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

  const follow = () => panel.locator(".similar-row").first().click();
  await follow();
  await expect.poll(turning).toEqual({ way: "open", readingArea: true, names: ["cover-scroll"] });
  await expect(title, "the new posting is what comes in").toHaveText(jobFixture2.title);
  await finish();
  await expect.poll(turning).toEqual({ way: null, readingArea: false, names: [] });

  await follow();
  await expect.poll(turning).toEqual({ way: "open", readingArea: true, names: ["cover-scroll"] });
  await finish();
  await expect(title).toHaveText(jobFixture.title);
  await expect.poll(turning).toEqual({ way: null, readingArea: false, names: [] });

  await page.emulateMedia({ reducedMotion: "reduce" });
  await follow();
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

test("a posting opened by its link has no pager", async ({ page }) => {
  await page.goto("/company/openai/job/101");
  await expect(detail(page).getByRole("heading", { level: 1 })).toBeVisible();
  await expect(detail(page).getByRole("group", { name: /place in the list/i })).toHaveCount(0);
  await expect(detail(page).locator(".jd-pager")).toHaveCount(0);
});

/* More like this folds to its heading, for a column of the role's own facts.
   The choice is kept with the person's settings, and holds for the next
   posting opened. */
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
   reading it stays open, and none of that changes the choice the person keeps. */
test("More like this folds while the posting is read and opens again at the top", async ({ page }) => {
  const saved = await viewChoices(page);
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
  expect(saved).not.toHaveProperty("posting.similar-folded");
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

/* A posting that opened with no text reads it from the employer's site after
   the page is shown. Meanwhile the Description section says so under a
   running line, never "No description"; the text lands where the line stood. */
const NO_TEXT = { ...jobFixture, description_text: null, description_sections: [], description_readable: true };
const READ_TEXT = {
  description_text: "Shape the API platform with the teams that build on it.",
  description_sections: [{ key: "summary", title: "About the role", content: "Shape the API platform with the teams that build on it." }],
};

test("a posting that opened with no text reads it once, says so meanwhile, then shows it", async ({ page }) => {
  let release!: () => void;
  const answered = new Promise<void>((resolve) => { release = resolve; });
  let stored = false;
  const textReads = watchReads(page, "POST", "/api/jobs/101/description");
  await mockApi(page, "POST", "/api/jobs/101/description", async (route) => {
    await answered;
    stored = true;
    return route.fulfill({ json: { outcome: "read", ...READ_TEXT } });
  });
  await mockGet(page, "/api/jobs/101", (route) => route.fulfill({ json: stored
    ? { ...jobFixture, ...READ_TEXT, description_readable: false }
    : NO_TEXT }));
  await page.goto("/company/openai/job/101");

  const panel = detail(page);
  const reading = panel.getByRole("status").filter({ hasText: msg("role-job-description-reading", { company: "OpenAI" }) });
  await expect(reading).toBeVisible();
  await expect(reading.getByRole("progressbar", { name: msg("role-job-description-reading-progress") })).toBeVisible();
  await expect(panel.getByText(msg("role-job-description-no-description-captured"))).toHaveCount(0);

  release();
  await expect(panel.getByRole("heading", { name: "About the role" })).toBeVisible();
  await expect(panel.getByText(READ_TEXT.description_text)).toBeVisible();
  await expect(reading).toHaveCount(0);
  // The region that said "reading" says the text came, out of sight.
  await expect(panel.getByRole("status").filter({ hasText: msg("role-job-description-arrived", { company: "OpenAI" }) })).toHaveCount(1);
  expect(textReads.started).toBe(1);
});

test("a slow site is said with the posting; a failed read offers Try again, which asks again", async ({ page }) => {
  await page.clock.install();
  const asked: string[] = [];
  let answer: "hold" | "failed" | "read" = "hold";
  await mockApi(page, "POST", "/api/jobs/101/description**", async (route) => {
    asked.push(new URL(route.request().url()).search);
    while (answer === "hold") await new Promise((resolve) => setTimeout(resolve, 50));
    return route.fulfill({ json: answer === "read" ? { outcome: "read", ...READ_TEXT } : { outcome: "failed", description_text: null, description_sections: [] } });
  });
  await mockGet(page, "/api/jobs/101", (route) => route.fulfill({ json: answer === "read"
    ? { ...jobFixture, ...READ_TEXT, description_readable: false }
    : NO_TEXT }));
  await page.goto("/company/openai/job/101");

  const panel = detail(page);
  const slow = panel.getByRole("status").filter({ hasText: msg("role-job-description-reading-slow", { company: "OpenAI" }) });
  const failed = panel.getByRole("status").filter({ hasText: msg("role-job-description-read-failed", { company: "OpenAI" }) });
  const posting = panel.getByRole("link", { name: msg("role-job-description-open-posting", { company: "OpenAI" }) });
  await expect(panel.getByRole("status").filter({ hasText: msg("role-job-description-reading", { company: "OpenAI" }) })).toBeVisible();
  await expect(posting).toHaveCount(0);

  await page.clock.runFor(7_000);
  await expect(slow).toBeVisible();
  await expect(posting).toHaveAttribute("href", jobFixture.url);
  await expect(posting).toHaveAttribute("target", "_blank");

  answer = "failed";
  await expect(failed).toBeVisible();
  await expect(failed.getByRole("progressbar")).toHaveCount(0);
  await expect(posting).toBeVisible();

  answer = "read";
  await panel.getByRole("button", { name: msg("common-try-again") }).click();
  await expect(panel.getByText(READ_TEXT.description_text)).toBeVisible();
  expect(asked).toEqual(["", "?retry=true"]);
});

test("a posting nothing can read says it has no description and asks for none", async ({ page }) => {
  const textReads = watchReads(page, "POST", "/api/jobs/101/description");
  await mockGet(page, "/api/jobs/101", (route) => route.fulfill({ json: { ...NO_TEXT, description_readable: false } }));
  await page.goto("/company/openai/job/101");

  const panel = detail(page);
  await expect(panel.getByText(msg("role-job-description-no-description-captured"))).toBeVisible();
  await page.waitForLoadState("networkidle");
  await expect(panel.getByRole("progressbar")).toHaveCount(0);
  expect(textReads.started).toBe(0);
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
   tabs through every control of a page they cannot see to reach "Apply", and gets
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
  await expect(dialog.getByRole("link", { name: "Apply", exact: true })).toBeVisible();
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
