import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { rules } from "./cssRules";

/* ONE FOCUS RING (docs/ui.md "One focus ring").
 *
 * A focus indicator needs 3:1 against the page (WCAG 1.4.11), which a tinted
 * outline (`--app-action-line`), a text field's halo (`-line` border + 3px
 * `-ring`) or a soft halo does not reach. A look that passes contrast can
 * still say something else: a gold left edge is the mark of a row picked for
 * Compare, a glow is a hover, and danger, information and ink are hues with
 * their own meaning.
 *
 * The ring is `shell.css`'s global rule: `--app-ring-width` solid
 * `--app-action`. A sheet may change only WHERE it is drawn. This is the
 * source half:
 *   1. a focus rule paints its ring only in `--app-action` (in the rail, the
 *      rail's own `--rail-accent`), at the ring's width and one of the ring's
 *      two offsets; no tint, halo, glow, literal or other hue;
 *   2. `outline: none` appears only where a named carrier draws the ring
 *      instead, or on an element focused only by script, each with its reason;
 *      every carrier still declares the ring;
 *   3. the ring's colours clear 3:1 on every ground they land on.
 * The behaviour half is `tests/ux/focus-ring.spec.ts`, a name-blind Tab sweep.
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

const SHEETS = sheets(SRC).map((path) => ({
  file: relative(SRC, path).split(sep).join("/"),
  css: readFileSync(path, "utf8"),
}));

const withoutNegations = (s: string) => {
  let out = "";
  for (let i = 0; i < s.length; i++) {
    if (s.startsWith(":not(", i)) {
      let depth = 0;
      for (; i < s.length; i++) {
        if (s[i] === "(") depth++;
        else if (s[i] === ")" && --depth === 0) break;
      }
      continue;
    }
    out += s[i];
  }
  return out;
};

const isFocusRule = (selector: string) => /:focus(?:-visible|-within)?\b/.test(withoutNegations(selector));

const RING_PROPS = /^(?:outline(?:-color|-width|-style)?|box-shadow|stroke|border(?:-(?:top|right|bottom|left))?(?:-color)?)$/;
const RING_TOKEN = /^--app-action$/;
const RAIL_TOKEN = /^--rail-accent$/;
const OFFSETS = new Set(["var(--app-ring-offset)", "calc(-1 * var(--app-ring-offset))"]);

/** Where the ring is drawn by something other than the focused element, and
 *  every other `outline: none` in the app. Each names what draws instead. */
const SUPPRESSIONS: { file: string; selector: string; drawnBy: string; why: string }[] = [
  { file: "ui/SearchField.css", selector: ".ui-search-input", drawnBy: ".ui-search:focus-within", why: "the field the user sees is the wrapper; the bare input inside it would draw a square ring within the rounded one" },
  { file: "ui/SearchField.css", selector: ".ui-search-input:focus-visible", drawnBy: ".ui-search:focus-within", why: "the same, stated on the focus state so it outranks shell.css's input ring" },
  { file: "features/statistics/statistics.css", selector: ".cluster-card-select:focus-visible", drawnBy: ".cluster-card:has(.cluster-card-select:focus-visible)", why: "the card is what responds; the button is only its title, and shell.css's button ring would draw a second ring around those words" },
  { file: "ui/FilterRail.css", selector: ".filter-search-row input", drawnBy: ".filter-search-row:focus-within", why: "the row is the field; the input has no border of its own" },
  { file: "ui/FilterRail.css", selector: ".filter-search-row input:focus-visible", drawnBy: ".filter-search-row:focus-within", why: "the same, on the focus state" },
  { file: "shell.css", selector: ".palette-input input", drawnBy: ".palette-item.is-cursor", why: "focus never leaves the palette's field, so the highlighted option, where Enter acts, wears the one ring; a ring on the field too would be a second" },
  { file: "ui/Select.css", selector: ".ui-select > select[data-pointer]:focus-visible", drawnBy: ".ui-select > select:focus-visible:not([data-pointer])", why: "the select rings for the keyboard only: pointer focus on a native select never releases" },
  { file: "features/intelligence/IntelligenceSection.css", selector: ".intel-field-svg .fit-band", drawnBy: ".intel-field-svg .fit-band:focus-visible .fit-band-zone", why: "an SVG band takes the ring as a stroke on its shape; an outline on a `g` boxes its bounds" },
  { file: "features/scope/walk/walk.css", selector: ".walk-pyramid-layer", drawnBy: ".walk-pyramid-layer:focus-visible .walk-pyramid-hit", why: "an SVG layer takes the ring as a stroke" },
  { file: "ui/TimeField.css", selector: ".ui-timefield-framed input[type=\"time\"]", drawnBy: ".ui-timefield-framed:has(> input:focus)", why: "the framed field the user sees is the wrapper, which also holds the list button; the bare input inside it would draw a second ring within the field's edge" },
  { file: "ui/TimeField.css", selector: ".ui-timefield-list:focus-visible", drawnBy: ".ui-timefield-list:focus-visible .ui-timefield-option[data-cursor]", why: "focus stays on the list while the arrows move through it, so the time they are on, where Enter acts, wears the one ring; a ring on the list too would be a second" },
  { file: "ui/Overlay.css", selector: ".ui-overlay-content", drawnBy: "", why: "focused only by script when a dialog opens with nothing focusable; never a Tab stop" },
  { file: "ui/Overlay.css", selector: ".ui-overlay-content[tabindex]:focus-visible", drawnBy: "", why: "the same, on the focus state, heavy enough to beat the global ring whatever order the sheets load in" },
  { file: "shell.css", selector: ".body:focus", drawnBy: "", why: "the page region the skip link sends focus to by script; never a Tab stop" },
];

type Finding = string;

function audit(): { paints: Finding[]; suppressions: Finding[]; used: Set<number> } {
  const paints: Finding[] = [];
  const suppressions: Finding[] = [];
  const used = new Set<number>();
  for (const { file, css } of SHEETS) {
    for (const rule of rules(css)) {
      for (const selector of rule.selectors) {
        const at = `${file}:${rule.line} ${selector}`;
        const outline = rule.decls.get("outline");
        if (outline && /^(?:none|0)$/.test(outline.trim())) {
          const i = SUPPRESSIONS.findIndex((s) => s.file === file && s.selector === selector);
          if (i < 0) suppressions.push(`${at}  ->  outline: ${outline} with nothing named to draw the ring`);
          else used.add(i);
          continue;
        }
        if (!isFocusRule(selector)) continue;
        const rail = file === "shell.css" && selector.startsWith(".nav-rail");
        for (const [prop, value] of rule.decls) {
          if (prop === "outline-offset") {
            if (!OFFSETS.has(value)) paints.push(`${at}  ->  outline-offset: ${value} (the ring's offset, or its inverse)`);
            continue;
          }
          if (!RING_PROPS.test(prop)) continue;
          if (/#[0-9a-f]{3,8}\b|rgba?\(|hsla?\(|color-mix\(/i.test(value)) {
            paints.push(`${at}  ->  ${prop}: ${value} (a literal colour)`);
            continue;
          }
          if (prop === "outline" && !/var\(--app-ring-width\)/.test(value)) {
            paints.push(`${at}  ->  outline: ${value} (the ring is --app-ring-width wide)`);
          }
          for (const [, token] of value.matchAll(/var\((--[\w-]+)/g)) {
            if (token === "--app-ring-width") continue;
            if (RING_TOKEN.test(token) || (rail && RAIL_TOKEN.test(token))) continue;
            paints.push(`${at}  ->  ${prop}: ${value} (a focus ring is --app-action${rail ? " or --rail-accent" : ""})`);
          }
        }
      }
    }
  }
  return { paints, suppressions, used };
}

const result = audit();

describe("one focus ring", () => {
  it("every focus rule paints the ring in the action colour, at its width and offset", () => {
    expect(result.paints).toEqual([]);
  });

  it("outline is suppressed only where a named carrier draws it, or focus is script-only", () => {
    expect(result.suppressions).toEqual([]);
  });

  it("every named suppression is live, and every carrier still declares the ring", () => {
    const dead = SUPPRESSIONS.filter((_, i) => !result.used.has(i)).map((s) => `${s.file} ${s.selector}`);
    expect(dead, "a suppression that matches nothing").toEqual([]);
    const ringless = SUPPRESSIONS.filter((s) => s.drawnBy).filter((s) => {
      const css = SHEETS.find((sh) => sh.file === s.file)!.css;
      // A selector can appear in more than one rule (one sets fill-opacity, the
      // next the stroke): the carrier holds if ANY of them draws the ring.
      return !rules(css)
        .filter((r) => r.selectors.includes(s.drawnBy))
        .some((r) =>
          /var\(--app-action\)/.test([...r.decls.values()].join(" ")) &&
          /(?:outline|stroke)/.test([...r.decls.keys()].join(" ")));
    });
    expect(ringless.map((s) => `${s.file} ${s.drawnBy}`), "a carrier that no longer draws the ring").toEqual([]);
  });

  it("the global rule is the ring, and reaches every focusable element kind", () => {
    const shell = SHEETS.find((s) => s.file === "shell.css")!.css;
    const global = rules(shell).find((r) => r.selectors.includes("[tabindex]:focus-visible"))!;
    expect(global.selectors).toEqual(expect.arrayContaining([
      "button:focus-visible", "a:focus-visible", "input:focus-visible", "select:focus-visible",
      "textarea:focus-visible", "summary:focus-visible", "[tabindex]:focus-visible",
      'input:is([type="time"], [type="date"], [type="datetime-local"], [type="month"], [type="week"]):focus-within',
    ]));
    expect(global.decls.get("outline")).toBe("var(--app-ring-width) solid var(--app-action)");
    expect(global.decls.get("outline-offset")).toBe("var(--app-ring-offset)");
  });

  it("the carriers the UX sweep accepts are the carriers named here", () => {
    const spec = readFileSync(join(SRC, "..", "tests", "ux", "focus-ring.spec.ts"), "utf8");
    const block = spec.slice(spec.indexOf("const CARRIERS"), spec.indexOf("];", spec.indexOf("const CARRIERS")));
    const carriers = [...block.matchAll(/\["([^"]+)", "([^"]+)"\]/g)].map((m) => m[2]);
    // Each carrier the sweep accepts draws the ring in a sheet.
    const drawn = SHEETS.flatMap(({ css }) => rules(css))
      .filter((r) => /var\(--app-action\)/.test([...r.decls.values()].join(" ")))
      .flatMap((r) => r.selectors);
    for (const carrier of carriers) {
      expect(drawn.some((s) => s.startsWith(carrier) && isFocusRule(s)), `${carrier} draws no ring`).toBe(true);
    }
  });
});

/* A field wears the ring on its own edge (docs/ui.md "One focus ring"). A
 * field has a border, so a ring outside it is a second frame, and a field
 * rings on every click: the doubled frame is the look of every form. */
const INSIDE = "calc(-1 * var(--app-ring-offset))";
/** Wrappers that are the visible field around a bare input. */
const FIELD_CARRIERS = [".ui-search", ".filter-search-row"];
const NOT_FIELD_TYPES = /\[type="(?:checkbox|radio|range|color|file|button|submit|reset|image)"\]/;

/** Splits `s` at each `sep` that stands outside brackets, so the spaces and
 *  commas inside `:is(…)` or `[type="…"]` never cut a selector apart. */
const splitOutside = (s: string, sep: RegExp) => {
  const parts: string[] = [];
  let depth = 0;
  let start = 0;
  for (let i = 0; i < s.length; i++) {
    if (s[i] === "(" || s[i] === "[") depth++;
    else if (s[i] === ")" || s[i] === "]") depth--;
    else if (depth === 0 && sep.test(s[i])) {
      parts.push(s.slice(start, i));
      start = i + 1;
    }
  }
  return [...parts, s.slice(start)].map((p) => p.trim()).filter(Boolean);
};

/** The focused thing a selector names is a field: a text input, a textarea,
 *  a select, or a carrier that stands for one. A leading `:is(…)` or
 *  `:where(…)` names a field when one of its choices does. */
const namesField = (selector: string): boolean => {
  const subject = splitOutside(withoutNegations(selector), /[\s>+~]/).pop() ?? "";
  const group = /^:(?:is|where)\(/.exec(subject);
  if (group) {
    let depth = 0;
    let end = group[0].length;
    for (let i = end - 1; i < subject.length; i++) {
      if (subject[i] === "(") depth++;
      else if (subject[i] === ")" && --depth === 0) { end = i; break; }
    }
    const rest = subject.slice(end + 1);
    return splitOutside(subject.slice(group[0].length, end), /,/).some((choice) => namesField(choice + rest));
  }
  if (FIELD_CARRIERS.some((c) => subject.startsWith(`${c}:`))) return true;
  if (/^(?:textarea|select)\b/.test(subject)) return true;
  return /^input\b/.test(subject) && !NOT_FIELD_TYPES.test(subject);
};

function fieldAudit(): Finding[] {
  const out: Finding[] = [];
  for (const { file, css } of SHEETS) {
    for (const rule of rules(css)) {
      const offset = rule.decls.get("outline-offset");
      if (!offset) continue;
      // The app-wide ring for every focusable kind; the field rule after it moves a field's inside.
      if (file === "shell.css" && rule.selectors.includes("[tabindex]:focus-visible")) continue;
      for (const selector of rule.selectors) {
        if (!isFocusRule(selector) || !namesField(selector) || offset === INSIDE) continue;
        out.push(`${file}:${rule.line} ${selector}  ->  outline-offset: ${offset} (a field's ring is inside its edge)`);
      }
    }
  }
  return out;
}

describe("a field wears the ring on its own edge", () => {
  it("shell.css moves every field's ring inside, by element, after the app-wide ring", () => {
    const shell = SHEETS.find((s) => s.file === "shell.css")!.css;
    const all = rules(shell);
    const global = all.findIndex((r) => r.selectors.includes("[tabindex]:focus-visible"));
    const field = all.findIndex((r) => r.selectors.some((s) => s.startsWith("input:not(") && s.endsWith(":focus-visible")));
    expect(field, "the field rule").toBeGreaterThan(global);
    expect(all[field].decls.get("outline-offset")).toBe(INSIDE);
    expect(all[field].selectors).toEqual(expect.arrayContaining(["select:focus-visible", "textarea:focus-visible"]));
    expect(all[field].selectors.some((s) => s.startsWith('input:is([type="time"]') && s.endsWith(":focus-within"))).toBe(true);
    // The types left out are the ones that are not fields.
    const sel = all[field].selectors.find((s) => s.startsWith("input:not("))!;
    for (const kept of ["text", "search", "email", "number", "url", "password", "date"]) {
      expect(sel.includes(`[type="${kept}"]`), `${kept} is a field`).toBe(false);
    }
    for (const left of ["checkbox", "radio", "range", "button", "submit"]) {
      expect(sel.includes(`[type="${left}"]`), `${left} is not a field`).toBe(true);
    }
  });

  it("no sheet draws a field's ring outside its edge", () => {
    expect(fieldAudit()).toEqual([]);
  });

  describe("the detector fails the shapes it exists to catch", () => {
    const check = (css: string) => {
      const saved = SHEETS.splice(0, SHEETS.length, { file: "features/x.css", css });
      try { return fieldAudit(); } finally { SHEETS.splice(0, SHEETS.length, ...saved); }
    };
    it.each([
      ".app-next-form input:focus-visible { outline-offset: var(--app-ring-offset); }",
      ".notes textarea:focus-visible { outline-offset: var(--app-ring-offset); }",
      ".ui-select > select:focus-visible:not([data-pointer]) { outline-offset: var(--app-ring-offset); }",
      ".ui-search:focus-within { outline-offset: var(--app-ring-offset); }",
      '.x input[type="date"]:focus-within { outline-offset: var(--app-ring-offset); }',
      '.x input:is([type="time"], [type="date"]):focus-within { outline-offset: var(--app-ring-offset); }',
      ".x :is(input, textarea):focus-visible { outline-offset: var(--app-ring-offset); }",
      ".x :where(button, select):focus-visible { outline-offset: var(--app-ring-offset); }",
    ])("%s fails", (css) => {
      expect(check(css).length).toBeGreaterThan(0);
    });
    it.each([
      ".app-next-form input:focus-visible { outline-offset: calc(-1 * var(--app-ring-offset)); }",
      '.x input[type="checkbox"]:focus-visible { outline-offset: var(--app-ring-offset); }',
      ".x button:focus-visible { outline-offset: var(--app-ring-offset); }",
      ".x :is(button, a):focus-visible { outline-offset: var(--app-ring-offset); }",
      '.x input:is([type="checkbox"], [type="radio"]):focus-visible { outline-offset: var(--app-ring-offset); }',
    ])("%s passes", (css) => {
      expect(check(css)).toEqual([]);
    });
  });
});

describe("a list's cursor is the keyboard's place, and wears the ring", () => {
  // In the palette and FilterSelect focus stays in the field; the option Enter
  // acts on is marked by a class beside `aria-activedescendant`/`aria-selected`.
  // It wears the ring, inside, like a flush row; a tint does not reach 3:1.
  it.each([
    ["shell.css", ".palette-item.is-cursor"],
    ["ui/FilterSelect.css", ".ui-filterselect-option.ui-cursor"],
  ])("%s %s", (file, selector) => {
    const css = SHEETS.find((s) => s.file === file)!.css;
    const ringed = rules(css)
      .filter((r) => r.selectors.includes(selector))
      .some((r) =>
        r.decls.get("outline") === "var(--app-ring-width) solid var(--app-action)" &&
        r.decls.get("outline-offset") === "calc(-1 * var(--app-ring-offset))");
    expect(ringed, `${selector} draws no ring`).toBe(true);
  });
});

describe("the detectors fail the shapes they exist to catch", () => {
  // Negative controls: focus looks the gate must reject.
  const check = (css: string, file = "features/x.css") => {
    const saved = SHEETS.splice(0, SHEETS.length, { file, css });
    try { return audit(); } finally { SHEETS.splice(0, SHEETS.length, ...saved); }
  };
  it.each([
    ".chip-co:focus-visible { outline: 2px solid var(--app-action-line); outline-offset: 1px; }",
    ".ui-switch-track:focus-visible { outline: none; box-shadow: 0 0 0 3px var(--app-action-ring); }",
    ".job-row:focus-visible { outline: none; box-shadow: inset 3px 0 0 var(--app-action), 0 16px 34px -18px var(--app-action-glow); }",
    ".req-row:focus-visible { outline: 2px solid var(--app-information); outline-offset: 1px; }",
    ".ui-btn-danger:focus-visible { outline-color: var(--app-danger); }",
    ".x:focus-visible { outline: 2px solid #7c6c22; }",
  ])("%s fails", (css) => {
    const r = check(css);
    expect(r.paints.length + r.suppressions.length).toBeGreaterThan(0);
  });

  it("the ring itself, outside and inside, passes", () => {
    const r = check(".a:focus-visible { outline: var(--app-ring-width) solid var(--app-action); outline-offset: var(--app-ring-offset); }\n.b:focus-visible { outline: var(--app-ring-width) solid var(--app-action); outline-offset: calc(-1 * var(--app-ring-offset)); }");
    expect(r.paints).toEqual([]);
    expect(r.suppressions).toEqual([]);
  });
});

describe("the ring clears 3:1 wherever it lands", () => {
  const tokens = readFileSync(join(SRC, "design", "tokens.css"), "utf8");
  const shell = SHEETS.find((s) => s.file === "shell.css")!.css;
  const block = (css: string, start: string) => {
    const at = css.indexOf(start);
    return css.slice(css.indexOf("{", at) + 1, css.indexOf("}", at));
  };
  const hex = (b: string, name: string) => b.match(new RegExp(`${name}:\\s*(#[0-9a-f]{6})`, "i"))?.[1];
  const lum = (h: string) => {
    const n = parseInt(h.slice(1), 16);
    const c = [n >> 16, (n >> 8) & 255, n & 255].map((v) => {
      const s = v / 255;
      return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
  };
  const ratio = (a: string, b: string) => {
    const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
    return (x + 0.05) / (y + 0.05);
  };

  it.each([
    ["light", ":root {"],
    ["dark", ':root[data-theme="dark"] {'],
  ])("--app-action on every opaque ground (%s)", (_, start) => {
    const b = block(tokens, start);
    const ring = hex(b, "--app-action")!;
    for (const ground of ["--app-canvas", "--app-surface-raised", "--app-surface-subtle", "--app-surface-sunken"]) {
      expect(ratio(ring, hex(b, ground)!), `${ground}`).toBeGreaterThanOrEqual(3);
    }
  });

  it("--rail-accent on the rail, in both themes (the rail is dark in both)", () => {
    const b = block(shell, ".nav-rail {");
    expect(ratio(hex(b, "--rail-accent")!, hex(b, "--rail-canvas")!)).toBeGreaterThanOrEqual(3);
  });
});

/* The popover's shell takes focus on open; the ring it must not wear is the
 * app's global `[tabindex]:focus-visible` (shell.css), which loads after the
 * overlay's stylesheet. A tie in weight goes to whichever sheet comes last,
 * so the suppression must outweigh it outright. */
const weight = (selector: string) =>
  (selector.match(/\.[\w-]+|\[[^\]]+\]|:(?!:)[\w-]+/g) ?? []).length;

describe("the overlay shell's ring", () => {
  it("is switched off by a selector heavier than the global ring, whatever order the sheets load in", () => {
    const css = readFileSync(join(SRC, "ui", "Overlay.css"), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
    const rule = [...css.matchAll(/([^{}]+)\{([^}]*)\}/g)]
      .find(([, selector, body]) => selector.includes(".ui-overlay-content") && selector.includes(":focus-visible")
        && /outline:\s*none/.test(body));
    expect(rule).toBeDefined();
    expect(weight(rule![1].trim())).toBeGreaterThan(weight("[tabindex]:focus-visible"));
  });
});
