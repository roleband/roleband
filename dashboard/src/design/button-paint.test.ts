import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { SRC, buttonRepaints, classesOnButtons, compareNames, components, stylesheets } from "./recipes";

/* A screen places a Button; it does not repaint or resize it.
 *
 * `Button` and `RouterLink` pass any `className` through. A class a module
 * outside `src/ui/` hands them is in scope when a rule with that class in its
 * subject declares paint or size: colour, ground, border or corner, shadow,
 * type size, weight, leading or tracking, height or padding. Placement and
 * reveal stay open and are never listed: margins, width, flex and grid
 * placement, position, `opacity` and `visibility`, the same line
 * `primitive-states.test.ts` draws for a primitive's states.
 *
 * Every class in scope is named in `button-paint-names.json`, exact match both
 * ways: a class that is not on the list fails, and a listed class that no
 * longer repaints a button fails until its line is deleted. The list holds
 * names, never a count, because a count lets a new class in whenever an old
 * one leaves in the same change. Being on the list is an inventory entry, not
 * an endorsement.
 */

const LIST = "design/button-paint-names.json";

describe("a screen does not repaint or resize a Button", () => {
  const list: string[] = JSON.parse(readFileSync(join(SRC, LIST), "utf8"));
  const found = buttonRepaints(components(), stylesheets());
  const { added, stale } = compareNames(list, found);

  it("keeps its list sorted and unique, so a diff reads as a diff", () => {
    expect(list).toEqual([...new Set(list)].sort());
  });

  it("finds no new class that repaints or resizes a Button or RouterLink", () => {
    expect(
      added,
      `These classes, handed to <Button> or <RouterLink> outside src/ui/, set ` +
        `the button's paint or size:\n  ` +
        added.map((name) => `.${name}  (${found.get(name)!.join("; ")})`).join("\n  ") +
        `\nAdd a variant to ui/Button with its whole state set, or use an existing ` +
        `variant or modifier (docs/ui.md, "Button"). A class on a button may place ` +
        `it (margin, width, flex, grid, position) or reveal it (opacity, ` +
        `visibility). Neither is a reason to add the class to ${LIST}.`,
    ).toEqual([]);
  });

  it("drops a listed class once it no longer repaints a button", () => {
    expect(
      stale,
      `These entries in ${LIST} no longer repaint or resize a Button. Delete ` +
        `them in this change, so the slot cannot be filled again without ` +
        `notice:\n  ${stale.join("\n  ")}`,
    ).toEqual([]);
  });
});

describe("the button scan can see a repaint", () => {
  const screen = `
    export function Probe({ open }: { open: boolean }) {
      return (
        <div className="probe-row">
          <Button
            variant="link"
            onClick={() => open && go({ to: "x" })}
            className={\`probe-fold \${open ? "is-open" : ""}\`}
          >More</Button>
          <RouterLink to="/x" className="probe-place ui-btn-strong">Go</RouterLink>
          <ButtonGroup className="probe-group" />
        </div>
      );
    }`;

  it("reads the literal classes handed to Button and RouterLink, and no other tag", () => {
    expect(classesOnButtons(screen).sort()).toEqual(["is-open", "probe-fold", "probe-place", "ui-btn-strong"]);
  });

  it("reports a class that repaints, and leaves placement, reveal and ui- classes alone", () => {
    const sheet = `
      .probe-fold { padding: 0; color: var(--app-text-muted); }
      .probe-row .probe-place { margin-inline-start: auto; width: 100%; opacity: 0; }
      .probe-row:hover .probe-place { opacity: 1; }
      .probe-fold:not(.probe-place) svg { color: var(--app-action); }
      .ui-btn-strong { font-weight: 700; }`;
    const found = buttonRepaints(
      [["features/probe/Probe.tsx", screen]],
      [["features/probe/probe.css", sheet]],
    );
    expect([...found.keys()]).toEqual(["probe-fold"]);
    expect(found.get("probe-fold")).toEqual(["features/probe/probe.css:2 padding, color"]);
  });

  it("does not read a class handed to a Button inside src/ui/", () => {
    const found = buttonRepaints(
      [["ui/Probe.tsx", screen]],
      [["features/probe/probe.css", ".probe-fold { padding: 0; }"]],
    );
    expect(found.size).toBe(0);
  });
});
