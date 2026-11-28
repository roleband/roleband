import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { rules } from "./cssRules";

/* What the recipe gates share: the walk over the source, the subject of a
 * selector, the recipes themselves, and the frozen name lists. Each gate runs
 * its scanner over `[path, text]` pairs, so a fixture goes through the same code
 * as the real tree. */

export const SRC = join(dirname(fileURLToPath(import.meta.url)), "..");

export type Source = readonly [rel: string, text: string];

function walk(dir: string, keep: (name: string) => boolean, acc: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) {
      if (name !== "gen" && name !== "node_modules") walk(path, keep, acc);
    } else if (keep(name)) acc.push(path);
  }
  return acc;
}

const read = (keep: (name: string) => boolean): Source[] =>
  walk(SRC, keep)
    .map((path) => [relative(SRC, path).split(sep).join("/"), readFileSync(path, "utf8")] as const)
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));

/** Every stylesheet under `src/`, as `[path relative to src, text]`. */
export const stylesheets = (): Source[] => read((name) => name.endsWith(".css"));

/** Every component module under `src/`, tests left out. */
export const components = (): Source[] =>
  read((name) => name.endsWith(".tsx") && !/\.test\.tsx$/.test(name));

/** The compound a selector styles: the last one, with the arguments of
 *  `:not()` and `:has()` removed, since those name other elements. */
function subjectOf(selector: string): string {
  const compounds = selector.split(/\s*[\s>+~]\s*(?![^(]*\))/);
  return compounds[compounds.length - 1].replace(/:(?:not|has)\((?:[^()]|\([^()]*\))*\)/g, "");
}

export const classesIn = (compound: string): string[] =>
  [...compound.matchAll(/\.(-?[a-zA-Z_][\w-]*)/g)].map((m) => m[1]);

/** A padding that says the box is not a card: `0` is a frame whose rows carry
 *  their own inset, and anything under the smallest card step is a bar, a
 *  notice or a chip. `card-inset.test.ts` reads cards by the same rule. */
export const NOT_A_CARD = (padding: string) =>
  /^0(px)?$/.test(padding.trim()) ||
  /var\(--app-space-(1|2)\)/.test(padding) ||
  /^(?:[0-9]|1[0-3])px/.test(padding.trim());

/** The card recipe: a 1px hairline, the card radius and a card inset. */
export function writesCard(decls: Map<string, string>): boolean {
  const border = decls.get("border");
  const radius = decls.get("border-radius");
  const padding = decls.get("padding");
  return (
    !!border && /^1px\b/.test(border) &&
    !!radius && radius.startsWith("var(--app-radius-lg)") &&
    !!padding && !NOT_A_CARD(padding)
  );
}

/** The small label recipe, by the one declaration every copy of it shares. */
export const writesLabel = (decls: Map<string, string>): boolean =>
  decls.get("text-transform") === "uppercase";

/** `sheet :: selector` for every rule in `sheets` that `matches`, outside the
 *  sheets `owns` accepts, with the lines that write it. */
export function recipeCopies(
  sheets: readonly Source[],
  owns: (rel: string) => boolean,
  matches: (decls: Map<string, string>) => boolean,
): Map<string, string[]> {
  const found = new Map<string, string[]>();
  for (const [rel, text] of sheets) {
    if (owns(rel)) continue;
    for (const rule of rules(text)) {
      if (!matches(rule.decls)) continue;
      for (const selector of rule.selectors) {
        const name = `${rel} :: ${selector}`;
        found.set(name, [...(found.get(name) ?? []), `${rel}:${rule.line}`]);
      }
    }
  }
  return found;
}

/* ---- The button's paint and size ---------------------------------------- */

/** What repaints or resizes a button. Placement (margins, width, flex and
 *  grid placement, position) and reveal (`opacity`, `visibility`) are not here:
 *  a screen places a button and may hide it until a row is hovered. */
const BUTTON_PAINT =
  /^(?:color|background(?:-[a-z-]+)?|border(?:-[a-z-]+)?|box-shadow|font-size|font-weight|line-height|letter-spacing|height|min-height|padding(?:-[a-z-]+)?)$/;

function endOfString(s: string, i: number): number {
  const quote = s[i++];
  while (i < s.length && s[i] !== quote) {
    if (s[i] === "\\") i += 2;
    else if (quote === "`" && s.startsWith("${", i)) i = endOfBraces(s, i + 1);
    else i++;
  }
  return i + 1;
}

function endOfBraces(s: string, i: number): number {
  let depth = 0;
  while (i < s.length) {
    const c = s[i];
    if (c === '"' || c === "'" || c === "`") { i = endOfString(s, i); continue; }
    if (c === "{") depth++;
    else if (c === "}" && --depth === 0) return i + 1;
    i++;
  }
  return i;
}

/** The words of every string literal in an attribute value, a template's
 *  `${...}` parts read as expressions of their own. */
function literalWords(value: string): string[] {
  const words: string[] = [];
  for (let i = 0; i < value.length;) {
    const c = value[i];
    if (c !== '"' && c !== "'" && c !== "`") { i++; continue; }
    const end = endOfString(value, i);
    let body = value.slice(i + 1, end - 1);
    if (c === "`") {
      let plain = "";
      for (let j = 0; j < body.length;) {
        if (body.startsWith("${", j)) {
          const close = endOfBraces(body, j + 1);
          words.push(...literalWords(body.slice(j + 2, close - 1)));
          plain += " ";
          j = close;
        } else plain += body[j++];
      }
      body = plain;
    }
    words.push(...body.split(/\s+/).filter((w) => /^[a-zA-Z][\w-]*$/.test(w)));
    i = end;
  }
  return words;
}

/** The literal class names a module hands to `<Button` and `<RouterLink`. */
export function classesOnButtons(tsx: string): string[] {
  const out = new Set<string>();
  for (const tag of tsx.matchAll(/<(?:Button|RouterLink)(?=[\s/>])/g)) {
    let i = tag.index + tag[0].length;
    while (i < tsx.length && tsx[i] !== ">") {
      if (tsx.startsWith("className=", i) && /\s/.test(tsx[i - 1])) {
        const at = i + "className=".length;
        const end = tsx[at] === "{" ? endOfBraces(tsx, at) : endOfString(tsx, at);
        for (const word of literalWords(tsx[at] === "{" ? tsx.slice(at + 1, end - 1) : tsx.slice(at, end))) {
          out.add(word);
        }
        i = end;
        continue;
      }
      const c = tsx[i];
      if (c === "{") i = endOfBraces(tsx, i);
      else if (c === '"' || c === "'") i = endOfString(tsx, i);
      else i++;
    }
  }
  return [...out];
}

/** Classes handed to a `Button` or `RouterLink` outside `src/ui/` whose own
 *  rules repaint or resize it, with the rules that do. */
export function buttonRepaints(modules: readonly Source[], sheets: readonly Source[]): Map<string, string[]> {
  const onButtons = new Set(
    modules
      .filter(([rel]) => !rel.startsWith("ui/"))
      .flatMap(([, text]) => classesOnButtons(text))
      .filter((name) => !name.startsWith("ui-")),
  );
  const found = new Map<string, string[]>();
  for (const [rel, text] of sheets) {
    for (const rule of rules(text)) {
      const painted = [...rule.decls.keys()].filter((p) => BUTTON_PAINT.test(p));
      if (!painted.length) continue;
      for (const selector of rule.selectors) {
        for (const name of classesIn(subjectOf(selector))) {
          if (!onButtons.has(name)) continue;
          const where = `${rel}:${rule.line} ${painted.join(", ")}`;
          const seen = found.get(name) ?? [];
          if (!seen.includes(where)) found.set(name, [...seen, where]);
        }
      }
    }
  }
  return found;
}

/* ---- Frozen name lists -------------------------------------------------- */

/** Names found and not listed, and names listed and no longer found. */
export function compareNames(list: readonly string[], found: ReadonlyMap<string, unknown>) {
  return {
    added: [...found.keys()].filter((name) => !list.includes(name)).sort(),
    stale: list.filter((name) => !found.has(name)),
  };
}
