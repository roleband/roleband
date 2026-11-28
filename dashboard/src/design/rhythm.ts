/* Rhythm literals: bare px from 4 to 48 in a property that spaces or rounds a
 * box. Below 4px is a hairline or an optical nudge; above 48px is an SVG
 * dimension or a max-width. `geometry.test.ts` holds the sheets it enrols at
 * none, and `rhythm-literals.test.ts` lets every other sheet's count only fall,
 * both through this one reading. */

const strip = (source: string) => source.replace(/\/\*[\s\S]*?\*\//g, "");

const RHYTHM_PROPS = [
  "padding", "padding-top", "padding-right", "padding-bottom", "padding-left",
  "padding-inline", "padding-block",
  "margin", "margin-top", "margin-right", "margin-bottom", "margin-left",
  "margin-inline", "margin-block",
  "gap", "row-gap", "column-gap",
  "border-radius",
];

/** One entry per rhythm literal in a stylesheet's text. */
export function literalsIn(source: string): string[] {
  const out: string[] = [];
  for (const prop of RHYTHM_PROPS) {
    const re = new RegExp(`(?:^|[;{\\s])${prop}:\\s*([^;}]+)`, "g");
    for (const match of strip(source).matchAll(re)) {
      const value = match[1];
      if (/var\(|calc\(|clamp\(|env\(/.test(value)) continue;
      for (const px of value.matchAll(/(\d+(?:\.\d+)?)px/g)) {
        const n = Number(px[1]);
        if (n > 3 && n <= 48) out.push(`${prop}: ${value.trim()}`);
      }
    }
  }
  return out;
}
