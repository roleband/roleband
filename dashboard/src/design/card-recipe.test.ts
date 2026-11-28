import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { SRC, compareNames, recipeCopies, stylesheets, writesCard, type Source } from "./recipes";

/* The card is written in three places.
 *
 * The card recipe is a 1px hairline, `--app-radius-lg` and a card inset
 * (`card-inset.test.ts` holds the inset's steps). Three sheets own it:
 * `ui/Card.css` (the `Card` component), `design/overlays.css` (`.panel`, the
 * card without `Card`'s heading) and `design/settings.css` (the setup walk's
 * card). A rule anywhere else that writes all three is a card of its own.
 *
 * Every such rule is named in `card-recipe-names.json` as `sheet :: selector`,
 * exact match both ways: a rule that is not on the list fails, and a listed
 * rule that no longer writes the recipe fails until its line is deleted, so a
 * move onto `Card` or `.panel` banks its win. The list holds names, never a
 * count, because a count lets a new copy in whenever an old one leaves in the
 * same change. Being on the list is an inventory entry, not an endorsement.
 */

const LIST = "design/card-recipe-names.json";
const OWNERS = new Set(["ui/Card.css", "design/overlays.css", "design/settings.css"]);

const cardCopies = (sheets: readonly Source[]) => recipeCopies(sheets, (rel) => OWNERS.has(rel), writesCard);

describe("the card recipe is written only by its owners", () => {
  const list: string[] = JSON.parse(readFileSync(join(SRC, LIST), "utf8"));
  const found = cardCopies(stylesheets());
  const { added, stale } = compareNames(list, found);

  it("keeps its list sorted and unique, so a diff reads as a diff", () => {
    expect(list).toEqual([...new Set(list)].sort());
  });

  it("finds no new card written outside ui/Card.css, overlays.css and settings.css", () => {
    expect(
      added,
      `These rules write the card recipe (1px hairline, --app-radius-lg, a card ` +
        `inset) outside the sheets that own it:\n  ` +
        added.map((name) => `${name}  (${found.get(name)!.join(", ")})`).join("\n  ") +
        `\nUse ui/Card, or the .panel class for a card without Card's heading ` +
        `(docs/ui.md, "The primitive tier"). Neither is a reason to add the rule ` +
        `to ${LIST}.`,
    ).toEqual([]);
  });

  it("drops a listed rule once it no longer writes the recipe", () => {
    expect(
      stale,
      `These entries in ${LIST} no longer match a rule that writes the card ` +
        `recipe. Delete them in this change, so the slot cannot be filled again ` +
        `without notice:\n  ${stale.join("\n  ")}`,
    ).toEqual([]);
  });
});

describe("the card scan can see a card", () => {
  const card = ".x { padding: var(--app-space-5); border: 1px solid var(--app-border); border-radius: var(--app-radius-lg); }";

  it("reports a card written in a screen sheet, under its selector", () => {
    const found = cardCopies([["features/probe/probe.css", card.replace(".x", ".probe-box, .probe-tile")]]);
    expect([...found.keys()]).toEqual([
      "features/probe/probe.css :: .probe-box",
      "features/probe/probe.css :: .probe-tile",
    ]);
  });

  it("reports a card nested inside another rule or a media query", () => {
    const nested = `.probe-screen { display: grid; @media (min-width: 900px) { .probe-box ${card.slice(3)} } }`;
    expect([...cardCopies([["features/probe/probe.css", nested]]).keys()]).toEqual([
      "features/probe/probe.css :: .probe-screen .probe-box",
    ]);
  });

  it("leaves the owners, a frame with no inset and a bar alone", () => {
    expect(cardCopies([["design/overlays.css", card]]).size).toBe(0);
    const frame = card.replace("var(--app-space-5)", "0");
    const bar = card.replace("var(--app-space-5)", "var(--app-space-2)");
    const tile = card.replace("var(--app-radius-lg)", "var(--app-radius-md)");
    expect(cardCopies([["features/probe/probe.css", `${frame} ${bar} ${tile}`]]).size).toBe(0);
  });
});
