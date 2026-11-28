import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { SRC, stylesheets } from "./recipes";
import { literalsIn } from "./rhythm";

/* RHYTHM LITERALS ONLY FALL.
 *
 * `geometry.test.ts` holds the sheets it enrols at no rhythm literal (a bare
 * px from 4 to 48 in padding, margin, gap or radius). Every other sheet keeps
 * a count in `rhythm-literals-baseline.json` that may only fall: a sheet over
 * its number fails, and a sheet under it fails until the number is lowered, so
 * the slack never lets a new literal in. A sheet not in the file is held at
 * none. Distance comes from `--app-space-*`, a corner from `--app-radius-*`.
 */

const BASELINE_FILE = "design/rhythm-literals-baseline.json";
const BASELINE: Record<string, number> = JSON.parse(readFileSync(join(SRC, BASELINE_FILE), "utf8"));

const COUNTS: Record<string, number> = Object.fromEntries(
  stylesheets()
    .map(([rel, text]) => [rel, literalsIn(text).length] as const)
    .filter(([, n]) => n > 0),
);

describe("rhythm literals only fall", () => {
  it("keeps its baseline sorted, so a diff reads as a diff", () => {
    const keys = Object.keys(BASELINE);
    expect(keys).toEqual([...keys].sort());
  });

  it("no sheet sets more rhythm literals than its frozen number", () => {
    const over = Object.entries(COUNTS)
      .filter(([file, n]) => n > (BASELINE[file] ?? 0))
      .map(([file, n]) =>
        `${file}: ${n} (frozen at ${BASELINE[file] ?? 0}). Space with --app-space-1..6, ` +
        `round with --app-radius-sm..xl, size a control with --app-control-*:\n    ` +
        literalsIn(readFileSync(join(SRC, file), "utf8")).join("\n    "));
    expect(over, over.join("\n")).toEqual([]);
  });

  it("a sheet below its number has its number lowered", () => {
    const slack = Object.entries(BASELINE)
      .filter(([file, n]) => (COUNTS[file] ?? 0) < n)
      .map(([file, n]) => `${file}: ${COUNTS[file] ?? 0} (frozen at ${n}; lower it in ${BASELINE_FILE})`);
    expect(slack, slack.join("\n")).toEqual([]);
  });

  it("counts what it claims to: rhythm px in the band, never a token or another property", () => {
    expect(literalsIn(".a { padding: 6px 10px; gap: 12px; border-radius: 8px; }")).toHaveLength(4);
    expect(literalsIn(".b { margin: 0 auto 2px; padding: 1px 3px; gap: 64px; }")).toHaveLength(0);
    expect(literalsIn(".c { padding: var(--app-space-2); width: 24px; height: 12px; }")).toHaveLength(0);
    expect(literalsIn(".d { /* padding: 12px */ margin: calc(var(--app-space-2) - 2px); }")).toHaveLength(0);
  });
});
