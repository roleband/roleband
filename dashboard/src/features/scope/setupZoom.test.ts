import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { DESIGN_HEIGHT, DESIGN_WIDTH, MAX_FACTOR, setupFactor } from "./setupZoom";

const SRC = join(dirname(fileURLToPath(import.meta.url)), "../..");
const rel = (file: string) => relative(SRC, file).split(sep).join("/");

function files(dir: string, ext: RegExp, acc: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) files(path, ext, acc);
    else if (ext.test(name)) acc.push(path);
  }
  return acc;
}

describe("the factor", () => {
  /* Six tenths of the room beyond the design: a window with a fifth more
     room is drawn an eighth larger, not a fifth. */
  it.each([
    [1440, 900, 1], [1440, 1100, 1], [2000, 760, 1], [1280, 800, 1], [390, 844, 1],
    [1584, 990, 1.06], [1728, 1080, 1.12], [1728, 1000, 1.12], [1872, 1170, 1.18],
    [1600, 900, 1 + 0.6 * (1600 / DESIGN_WIDTH - 1)], [1470, 850, 1 + 0.6 * (1470 / DESIGN_WIDTH - 1)],
    [2000, 900, 1 + 0.6 * (900 / DESIGN_HEIGHT - 1)], [1920, 1000, 1 + 0.6 * (1000 / DESIGN_HEIGHT - 1)],
    [2000, 1100, 1 + 0.6 * (2000 / DESIGN_WIDTH - 1)],
    [2160, 1350, 1.3], [2560, 1440, 1.3], [5120, 2880, 1.3],
  ])("a %i x %i window is magnified %f", (width, height, factor) => {
    expect(setupFactor(width, height)).toBeCloseTo(factor, 9);
  });

  it("never gives the layout less room than the design", () => {
    for (let width = 1200; width <= 2600; width += 7) {
      for (let height = 600; height <= 1500; height += 11) {
        const factor = setupFactor(width, height);
        expect(factor).toBeGreaterThanOrEqual(1);
        expect(factor).toBeLessThanOrEqual(MAX_FACTOR);
        if (factor === 1) continue;
        expect(width / factor).toBeGreaterThanOrEqual(DESIGN_WIDTH - 1e-9);
        expect(height / factor).toBeGreaterThanOrEqual(DESIGN_HEIGHT - 1e-9);
      }
    }
  });

  /* Browser zoom shrinks the window in CSS pixels and enlarges each one, so
     what the person sees is the browser's zoom times this factor. Turning the
     browser's zoom up must never make setup smaller, at any zoom: the
     browsers' own steps, and the finer ones a pinch or a setting reaches. */
  const LADDER = [0.9, 1, 1.02, 1.04, 1.06, 1.08, 1.1, 1.15, 1.2, 1.25, 1.3, 1.5, 1.75, 2];
  const WINDOWS = [[1920, 1000], [1728, 1000], [2560, 1300], [1600, 900], [2000, 1100], [1872, 1170]] as const;
  const shrinks = (factor: (width: number, height: number) => number) => WINDOWS.filter(([width, height]) => {
    const seen = LADDER.map((zoom) => zoom * factor(width / zoom, height / zoom));
    return seen.some((size, i) => i > 0 && size < seen[i - 1] - 1e-9);
  });

  it("turning the browser's zoom up never makes setup smaller", () => {
    expect(shrinks(setupFactor)).toEqual([]);
  });

  it("would catch a factor rounded to a step, which shrinks setup as browser zoom grows", () => {
    const stepped = (width: number, height: number) => Math.round(setupFactor(width, height) * 20) / 20;
    expect(shrinks(stepped)).not.toEqual([]);
  });
});

/* Under the zoom, a window unit is measured from the real window and then
   magnified, so every one a setup screen can draw is divided back by
   `--page-zoom`; the rest are listed with the reason no setup screen draws
   them. A new window unit fails here until it is one or the other. */

const WINDOW_UNIT = /(?<![\w-])(\d*\.?\d+)(vw|vh|vmin|vmax|dvh|svh|lvh|dvw|svw|lvw|dvmin|dvmax)\b/g;
const DIVIDED = /^\s*\/\s*var\(--page-zoom, 1\)/;

type Declaration = { file: string; selector: string; text: string; within: string[] };

/** Every declaration in a stylesheet, with the rule and the at-rules it is in. */
function declarations(file: string): Declaration[] {
  const css = readFileSync(file, "utf8").replace(/\/\*[\s\S]*?\*\//g, (comment) => comment.replace(/[^\n]/g, " "));
  const out: Declaration[] = [];
  const stack: string[] = [];
  let start = 0;
  const take = (end: number) => {
    const text = css.slice(start, end).trim();
    if (!text) return;
    const selector = [...stack].reverse().find((prelude) => !prelude.startsWith("@")) ?? "";
    out.push({ file: rel(file), selector: selector.replace(/\s+/g, " "), text, within: [...stack] });
  };
  for (let i = 0; i < css.length; i++) {
    if (css[i] === "{") { stack.push(css.slice(start, i).trim()); start = i + 1; }
    else if (css[i] === ";") { take(i); start = i + 1; }
    else if (css[i] === "}") { take(i); stack.pop(); start = i + 1; }
  }
  return out;
}

const STYLESHEETS = files(SRC, /\.css$/);
const ALL = STYLESHEETS.flatMap(declarations);

const BOARD = "the board, its filters and its job pages; setup shows none of them";
const PAGES = "a page of the app's own, reached from the rail, which setup does not draw";
const NOT_SETUP: Record<string, string> = {
  "features/company-profiles/company-profiles.css .main.prof-main": PAGES,
  "features/company-profiles/company-profiles.css .prof-main > .prof-shell > .prof-list": PAGES,
  "features/notifications/notification-bell.css .notif-popover .ui-popover-inner": "the bell sits in the top bar, which setup does not draw",
  "features/opportunities/board-shell.css .board-first-scan .empty": BOARD,
  "features/review/review.css .review-decision-console.has-ai-response": PAGES,
  "features/review/review.css .review-history": PAGES,
  "features/review/review.css .review-history-search": PAGES,
  "features/scope/welcome/welcome.css .welcome-intro--asking .welcome-globe": "a phone-width rule; setup is magnified only from 1440 px wide",
  "features/settings/ScheduleSection.css .ui-popover.schedule-help .ui-popover-inner": PAGES,
  "features/settings/ScheduleSection.css .schedule-clock-editor": PAGES,
  "features/settings/ScheduleSection.css .schedule-clock-stage": PAGES,
  "features/settings/ScheduleSection.css .ui-popover.schedule-inspector .ui-popover-inner": PAGES,
  "features/settings/ScheduleSection.css .schedule-deadlines-sheet": PAGES,
  "patterns/jobs/margin.css .job-reveal": BOARD,
  "patterns/rail-shell.css .rail-shell-rail": BOARD,
  "shell.css .palette-wrap": "the command palette, which does not open during setup (App.tsx)",
  "shell.css .palette": "the command palette, which does not open during setup (App.tsx)",
  "shell.css .palette-list": "the command palette, which does not open during setup (App.tsx)",
  "ui/FilterRail.css .filter-pop": BOARD,
  "ui/FilterRail.css .ui-overlay-content.filter-pop": BOARD,
  "ui/FilterSelect.css .ui-filterselect": BOARD,
  "ui/FilterSelect.css .ui-filterselect-list": BOARD,
};

describe("window units under the setup zoom", () => {
  const uses = ALL.flatMap((d) => [...d.text.matchAll(WINDOW_UNIT)].map((match) => ({
    key: `${d.file} ${d.selector}`,
    divided: DIVIDED.test(d.text.slice((match.index ?? 0) + match[0].length)),
    text: d.text,
  })));

  it("finds the window units it guards", () => {
    expect(uses.length).toBeGreaterThan(20);
  });

  it("divides every window unit a setup screen can draw by the zoom", () => {
    const loose = uses.filter((use) => !use.divided && !(use.key in NOT_SETUP)).map((use) => `${use.key}: ${use.text}`);
    expect(loose).toEqual([]);
  });

  it("lists only rules that still use a window unit, and divides none of them", () => {
    const listed = new Set(uses.filter((use) => !use.divided).map((use) => use.key));
    expect(Object.keys(NOT_SETUP).filter((key) => !listed.has(key))).toEqual([]);
    expect(uses.filter((use) => use.divided && use.key in NOT_SETUP).map((use) => use.key)).toEqual([]);
  });

  it("sets the zoom's value only where the browser supports zoom", () => {
    const set = ALL.filter((d) => /^--page-zoom\s*:/.test(d.text));
    expect(set.length).toBeGreaterThan(0);
    expect(set.filter((d) => !d.within.some((prelude) => /^@supports\s*\(zoom:\s*1\)$/.test(prelude)))
      .map((d) => `${d.file} ${d.selector}`)).toEqual([]);
    const scripts = files(SRC, /\.tsx?$/).filter((file) => !file.endsWith(".test.ts") && !file.endsWith(".test.tsx"));
    expect(scripts.filter((file) => /["'`]--page-zoom["'`]/.test(readFileSync(file, "utf8"))).map(rel)).toEqual([]);
  });
});

/* A box placed from `getBoundingClientRect` and the window's size lands off
   by the factor under the zoom. These place one; none may be reachable from a
   setup screen until it converts by the zoom and is tested at it. */
const PLACED = ["ui/Popover.tsx", "patterns/companies/CompanyChip.tsx", "patterns/FilterSurface.tsx"];
const SETUP_SCREENS = ["features/scope/Welcome.tsx", "features/scope/walk/Walk.tsx", "features/companies/SetupCompanies.tsx"];

function resolveModule(from: string, spec: string): string | null {
  if (!spec.startsWith(".")) return null;
  const base = resolve(dirname(from), spec);
  for (const candidate of [base, `${base}.ts`, `${base}.tsx`, join(base, "index.ts"), join(base, "index.tsx")]) {
    if (existsSync(candidate) && statSync(candidate).isFile()) return candidate;
  }
  return null;
}

/** What a file imports: each module, and the names taken from it (null: all of it). */
function imports(file: string): { module: string; names: string[] | null }[] {
  const text = readFileSync(file, "utf8");
  const out: { module: string; names: string[] | null }[] = [];
  const add = (spec: string, names: string[] | null) => {
    const module = resolveModule(file, spec);
    if (module) out.push({ module, names });
  };
  for (const match of text.matchAll(/(?:^|\n)\s*(?:import|export)\s+(type\s+)?([\s\S]*?)\s+from\s+["']([^"']+)["']/g)) {
    if (match[1]) continue;
    const braces = /\{([\s\S]*)\}/.exec(match[2]);
    const names = braces
      ? braces[1].split(",").map((part) => part.trim()).filter((part) => part && !part.startsWith("type "))
        .map((part) => part.split(/\s+as\s+/)[0].trim())
      : null;
    add(match[3], names && !/^\*|,\s*\*/.test(match[2]) ? names : null);
  }
  for (const match of text.matchAll(/(?:^|\n)\s*import\s+["']([^"']+)["']/g)) add(match[1], null);
  for (const match of text.matchAll(/import\(\s*["']([^"']+)["']\s*\)/g)) add(match[1], null);
  return out;
}

/** The files a barrel re-exports `names` from. */
function throughBarrel(barrel: string, names: string[]): string[] {
  const text = readFileSync(barrel, "utf8");
  const out: string[] = [];
  for (const match of text.matchAll(/export\s+(type\s+)?\{([^}]*)\}\s+from\s+["']([^"']+)["']/g)) {
    if (match[1]) continue;
    const exported = match[2].split(",").map((part) => part.trim().split(/\s+as\s+/).pop()!.trim());
    if (exported.some((name) => names.includes(name))) {
      const module = resolveModule(barrel, match[3]);
      if (module) out.push(module);
    }
  }
  for (const match of text.matchAll(/export\s+\*\s+from\s+["']([^"']+)["']/g)) {
    const module = resolveModule(barrel, match[1]);
    if (module) out.push(module);
  }
  return out;
}

/** Every source file a setup screen can reach, following a barrel only to the names taken from it. */
function reachable(entries: string[]): Set<string> {
  const seen = new Set<string>();
  const queue = entries.map((entry) => join(SRC, entry));
  while (queue.length) {
    const file = queue.pop()!;
    if (seen.has(file) || !/\.tsx?$/.test(file)) continue;
    seen.add(file);
    for (const { module, names } of imports(file)) {
      const barrel = /[/\\]index\.tsx?$/.test(module);
      if (barrel && names) queue.push(...throughBarrel(module, names));
      else queue.push(module);
    }
  }
  return seen;
}

describe("pop-ups placed from a position", () => {
  const reached = [...reachable(SETUP_SCREENS)].map(rel);

  it("follows the setup screens' imports into the pieces they draw", () => {
    expect(reached).toEqual(expect.arrayContaining([
      "features/scope/walk/SummaryStep.tsx", "ui/Button.tsx", "patterns/privacy/ConsentPane.tsx",
    ]));
  });

  it("are not reachable from any setup screen", () => {
    expect(reached.filter((file) => PLACED.includes(file))).toEqual([]);
  });

  it("would be found through the ui barrel", () => {
    const barrel = join(SRC, "ui/index.ts");
    expect(throughBarrel(barrel, ["Popover"]).map(rel)).toContain("ui/Popover.tsx");
    expect(throughBarrel(barrel, ["Button"]).map(rel)).not.toContain("ui/Popover.tsx");
  });
});
