import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { SRC, compareNames, recipeCopies, stylesheets, writesLabel, type Source } from "./recipes";

/* The small uppercase label is written by its owners.
 *
 * The label recipe is the whisper size, its weight and tracking, mono and
 * uppercase; every copy of it declares `text-transform: uppercase`, so that is
 * what the scan reads. Its owners:
 *   - everything under `ui/`, the primitive tier;
 *   - `design/surfaces.css`: `.eyebrow`, the label itself, and `.data-table th`;
 *   - `patterns/figure-table.css`: the figure table's column heads;
 *   - `design/dataviz.css`: `.kpi-l`, the label of the shared KPI tile, in the
 *     sheet that states the data vocabulary once for every screen.
 * `shell.css` is not an owner. Its two labels belong to the frame alone (the
 * rail brand's subtitle, on the rail's own palette, and the command palette's
 * section heads); no screen uses them, so they are inventory like any screen's.
 *
 * Every other rule that sets uppercase is named in `label-recipe-names.json`
 * as `sheet :: selector`, exact match both ways: a rule that is not on the list
 * fails, and a listed rule that no longer sets uppercase fails until its line
 * is deleted. The list holds names, never a count, because a count lets a new
 * copy in whenever an old one leaves in the same change. Being on the list is
 * an inventory entry, not an endorsement.
 */

const LIST = "design/label-recipe-names.json";
const OWNERS = new Set(["design/surfaces.css", "patterns/figure-table.css", "design/dataviz.css"]);
const owns = (rel: string) => rel.startsWith("ui/") || OWNERS.has(rel);

const labelCopies = (sheets: readonly Source[]) => recipeCopies(sheets, owns, writesLabel);

describe("the uppercase label is written only by its owners", () => {
  const list: string[] = JSON.parse(readFileSync(join(SRC, LIST), "utf8"));
  const found = labelCopies(stylesheets());
  const { added, stale } = compareNames(list, found);

  it("keeps its list sorted and unique, so a diff reads as a diff", () => {
    expect(list).toEqual([...new Set(list)].sort());
  });

  it("finds no new uppercase label written outside its owners", () => {
    expect(
      added,
      `These rules write the small uppercase label outside ui/, surfaces.css, ` +
        `figure-table.css and dataviz.css:\n  ` +
        added.map((name) => `${name}  (${found.get(name)!.join(", ")})`).join("\n  ") +
        `\nPut the .eyebrow class on the element instead (docs/ui.md, "The ` +
        `primitive tier"). A role that needs another ink adds a rule that sets ` +
        `only its colour. Neither is a reason to add the rule to ${LIST}.`,
    ).toEqual([]);
  });

  it("drops a listed rule once it no longer sets uppercase", () => {
    expect(
      stale,
      `These entries in ${LIST} no longer match a rule that sets uppercase. ` +
        `Delete them in this change, so the slot cannot be filled again without ` +
        `notice:\n  ${stale.join("\n  ")}`,
    ).toEqual([]);
  });
});

describe("the label scan can see a label", () => {
  const label =
    "{ color: var(--app-text-faint); font-family: var(--app-font-mono); " +
    "font-size: var(--app-type-whisper); text-transform: uppercase; }";

  it("reports a label written in a screen sheet and in shell.css", () => {
    const found = labelCopies([
      ["features/probe/probe.css", `.probe-kicker ${label}`],
      ["shell.css", `.probe-rail-label ${label}`],
    ]);
    expect([...found.keys()]).toEqual([
      "features/probe/probe.css :: .probe-kicker",
      "shell.css :: .probe-rail-label",
    ]);
  });

  it("leaves the owners alone, and a rule that only sets the ink", () => {
    for (const owner of ["ui/Probe.css", "design/surfaces.css", "patterns/figure-table.css", "design/dataviz.css"]) {
      expect(labelCopies([[owner, `.probe-kicker ${label}`]]).size, owner).toBe(0);
    }
    const ink = ".probe-kicker.eyebrow { color: var(--app-text-muted); }";
    expect(labelCopies([["features/probe/probe.css", ink]]).size).toBe(0);
  });
});
