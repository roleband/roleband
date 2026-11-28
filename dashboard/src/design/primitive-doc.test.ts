import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { rules } from "./cssRules";
import { SRC, classesIn } from "./recipes";

/* docs/ui.md names the shared pieces where they are.
 *
 * "The primitive tier" is where a contributor looks before writing a box, a
 * label or a table, so what it names must exist where it says, and what the
 * tier exports must be named there. A shared class the table names is defined
 * in the sheet the table gives; every component `ui/index.ts` exports is named
 * in the document, in code type (`Name`, `ui/Name` or `<Name ...>`).
 */

const DOC = readFileSync(join(SRC, "../../docs/ui.md"), "utf8");
const INDEX = readFileSync(join(SRC, "ui/index.ts"), "utf8");

/** Rows of the table headed `| Job | Class | Sheet |`. */
function sharedClassRows(markdown: string): { classes: string[]; sheet: string }[] {
  const start = markdown.indexOf("| Job | Class | Sheet |");
  if (start < 0) return [];
  const rows = markdown.slice(start).split("\n").slice(2);
  const out: { classes: string[]; sheet: string }[] = [];
  for (const row of rows) {
    if (!row.startsWith("|")) break;
    const cells = row.split(/(?<!\\)\|/).slice(1, -1);
    out.push({
      classes: [...cells[1].matchAll(/`\.([\w-]+)`/g)].map((m) => m[1]),
      sheet: cells[2].match(/`([^`]+\.css)`/)?.[1] ?? "",
    });
  }
  return out;
}

const definedIn = (css: string, name: string) =>
  rules(css).some((rule) => rule.selectors.some((selector) => classesIn(selector).includes(name)));

/** The components the tier exports: value exports named in PascalCase. */
function exportedComponents(index: string): string[] {
  return [...index.matchAll(/^export \{([^}]+)\} from/gm)]
    .flatMap((m) => m[1].split(","))
    .map((name) => name.trim())
    .filter((name) => /^[A-Z][a-z]\w*$/.test(name) && !name.includes("_"));
}

const namedIn = (markdown: string, name: string) =>
  new RegExp("`(?:ui/|<)?" + name + "\\b[^`]*`").test(markdown);

describe("the primitive tier in docs/ui.md", () => {
  const rows = sharedClassRows(DOC);

  it("names a shared class only where its sheet defines it", () => {
    const missing = rows.flatMap(({ classes, sheet }) => {
      let css = "";
      try { css = readFileSync(join(SRC, sheet), "utf8"); } catch { return [`${sheet} (no such sheet)`]; }
      return classes.filter((name) => !definedIn(css, name)).map((name) => `.${name} in ${sheet}`);
    });
    expect(
      missing,
      `docs/ui.md (The primitive tier) names classes their sheet does not define. ` +
        `Correct the row, or the sheet it points at:\n  ${missing.join("\n  ")}`,
    ).toEqual([]);
  });

  it("names every component ui/index.ts exports", () => {
    const unnamed = exportedComponents(INDEX).filter((name) => !namedIn(DOC, name));
    expect(
      unnamed,
      `ui/index.ts exports components docs/ui.md never names. Add each to the ` +
        `primitive tier's table with the job it does, so a screen finds it ` +
        `before writing its own: ${unnamed.join(", ")}`,
    ).toEqual([]);
  });
});

describe("the primitive tier scan can see a gap", () => {
  const doc = [
    "| Job | Use |", "|---|---|", "| A button | `Button` |", "",
    "| Job | Class | Sheet |", "|---|---|---|",
    "| A card | `.panel` | `design/overlays.css` |",
    "| A form | `.probe-form`, `.probe-form-actions` | `design/probe.css` |",
    "", "Text after the table.",
  ].join("\n");

  it("reads every class of every row, and the sheet beside them", () => {
    expect(sharedClassRows(doc)).toEqual([
      { classes: ["panel"], sheet: "design/overlays.css" },
      { classes: ["probe-form", "probe-form-actions"], sheet: "design/probe.css" },
    ]);
  });

  it("finds a class in a compound or nested selector, and misses one that is absent", () => {
    const css = ".probe-form { display: grid; > .probe-form-actions { gap: 0; } }";
    expect(definedIn(css, "probe-form-actions")).toBe(true);
    expect(definedIn(css, "probe-form-act")).toBe(false);
    expect(definedIn(css, "panel")).toBe(false);
  });

  it("reads value exports, never types, hooks or constants, and needs the name in code type", () => {
    const index = 'export { Probe, ProbeRow, useProbe, PROBE_QUERY } from "./Probe";\nexport type { ProbeProps } from "./Probe";\n';
    expect(exportedComponents(index)).toEqual(["Probe", "ProbeRow"]);
    expect(namedIn(doc, "Button")).toBe(true);
    expect(namedIn("A plain Probe in prose, and `ProbeRow`.", "Probe")).toBe(false);
  });

  it("finds the real table and exports, so the checks above are about something", () => {
    expect(sharedClassRows(DOC).length).toBeGreaterThanOrEqual(8);
    expect(exportedComponents(INDEX).length).toBeGreaterThanOrEqual(40);
  });
});
