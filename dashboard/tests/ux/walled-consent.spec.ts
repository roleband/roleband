/* Walled companies follow only with the user's consent.

   A company whose source limits automated collection — robots.txt disallows
   the route RoleBand requests — is followed through its own dialog, and a
   follow from before consent existed is kept but not scanned until the user
   answers. DeepMind is added to the shared register fixture here, followed and
   unconsented, the state a real install is in after the upgrade. */

import { expect, test } from "./fixtures";
import { companyDiscovery, installSettingsRoutes } from "./settingsHarness";

const deepmind = {
  slug: "google-deepmind", display: "Google DeepMind", careers_url: "https://deepmind.google/careers",
  sectors: ["ai"], aliases: [], connector_state: "family" as const,
  parked_reason: null, selectable: true, tracked: true, enabled: true,
  visible: true, builtin: false, curated: false, directory: false, wall: "robots" as const, consented: false, status: "active",
};

test.beforeEach(async ({ page }) => {
  await installSettingsRoutes(page);
  await page.route("/api/companies/discovery", (route) =>
    route.fulfill({ json: { ...companyDiscovery, companies: [...companyDiscovery.companies, deepmind] } }));
});

test("a walled company waiting for consent is named, and Review records the words shown", async ({ page }) => {
  const writes: { follow: string[]; consents: { slug: string; text: string; locale:string }[] }[] = [];
  await page.route("/api/companies/selection", async (route) => {
    const body = route.request().postDataJSON();
    writes.push(body);
    await route.fulfill({
      json: {
        ...companyDiscovery,
        companies: [...companyDiscovery.companies, { ...deepmind, consented: true }],
      },
    });
  });
  await page.goto("/settings/companies");

  const strip = page.getByRole("region", { name: "Companies needing attention" });
  await expect(strip).toContainText("1 followed company waits for your consent");
  await expect(page.getByRole("region", { name: "AI", exact: true }).getByText("Needs consent")).toBeVisible();

  await strip.getByRole("button", { name: "Review", exact: true }).click();
  const ask = page.getByRole("dialog", { name: "Keep following Google DeepMind?" });
  // The consent wording, spelled out: it is the text a user agrees to and the
  // text counsel reads, so a change to it must be deliberate enough to change
  // this line too.
  await expect(ask.locator("p")).toHaveText([
    "Its careers site changed how it can be read. Until you answer, it isn't scanned.",
    "Its careers site limits automated collection.",
    "By following, you choose to collect Google DeepMind's public postings. Unfollow at any time to stop.",
  ]);
  // The safe answer holds focus: Enter on the fresh dialog consents to nothing.
  await expect(ask.getByRole("button", { name: "Not now" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(ask).toBeHidden();
  expect(writes).toEqual([]);

  await strip.getByRole("button", { name: "Review", exact: true }).click();
  const heading = await ask.getByRole("heading").innerText();
  const paragraphs = await ask.locator("p").allInnerTexts();
  const shown = [heading, ...paragraphs].join("\n\n");
  // "The words shown" must be ALL the words shown: nothing in the dialog may
  // sit outside the heading and paragraphs the consent records, beyond the
  // two answers themselves.
  const buttons = await ask.getByRole("button").allInnerTexts();
  const everything = (await ask.innerText()).replace(/\s+/g, " ").trim();
  expect(everything).toBe([heading, ...paragraphs, ...buttons].join(" ").replace(/\s+/g, " ").trim());
  await ask.getByRole("button", { name: "Keep following", exact: true }).click();

  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0].follow).toEqual(["google-deepmind"]);
  expect(writes[0].consents).toEqual([{ slug: "google-deepmind", text: shown, locale: "en", scan_on_schedule: true }]);
  await expect(strip).toBeHidden();
});

/* Consent is asked once per company. The backend keeps `consented` true after an
   unfollow and after the register changes; given that, following again writes
   the follow with no dialog and no new consent. The unconsented case is the
   negative control: the same click asks. */
async function followUnfollowedDeepmind(page: import("@playwright/test").Page, consented: boolean) {
  const unfollowed = { ...deepmind, enabled: false, consented };
  await page.route("/api/companies/discovery", (route) =>
    route.fulfill({ json: { ...companyDiscovery, companies: [...companyDiscovery.companies, unfollowed] } }));
  const writes: { follow: string[]; consents?: unknown[] }[] = [];
  await page.route("/api/companies/selection", async (route) => {
    writes.push(route.request().postDataJSON());
    await route.fulfill({
      json: { ...companyDiscovery, companies: [...companyDiscovery.companies, { ...unfollowed, enabled: true, consented: true }] },
    });
  });
  await page.goto("/settings/companies");
  await page.getByRole("region", { name: "AI", exact: true })
    .getByRole("checkbox", { name: "Google DeepMind", exact: true }).click();
  return { writes, ask: page.getByRole("dialog", { name: "Follow Google DeepMind?" }) };
}

test("following a company again after unfollowing it never asks a second time", async ({ page }) => {
  const { writes, ask } = await followUnfollowedDeepmind(page, true);
  await expect.poll(() => writes.length).toBe(1);
  await expect(ask).toHaveCount(0);
  expect(writes[0].follow).toEqual(["google-deepmind"]);
  expect(writes[0].consents ?? []).toEqual([]);
});

test("following a walled company the user never answered for still asks", async ({ page }) => {
  const { writes, ask } = await followUnfollowedDeepmind(page, false);
  await expect(ask).toBeVisible();
  expect(writes).toEqual([]);
});

test("a Spanish confirmation submits its displayed wording and language together",async({page})=>{
  await page.addInitScript(()=>localStorage.setItem("roleband.locale",JSON.stringify({language:"es",region:"es-ES"})));
  await page.route("/api/settings/locale",route=>route.fulfill({json:{language:"es",region:"es-ES"}}));
  const writes: {consents:{slug:string;text:string;locale:string}[]}[]=[];
  await page.route("/api/companies/selection",async route=>{
    writes.push(route.request().postDataJSON());
    await route.fulfill({json:{...companyDiscovery,companies:[...companyDiscovery.companies,{...deepmind,consented:true}]}});
  });
  await page.goto("/settings/companies");
  await expect(page.locator("html")).toHaveAttribute("lang","es");
  // The stable attention surface holds the one Review action in any language.
  await page.locator(".ledger-attention").getByRole("button").click();
  const ask=page.getByRole("dialog");
  const heading=await ask.getByRole("heading").innerText();
  expect(heading).toContain("Google DeepMind");
  expect(heading).not.toBe("Keep following Google DeepMind?");
  const shown=[heading,...await ask.locator("p").allInnerTexts()].join("\n\n");
  expect(shown).toContain("Its careers site limits automated collection.");
  await ask.getByRole("button",{name:"Seguir siguiendo",exact:true}).click();
  await expect.poll(()=>writes.length).toBe(1);
  expect(writes[0].consents).toEqual([{ slug: "google-deepmind", text: shown, locale: "es", scan_on_schedule: true }]);
});

/* Forty followed companies waiting at once: one question, and its choose step
   keeps the list inside the dialog, so the answers stay on screen at a
   laptop's height and on a phone. */
for (const viewport of [{ width: 1280, height: 720 }, { width: 390, height: 760 }]) {
  test(`forty waiting companies are one question whose list scrolls inside the dialog (${viewport.width}px)`, async ({ page }) => {
    await page.setViewportSize(viewport);
    const waiting = Array.from({ length: 40 }, (_, index) => ({
      ...deepmind,
      slug: `waiting-${String(index).padStart(2, "0")}`,
      display: `Waiting ${String(index).padStart(2, "0")}`,
      careers_url: `https://example.com/${index}/careers`,
      wall: null,
      directed: true,
      scan_on_schedule: false,
    }));
    await page.route("/api/companies/discovery", (route) =>
      route.fulfill({ json: { ...companyDiscovery, companies: [...companyDiscovery.companies, ...waiting] } }));
    const writes: { follow: string[]; unfollow: string[]; consents: { slug: string }[] }[] = [];
    await page.route("/api/companies/selection", async (route) => {
      writes.push(route.request().postDataJSON());
      await route.fulfill({ json: companyDiscovery });
    });
    await page.goto("/settings/companies");

    const strip = page.getByRole("region", { name: "Companies needing attention" });
    await expect(strip).toContainText("40 followed companies wait for your consent");
    await expect(strip.getByRole("button")).toHaveCount(1);
    await strip.getByRole("button", { name: "Review", exact: true }).click();

    const ask = page.getByRole("dialog", { name: "Keep following Waiting 00, Waiting 01 and 38 more?" });
    await expect(ask.getByRole("button", { name: "Not now" })).toBeFocused();
    await ask.getByRole("button", { name: "Let me choose" }).click();

    const choose = page.getByRole("dialog", { name: "Which companies to unfollow?" });
    const list = choose.getByRole("group", { name: "Companies to unfollow" });
    await expect(list.getByRole("checkbox")).toHaveCount(40);
    // The list scrolls, not the page: every row is there, the frame is shorter.
    const frame = await list.evaluate((node) => ({ scroll: node.scrollHeight, client: node.clientHeight }));
    expect(frame.scroll).toBeGreaterThan(frame.client);
    const answer = choose.getByRole("button", { name: "Keep following 40" });
    await expect(answer).toBeInViewport();
    await expect(choose.getByRole("button", { name: "Back" })).toBeFocused();

    await list.getByRole("checkbox", { name: "Waiting 39" }).click();
    await expect(choose.getByText("1 to unfollow")).toBeVisible();
    await choose.getByRole("button", { name: "Keep following 39" }).click();

    await expect.poll(() => writes.length).toBe(1);
    expect(writes[0].unfollow).toEqual(["waiting-39"]);
    expect(writes[0].follow).toHaveLength(39);
    expect(writes[0].consents.map((consent) => consent.slug)).toEqual(writes[0].follow);
    await expect(page.getByText("Following 39 companies. Stopped following 1 company.")).toBeVisible();
  });
}
