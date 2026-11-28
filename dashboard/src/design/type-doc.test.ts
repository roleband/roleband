import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { rules } from "./cssRules";
import { SRC } from "./recipes";

/* The type table in docs/ui.md states the ramp `tokens.css` declares.
 *
 * The table is where a contributor picks a role, so a size it states and the
 * token does not set is a wrong choice made with confidence. Every role and
 * every size must agree, both ways.
 */

const DOC = readFileSync(join(SRC, "../../docs/ui.md"), "utf8");
const TOKENS = readFileSync(join(SRC, "design/tokens.css"), "utf8");

/** The `### Type` section's rows: `` | `role` | px | ``. */
function docRamp(markdown: string): Record<string, number> {
  const start = markdown.indexOf("\n### Type\n");
  if (start < 0) return {};
  const rest = markdown.slice(start + 1);
  const end = rest.slice(1).search(/\n#{1,3} /);
  const section = end < 0 ? rest : rest.slice(0, end + 1);
  return Object.fromEntries(
    [...section.matchAll(/^\| `([a-z-]+)` \| (\d+) \|/gm)].map((m) => [m[1], Number(m[2])]),
  );
}

/** Every `--app-type-<role>: <n>px` the sheet declares. */
function tokenRamp(css: string): Record<string, number> {
  const out: Record<string, number> = {};
  for (const rule of rules(css)) {
    for (const [prop, value] of rule.decls) {
      const role = prop.match(/^--app-type-([a-z-]+)$/)?.[1];
      const px = value.match(/^(\d+)px$/)?.[1];
      if (role && px) out[role] = Number(px);
    }
  }
  return out;
}

const sorted = (ramp: Record<string, number>) =>
  Object.entries(ramp).map(([role, px]) => `${role} ${px}px`).sort();

describe("docs/ui.md's type table", () => {
  it("states every role tokens.css declares, at the size it declares", () => {
    const doc = sorted(docRamp(DOC));
    const tokens = sorted(tokenRamp(TOKENS));
    const differ = [
      ...doc.filter((row) => !tokens.includes(row)).map((row) => `docs/ui.md says ${row}`),
      ...tokens.filter((row) => !doc.includes(row)).map((row) => `tokens.css sets ${row}`),
    ];
    expect(
      differ,
      "docs/ui.md (Type) and design/tokens.css disagree. The token is what " +
        `renders: correct the table, or change the ramp and the table together.\n  ${differ.join("\n  ")}`,
    ).toEqual([]);
  });
});

describe("the type table scan can see a disagreement", () => {
  const doc = "## Tokens\n\n### Type\n\n| Role | px |\n|---|---|\n| `title` | 16 | h3 |\n| `meta` | 13 | facts |\n\n### Geometry\n\n| `space` | 99 | not type |\n";

  it("reads only the Type section's rows", () => {
    expect(docRamp(doc)).toEqual({ title: 16, meta: 13 });
  });

  it("reads the ramp's px tokens and nothing else", () => {
    const css = ":root { --app-type-title: 15px; --app-type-meta: 13px; --app-type-whisper-track: 0.14em; }";
    expect(tokenRamp(css)).toEqual({ title: 15, meta: 13 });
    expect(sorted(docRamp(doc))).not.toEqual(sorted(tokenRamp(css)));
  });

  it("finds the whole ramp in the real files, so the comparison is about something", () => {
    expect(Object.keys(tokenRamp(TOKENS)).length).toBeGreaterThanOrEqual(15);
    expect(Object.keys(docRamp(DOC)).length).toBeGreaterThanOrEqual(15);
  });
});
