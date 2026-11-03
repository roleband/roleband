import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/* Every figure the two toolbars print goes through the region formatter, so
 * counts above 999 stay grouped ("1,200 of 3,054 followed · 2,927 live").
 * Same screen-contract shape as ../company-profiles/profiles-scope.test.ts:
 * a raw number here renders ungrouped and is what this pins out. */

const here = dirname(fileURLToPath(import.meta.url));
const chrome = readFileSync(join(here, "RegisterChrome.tsx"), "utf8");
const view = readFileSync(join(here, "../company-profiles/CompanyProfilesView.tsx"), "utf8");
const strip = (source: string) => source.replace(/\/\*[\s\S]*?\*\//g, "");

describe("toolbar counts follow the person's region", () => {
  it("every figure in the register toolbar-stats goes through copyNumber", () => {
    const stats = strip(chrome).match(
      /of=\{companiesRegisterChromeToolbarStats\}\s*elems=\{\{([\s\S]*?)\}\}/,
    );
    expect(stats).not.toBeNull();
    const figures = [...stats![1].matchAll(/^\s*(\w+):\s*(.+?),?$/gm)];
    expect(figures.map(([, key]) => key)).toEqual([
      "followed",
      "total",
      "sep",
      "openRoles",
      "live",
      "ready",
    ]);
    for (const [, key, value] of figures) {
      if (key === "sep") continue;
      expect(`${key}: ${value}`).toMatch(/copyNumber\(/);
    }
  });

  it("the review count on Companies is grouped, not raw", () => {
    expect(view).toContain('import { number } from "../../copy/format"');
    expect(strip(view)).toMatch(/is-warn"\>\{number\(reviewShown\)\}/);
  });
});
