import { activate } from "../../copy/activate";
import { wordsLanguage } from "../../copy/runtime";
import { describe, expect, it } from "vitest";
import type { CompanyDiscoveryCompany } from "../../api";
import { SITE_WALL_SENTENCE, agreementCopy, agreementText, awaitingConsent, consentsFor, followCopy, shownSentences, wallSentence } from "./followCopy";
import type { SectorGroup } from "./companiesModel";

/* The follow confirmations' words are the consent a walled company is
 * collected under: what is recorded must be what was shown. */

const company = (over: Partial<CompanyDiscoveryCompany>): CompanyDiscoveryCompany => ({
  slug: "acme", display: "Acme", careers_url: null, sectors: ["ai"], aliases: [],
  connector_state: "ready", parked_reason: null, selectable: true,
  tracked: false, enabled: false, visible: true, builtin: false, curated: false, directory: false,
  directed: false, scan_on_schedule: false, wall: null, consented: false, status: null, ...over,
});

const deepmind = company({ slug: "deepmind", display: "DeepMind", wall: "robots" });
const stripe = company({ slug: "stripe", display: "Stripe" });
const none = { volume: null, seconds: null } as const;
const LEDE = "Your radar starts with a curated list of well-known companies. More companies bring more roles, and each scan takes longer.";
const SOME_WALLED = "Some of these companies limit automated collection on their careers sites.";
const SOME_DIRECTED = "Some of these companies' careers sites are scanned only at your direction.";
const BY_FOLLOWING = "By following them, you choose to collect their public postings.";
const UNFOLLOW_NOTE = "Unfollow any time in Settings › Followed companies.";

describe("follow confirmations and the consent they record", () => {
  it("records exactly the words shown, once per walled company it starts to collect", () => {
    const pending = { kind: "include" as const, companies: [deepmind, stripe], estimate: none };
    const copy = followCopy(pending);
    expect(copy).toEqual({
      title: "Follow the whole list?",
      paragraphs: [LEDE],
      consent: { facts: [{ site: "walled", text: SOME_WALLED }], choice: BY_FOLLOWING },
      note: UNFOLLOW_NOTE,
      safe: "Keep curated list",
      act: "Follow all 2",
    });
    // The stored text is every sentence shown, in the order shown.
    const text = ["Follow the whole list?", LEDE, SOME_WALLED, BY_FOLLOWING, UNFOLLOW_NOTE].join("\n\n");
    expect(agreementText(copy)).toBe(text);
    expect(consentsFor(pending)).toEqual([{ slug: "deepmind", locale: "en", text, scan_on_schedule: true }]);
  });

  it("a sector's Follow all shows and records the same consent sentence as the whole list", () => {
    const group = { slug: "ai", display: "AI", members: [deepmind, stripe], connectable: [deepmind, stripe],
      bulk: [deepmind, stripe], trackedCount: 0 } as unknown as SectorGroup;
    const pending = { kind: "sector" as const, group, companies: [deepmind, stripe], estimate: none };
    const copy = followCopy(pending);
    expect(copy.consent).toEqual({ facts: [{ site: "walled", text: SOME_WALLED }], choice: BY_FOLLOWING });
    expect(consentsFor(pending)).toEqual([
      { slug: "deepmind", locale: "en", text: agreementText(copy), scan_on_schedule: true },
    ]);
    const clear = { ...pending, companies: [stripe], group: { ...group, bulk: [stripe] } };
    expect(followCopy(clear).consent).toBeUndefined();
    expect(shownSentences(followCopy(clear)).join(" ")).not.toMatch(/automated collection|collect/);
  });

  it("names no wall and records nothing when the set has no unconsented walled company", () => {
    const consented = { ...deepmind, consented: true };
    const pending = { kind: "include" as const, companies: [consented, stripe], estimate: none };
    expect(shownSentences(followCopy(pending))).toEqual([LEDE, UNFOLLOW_NOTE]);
    expect(consentsFor(pending)).toEqual([]);
    expect(awaitingConsent([consented, stripe])).toEqual([]);
  });

  it("states the site's reason, names no company, and says nothing when nothing walls it", () => {
    // Every wall is the SITE's. A company the product itself leaves
    // to the user is not walled at all: it never reaches a dialog, so there is
    // no sentence to write for it.
    for (const site of [deepmind, { ...deepmind, wall: "bot_wall" as const }]) {
      expect(wallSentence(site)).toBe(SITE_WALL_SENTENCE);
    }
    expect(SITE_WALL_SENTENCE).not.toMatch(/DeepMind/);
    expect(wallSentence(stripe)).toBeNull();
  });

  it("an individual walled follow shows the reason and what following means", () => {
    const copy = followCopy({ kind: "agree-follow", company: deepmind });
    expect(copy.title).toBe("Follow DeepMind?");
    expect(shownSentences(copy)).toEqual([
      SITE_WALL_SENTENCE,
      "By following, you choose to collect DeepMind's public postings. Unfollow at any time to stop.",
    ]);
    // One company's agreement stores the same words, in the same order, as
    // before its dialog split them into a fact and a choice.
    expect(agreementText(copy)).toBe([
      "Follow DeepMind?",
      SITE_WALL_SENTENCE,
      "By following, you choose to collect DeepMind's public postings. Unfollow at any time to stop.",
    ].join("\n\n"));
  });

  it("warns once about the walled companies in Follow the whole list, naming none of them", () => {
    const wise = company({ slug: "wise", display: "Wise", wall: "bot_wall" });
    const pending = { kind: "include" as const, companies: [deepmind, wise, stripe], estimate: none };
    const sentences = shownSentences(followCopy(pending));
    expect(sentences.filter((line) => line.includes("limit automated collection"))).toHaveLength(1);
    expect(sentences.join(" ")).not.toMatch(/DeepMind|Wise|\d/);
    // Both are consented to, in the words shown.
    expect(consentsFor(pending).map((entry) => entry.slug)).toEqual(["deepmind", "wise"]);
  });

  it("the list and the other companies is one question that names no number and no company, and consents for each walled one", () => {
    const wise = company({ slug: "wise", display: "Wise", wall: "bot_wall" });
    const pending = { kind: "everything" as const, companies: [deepmind, wise, stripe] };
    const copy = followCopy(pending);
    expect(copy).toEqual({
      title: "Follow the other companies too?",
      paragraphs: ["Your radar adds the other companies to the ones on the list.", "With more companies, scans take longer."],
      consent: {
        facts: [{ site: "walled", text: SOME_WALLED }],
        choice: "By picking this, you choose to collect their public postings.",
      },
      note: "Change it any time in Settings › Followed companies.",
      safe: "Cancel",
      act: "Follow them",
    });
    const text = agreementText(copy);
    expect(text).not.toMatch(/\d|DeepMind|Wise|Stripe/);
    expect(consentsFor(pending)).toEqual([
      { slug: "deepmind", locale: "en", text, scan_on_schedule: true },
      { slug: "wise", locale: "en", text, scan_on_schedule: true },
    ]);
  });

  it("the list and the other companies without a walled company to follow says nothing of walls and consents to nothing", () => {
    for (const companies of [[stripe], [{ ...deepmind, consented: true }, stripe], []]) {
      const pending = { kind: "everything" as const, companies };
      expect(shownSentences(followCopy(pending)).join(" ")).not.toMatch(/limit|collect/);
      expect(consentsFor(pending)).toEqual([]);
    }
  });

  it("an individual follow consents; an unfollow and a bulk unfollow consent to nothing", () => {
    const follow = { kind: "agree-follow" as const, company: deepmind };
    expect(followCopy(follow)).toMatchObject({ title: "Follow DeepMind?", safe: "Cancel", act: "Follow DeepMind" });
    expect(consentsFor(follow).map((entry) => entry.slug)).toEqual(["deepmind"]);
    expect(consentsFor({ kind: "walled-unfollow", company: deepmind })).toEqual([]);
    expect(consentsFor({ kind: "exclude", companies: [deepmind] })).toEqual([]);
  });
});

it("records the rendered consent snapshot even after the locale changes", async () => {
  await activate("es");
  const pending = { kind: "agree-follow" as const, company: deepmind };
  const shown = { copy: followCopy(pending), locale: wordsLanguage(), keepScanning: true };
  await activate("en");
  expect(consentsFor(pending, shown)).toEqual([{ slug: "deepmind", locale: "es", text: agreementText(shown.copy), scan_on_schedule: true }]);
});

describe("a company scanned only at the user's direction", () => {
  const nvidia = company({ slug: "nvidia", display: "NVIDIA", directed: true });
  const DIRECTED = "Its careers site is scanned only at your direction.";

  it("is followed through its own dialog: one press follows and scans, with Keep scanning ticked", () => {
    const copy = followCopy({ kind: "agree-follow", company: nvidia });
    expect(copy).toEqual({
      title: "Follow NVIDIA?",
      paragraphs: [],
      consent: {
        facts: [{ site: "directed", text: DIRECTED }],
        choice: "By following, you choose to collect NVIDIA's public postings. Unfollow at any time to stop.",
      },
      safe: "Cancel",
      act: "Follow and scan",
      keepScanning: "Keep scanning this company",
    });
    expect(awaitingConsent([nvidia])).toEqual([nvidia]);
    expect(awaitingConsent([{ ...nvidia, consented: true }])).toEqual([]);
  });

  it("records the checkbox as the agreement's choice, either way", () => {
    const pending = { kind: "agree-follow" as const, company: nvidia };
    const copy = followCopy(pending);
    const text = agreementText(copy);
    for (const keepScanning of [true, false]) {
      expect(consentsFor(pending, { copy, locale: "en", keepScanning })).toEqual([
        { slug: "nvidia", locale: "en", text, scan_on_schedule: keepScanning },
      ]);
    }
  });

  it("a walled company has no checkbox and is always on the schedule once agreed", () => {
    const pending = { kind: "agree-follow" as const, company: deepmind };
    const copy = followCopy(pending);
    expect(copy.keepScanning).toBeUndefined();
    expect(consentsFor(pending, { copy, locale: "en", keepScanning: false })[0].scan_on_schedule).toBe(true);
  });

  it("a company both walled and directed states both and keeps the checkbox", () => {
    const both = agreementCopy({ display: "NVIDIA", walled: true, directed: true });
    expect(both.consent?.facts).toEqual([{ site: "walled", text: SITE_WALL_SENTENCE }, { site: "directed", text: DIRECTED }]);
    expect(both.act).toBe("Follow and scan");
    expect(both.keepScanning).toBeDefined();
  });

  it("a bulk follow names directed companies in one line, with one checkbox for all of them", () => {
    const adobe = company({ slug: "adobe", display: "Adobe", directed: true });
    const group = { slug: "ai", display: "AI", bulk: [nvidia, adobe, deepmind, stripe] } as unknown as SectorGroup;
    const pending = { kind: "sector" as const, group, companies: [nvidia, adobe, deepmind, stripe], estimate: none };
    const copy = followCopy(pending);
    // Walled and directed: each fact once, and what following means once
    // under both, never repeated per fact.
    expect(copy.consent).toEqual({
      facts: [{ site: "walled", text: SOME_WALLED }, { site: "directed", text: SOME_DIRECTED }],
      choice: BY_FOLLOWING,
    });
    expect(shownSentences(copy).filter((line) => line.includes("choose to collect"))).toEqual([BY_FOLLOWING]);
    expect(shownSentences(copy).join(" ")).not.toMatch(/NVIDIA|Adobe/);
    expect(copy.keepScanning).toBe("Keep scanning these companies");
    const agreements = consentsFor(pending, { copy, locale: "en", keepScanning: false });
    expect(agreements.map(({ slug, scan_on_schedule }) => [slug, scan_on_schedule])).toEqual([
      ["nvidia", false], ["adobe", false], ["deepmind", true],
    ]);
    // Without a directed company left to agree to, no line and no checkbox.
    const agreed = followCopy({ ...pending, companies: [{ ...nvidia, consented: true }, stripe] });
    expect(agreed.keepScanning).toBeUndefined();
    expect(shownSentences(agreed).join(" ")).not.toContain("your direction");
    expect(agreed.consent).toBeUndefined();
  });
});
