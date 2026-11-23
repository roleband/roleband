import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { rules, type Rule } from "./cssRules";

/* A HELD ELEMENT NEVER PAINTS THE BASE COLOUR ALONE.
 *
 * A sticky band hides what scrolls beneath it with an opaque ground. The page
 * is not one flat colour: `body` paints --app-canvas under a wash
 * (--app-ambient-image) that brightens toward a corner. A band filled with
 * --app-canvas alone is darker (or, in the light theme, duller) than the page
 * where the wash is strong, so wherever it ends inside the wash its edge shows
 * as a plate. So over the base colour a held ground paints either
 *   - the page's wash, pinned to the window (`fixed` on every wash layer) so
 *     it lands on the page's own pixels, when it stands on the page; or
 *   - a surface layer, when it stands on a card and imitates the card.
 * A held element is one whose rule is `position: sticky`, or whose selector
 * names the stuck state (`[data-stuck]`), where the fill lives apart from the
 * sticky rule.
 */

const SRC = join(dirname(fileURLToPath(import.meta.url)), "..");

function sheets(dir: string, acc: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) {
      if (name !== "gen" && name !== "node_modules") sheets(path, acc);
    } else if (name.endsWith(".css")) acc.push(path);
  }
  return acc;
}

const BASE = /var\(--app-canvas\)/;
const WASH = /var\(--app-ambient-image\)/;

function held(rule: Rule): boolean {
  return rule.decls.get("position")?.trim() === "sticky" || rule.selectors.some((s) => s.includes("[data-stuck]"));
}

/** Top-level comma-separated items, so a gradient's own commas stay whole. */
function items(value: string): string[] {
  const out: string[] = [];
  let depth = 0;
  let start = 0;
  for (let i = 0; i < value.length; i++) {
    if (value[i] === "(") depth++;
    else if (value[i] === ")") depth--;
    else if (value[i] === "," && depth === 0) { out.push(value.slice(start, i).trim()); start = i + 1; }
  }
  out.push(value.slice(start).trim());
  return out.filter(Boolean);
}

/** What is wrong with a held rule's ground, or null when it is sound. */
function groundProblem(rule: Rule): string | null {
  const color = rule.decls.get("background-color") ?? rule.decls.get("background") ?? "";
  if (!BASE.test(color)) return null;
  const image = rule.decls.get("background-image") ?? "";
  if (!image.trim() || image.trim() === "none") return "paints --app-canvas alone";
  // The wash token is two radial layers; every other item is one.
  const layers = items(image).flatMap((item) => (WASH.test(item) ? ["wash", "wash"] : ["other"]));
  if (!layers.includes("wash")) return null; // a surface layer over the base: it imitates a card
  // As CSS reads it: layer i takes item i, the list repeating when short.
  const attach = items(rule.decls.get("background-attachment") ?? "scroll");
  const loose = layers.some((kind, i) => kind === "wash" && attach[i % attach.length] !== "fixed");
  return loose ? "paints the wash without pinning it to the window (background-attachment: fixed on each wash layer)" : null;
}

function problems(css: string, file: string): string[] {
  const out: string[] = [];
  for (const rule of rules(css)) {
    if (!held(rule)) continue;
    const problem = groundProblem(rule);
    if (problem) out.push(`${file}:${rule.line} ${rule.selectors.join(", ")}: ${problem}`);
  }
  return out;
}

describe("held grounds", () => {
  it("every held element paints the page's wash or a surface over the base colour", () => {
    const found = sheets(SRC).flatMap((path) =>
      problems(readFileSync(path, "utf8"), relative(SRC, path).split(sep).join("/")),
    );
    expect(found).toEqual([]);
  });

  it("the role page's held tabs and headings are among the elements it reads", () => {
    const css = readFileSync(join(SRC, "features/job-detail/job-detail.css"), "utf8");
    const read = rules(css).filter(held).flatMap((r) => r.selectors);
    expect(read).toContain(".jd-tabs[data-stuck]");
    expect(read).toContain(".jd-section h2[data-stuck]");
  });

  it.each([
    ["the base colour alone", ".x { position: sticky; background-color: var(--app-canvas); }", "alone"],
    ["a stuck state with the base colour alone", ".x[data-stuck] { background-color: var(--app-canvas); }", "alone"],
    ["the wash scrolling with the element", ".x { position: sticky; background-color: var(--app-canvas); background-image: var(--app-ambient-image); }", "pinning"],
    ["the wash scrolling under a pinned tint", ".x { position: sticky; background-color: var(--app-canvas); background-image: linear-gradient(var(--app-surface), var(--app-surface)), var(--app-ambient-image); background-attachment: fixed, scroll; }", "pinning"],
  ])("refuses %s", (_name, css, word) => {
    expect(problems(css, "probe.css").join("\n")).toContain(word);
  });

  it.each([
    ["the page's wash, pinned", ".x { position: sticky; background-color: var(--app-canvas); background-image: var(--app-ambient-image); background-attachment: fixed, fixed; }"],
    ["one `fixed`, which CSS repeats to every layer", ".x { position: sticky; background-color: var(--app-canvas); background-image: var(--app-ambient-image); background-attachment: fixed; }"],
    ["a wash under a scrolling tint", ".x { position: sticky; background-color: var(--app-canvas); background-image: linear-gradient(var(--app-surface), var(--app-surface)), var(--app-ambient-image); background-attachment: scroll, fixed, fixed; }"],
    ["a card's surface", ".x { position: sticky; background-color: var(--app-canvas); background-image: linear-gradient(var(--app-surface), var(--app-surface)); }"],
    ["a held element with no ground", ".x { position: sticky; top: 0; }"],
    ["a ground that is not held", ".x { background-color: var(--app-canvas); }"],
  ])("accepts %s", (_name, css) => {
    expect(problems(css, "probe.css")).toEqual([]);
  });
});
