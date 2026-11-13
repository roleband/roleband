/* The shape of a description section's text, for display only.
 *
 * A section's content is the employer's words as plain text: paragraphs apart
 * by a blank line, with the markup that set a list or a sub-heading gone. The
 * words are shown as stored; this reads their shape back from how the lines
 * are written, and where the signs are not clear a paragraph stays a
 * paragraph:
 *
 * - a line that opens with a bullet mark is a list item;
 * - a paragraph of three or more lines is a list, one item a line (the lines
 *   of a posting's list arrive this way when its items were not set apart);
 * - three or more one-line paragraphs in a row that do not end a sentence are
 *   a list (a posting's duties and requirements are written this way);
 * - a short one-line paragraph ending in a colon, with text after it, is a
 *   sub-heading;
 * - so is a title of a few words with no closing mark that stands alone
 *   before a paragraph of whole sentences or a list ("Team Leadership", then
 *   what the team's leader does).
 */

export type Block =
  | { kind: "heading"; text: string }
  | { kind: "list"; items: string[] }
  | { kind: "para"; lines: string[] };

/* An asterisk and a dash are a bullet only before a space: they also open
   an employer's own word ("*nix experience", "-40C"), and a mark stripped
   there would change what the posting says. */
const BULLET = /^\s*(?:[•·▪◦●○■]|[-–—*](?=\s))\s*/u;
const ENDS_SENTENCE = /[.!?…]["'”’)\]]*$/u;
/** How many lines, or one-line fragments in a row, read as a list. */
const LIST_RUN = 3;
const HEADING_MAX_CHARS = 80;
const HEADING_MAX_WORDS = 10;
/** A title with no colon has less to tell it from a short line of prose, so
 *  it is held to fewer words. */
const TITLE_MAX_WORDS = 6;
const TITLE_MAX_CHARS = 60;
const OPENS_TITLE = /^[\p{Lu}\p{N}]/u;
const TITLE_BREAKS = /[:;,]$|[.!?…:;]\s/u;

function paragraphs(content: string): string[][] {
  return content
    .split(/\n\s*\n/)
    .map((paragraph) => paragraph.split("\n").map((line) => line.trim()).filter(Boolean))
    .filter((lines) => lines.length > 0);
}

const isFragment = (lines: string[]): boolean =>
  lines.length === 1 && !ENDS_SENTENCE.test(lines[0]) && !lines[0].endsWith(":");

const isHeading = (lines: string[]): boolean =>
  lines.length === 1
  && lines[0].endsWith(":")
  && lines[0].length <= HEADING_MAX_CHARS
  && lines[0].split(/\s+/).length <= HEADING_MAX_WORDS;

/** A paragraph that reads as a title: one short line that opens with a
 *  capital or a number, closes with no mark and holds no sentence break. */
const isTitle = (lines: string[]): boolean =>
  isFragment(lines)
  && lines[0].length <= TITLE_MAX_CHARS
  && lines[0].split(/\s+/).length <= TITLE_MAX_WORDS
  && OPENS_TITLE.test(lines[0])
  && !BULLET.test(lines[0])
  && !TITLE_BREAKS.test(lines[0]);

/** What a title stands over: whole sentences, or a list. Another unfinished
 *  line after it leaves both as they are. */
const isBody = (lines: string[] | undefined): boolean =>
  lines !== undefined && (lines.length > 1 || BULLET.test(lines[0]) || ENDS_SENTENCE.test(lines[0]));

export function shapeBlocks(content: string): Block[] {
  const blocks: Block[] = [];
  const all = paragraphs(content);
  let at = 0;
  while (at < all.length) {
    const lines = all[at];
    // Bullet marks: every line of the paragraph, and of the ones that follow.
    if (lines.every((line) => BULLET.test(line))) {
      const items: string[] = [];
      while (at < all.length && all[at].every((line) => BULLET.test(line))) {
        items.push(...all[at].map((line) => line.replace(BULLET, "")));
        at += 1;
      }
      blocks.push({ kind: "list", items: items.filter(Boolean) });
      continue;
    }
    if (lines.length >= LIST_RUN) {
      blocks.push({ kind: "list", items: lines.map((line) => line.replace(BULLET, "")) });
      at += 1;
      continue;
    }
    let run = at;
    while (run < all.length && isFragment(all[run]) && !BULLET.test(all[run][0])) run += 1;
    if (run - at >= LIST_RUN) {
      blocks.push({ kind: "list", items: all.slice(at, run).map((one) => one[0]) });
      at = run;
      continue;
    }
    if (isHeading(lines) && at + 1 < all.length) {
      blocks.push({ kind: "heading", text: lines[0].replace(/\s*:$/, "") });
      at += 1;
      continue;
    }
    if (isTitle(lines) && isBody(all[at + 1])) {
      blocks.push({ kind: "heading", text: lines[0] });
      at += 1;
      continue;
    }
    blocks.push({ kind: "para", lines });
    at += 1;
  }
  return blocks;
}
