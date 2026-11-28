import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { rules } from "./cssRules";

/* ONE PAGE MEASURE (docs/ui.md "The app shell"). A screen's content, its
 * title, its toolbar and its body, takes the width `.main > *` gives it,
 * `--app-page-measure`, so every tab's title starts on one left edge at every
 * window width. A screen that caps its own children shows nothing at a laptop
 * width, where no cap applies, and moves its title on a wide window, which is
 * how the screens came apart. So no sheet sets a width on a page root's own
 * children, except through the token, or on the screens and blocks named
 * here.
 *
 * The page roots are read from the source: every element whose class list
 * starts with `main` is one (`<main className="main board-main">`). The
 * browser half is `tests/ux/page-header.spec.ts`, which measures the frame
 * at 1440, 1920 and 2560. */

const SRC = join(dirname(fileURLToPath(import.meta.url)), "..");

function files(dir: string, ext: string, acc: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) {
      if (name !== "gen" && name !== "node_modules") files(path, ext, acc);
    } else if (name.endsWith(ext) && !name.includes(".test.")) acc.push(path);
  }
  return acc;
}

const SHEETS = files(SRC, ".css").map((path) => ({
  file: relative(SRC, path).split(sep).join("/"),
  css: readFileSync(path, "utf8"),
}));

/** The class of every page root, from `className="main ..."` in the source,
 *  `main` itself included. A modifier the root carries (`job-margin-page`)
 *  is a root class too: a width set through it is a width set on the page. */
function pageRoots(): Set<string> {
  const roots = new Set(["main"]);
  for (const path of files(SRC, ".tsx")) {
    for (const m of readFileSync(path, "utf8").matchAll(/["'`]main((?: [\w-]+)+)["'`]/g)) {
      for (const name of m[1].trim().split(/\s+/)) roots.add(name);
    }
  }
  return roots;
}

/** Past the page measure on purpose: the Pipeline, whose stage columns are
 *  its content, and the welcome scene, which takes the whole window. */
const FULL_WIDTH = new Set(["app-main", "welcome-main"]);

/** A block narrower than the frame, centred in it, that moves no edge: Top
 *  picks before setup is one card, and its title is off screen. A toolbar or
 *  a list never is one, since its edges are the frame's. */
const NARROW_BLOCKS = new Set(["onboard"]);

type Finding = { where: string; selector: string; value: string };

/** Every rule that sets a width on a page root's own child, other than the
 *  page measure itself. */
export function measureAudit(sheets: { file: string; css: string }[], roots: Set<string>): Finding[] {
  const found: Finding[] = [];
  for (const { file, css } of sheets) {
    for (const rule of rules(css)) {
      const value = rule.decls.get("max-width") ?? rule.decls.get("max-inline-size");
      if (value === undefined || value === "var(--app-page-measure)") continue;
      for (const selector of rule.selectors) {
        // The subject is a direct child of a compound that names a page root.
        const m = /(?:^|\s)([^\s>]+)\s*>\s*([^\s>]+)\s*$/.exec(selector.replace(/&/g, ""));
        if (!m) continue;
        const named = [...m[1].matchAll(/\.([\w-]+)/g)].map((c) => c[1]);
        if (!named.some((name) => roots.has(name))) continue;
        if (named.some((name) => FULL_WIDTH.has(name))) continue;
        if ([...m[2].matchAll(/\.([\w-]+)/g)].some((c) => NARROW_BLOCKS.has(c[1]))) continue;
        found.push({ where: `${file}:${rule.line}`, selector, value });
      }
    }
  }
  return found;
}

describe("a screen's content takes the one page measure", () => {
  const roots = pageRoots();

  it("reads the page roots from the source", () => {
    // A reader that found none would pass every sheet.
    for (const root of ["board-main", "prof-main", "stats-main", "settings-view", "review-main", "app-main"]) {
      expect(roots, root).toContain(root);
    }
  });

  it("the shell gives every page's children the page measure", () => {
    const shell = SHEETS.find((sheet) => sheet.file === "shell.css")!;
    const main = rules(shell.css).find((rule) => rule.selectors.includes(".main > *"));
    expect(main?.decls.get("max-width")).toBe("var(--app-page-measure)");
  });

  it("no sheet sets a width of its own on a page's children", () => {
    const report = measureAudit(SHEETS, roots).map((f) => `${f.where} ${f.selector} { max-width: ${f.value} }`);
    expect(report).toEqual([]);
  });

  describe("negative controls: the audit refuses each way a screen took its own width", () => {
    const fails = (css: string) => measureAudit([{ file: "x.css", css }], new Set(["main", "board-main", "prof-main", "settings-view", "app-main", "passed-over"])).length > 0;
    it.each([
      [".board-main > * { max-width: 1460px; }"],
      [".passed-over > * { max-width: 1200px; }"],
      [".main > .page-hero { max-width: 1200px; }"],
      [".board-main > .board-toolbar { max-width: 1460px; }"],
      [".board-main > .board-toolbar { max-width: 1200px; }"],
      [".prof-main > .prof-shell { max-width: min(100%, 1480px); }"],
      [".main.stats-main > * { max-width: none; }"],
      [".prof-main > .page-hero, .prof-main > .prof-shell { max-width: 1480px; }"],
      ["main.settings-design-system { &.settings-view > * { max-width: none; } }"],
      [".main > * { max-width: 1200px; }"],
    ])("%s", (css) => expect(fails(css)).toBe(true));
    it.each([
      [".main > * { max-width: var(--app-page-measure); }"],
      [".main.app-main > * { max-width: none; }"],
      [".prof-main > .prof-shell .prof-list { max-width: 260px; }"],
      [".onboard { max-width: 920px; }"],
      [".main > .onboard { max-width: 920px; }"],
      [".board-main > * { padding-right: 76px; }"],
    ])("%s passes", (css) => expect(fails(css)).toBe(false));
  });
});
