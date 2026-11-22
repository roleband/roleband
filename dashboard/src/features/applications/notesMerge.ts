/* Notes written in two places at once, put together line by line. Both
 * sides changed the same text the page started from: a stretch only one side
 * changed takes that side's lines; a stretch both changed differently keeps
 * both, the page's own lines first. Nothing either side wrote is lost. */

/** Past this many line pairs the lines are not matched one by one: the
 *  page's lines are kept, then the other side's lines the page lacks. */
const MATCH_LIMIT = 4_000_000;

/** The pairs of equal lines a longest common run of `a` and `b` matches, as
 *  index in `a` to index in `b`. */
function matches(a: readonly string[], b: readonly string[]): Map<number, number> {
  const width = b.length + 1;
  // run[i * width + j]: the longest common run of a[i..] and b[j..].
  const run = new Uint32Array((a.length + 1) * width);
  for (let i = a.length - 1; i >= 0; i -= 1) {
    for (let j = b.length - 1; j >= 0; j -= 1) {
      run[i * width + j] = a[i] === b[j]
        ? run[(i + 1) * width + j + 1] + 1
        : Math.max(run[(i + 1) * width + j], run[i * width + j + 1]);
    }
  }
  const pairs = new Map<number, number>();
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      pairs.set(i, j);
      i += 1;
      j += 1;
    } else if (run[(i + 1) * width + j] >= run[i * width + j + 1]) {
      i += 1;
    } else {
      j += 1;
    }
  }
  return pairs;
}

const same = (a: readonly string[], b: readonly string[]) => a.length === b.length && a.every((line, at) => line === b[at]);

/** The page's lines, then the other side's, a blank line between so
 *  neither runs into the other's paragraph. */
function apart(mine: readonly string[], theirs: readonly string[]): string[] {
  if (mine.length === 0) return [...theirs];
  if (theirs.length === 0) return [...mine];
  const gap = mine[mine.length - 1].trim() !== "" && theirs[0].trim() !== "";
  return [...mine, ...(gap ? [""] : []), ...theirs];
}

/** Both sides' lines for a stretch they changed differently: a line both
 *  wrote stands once, and where they differ the page's lines come first. */
function both(mine: readonly string[], theirs: readonly string[]): string[] {
  const out: string[] = [];
  let m = 0;
  let t = 0;
  for (const [at, to] of matches(mine, theirs)) {
    out.push(...apart(mine.slice(m, at), theirs.slice(t, to)), mine[at]);
    m = at + 1;
    t = to + 1;
  }
  out.push(...apart(mine.slice(m), theirs.slice(t)));
  return out;
}

/** The page's notes and the notes written elsewhere since `base`, the text
 *  both started from, as one text. */
export function mergeNotes(base: string, mine: string, theirs: string): string {
  if (mine === theirs || theirs === base) return mine;
  if (mine === base) return theirs;
  const start = base.split("\n");
  const page = mine.split("\n");
  const other = theirs.split("\n");
  if (start.length * Math.max(page.length, other.length) > MATCH_LIMIT) {
    const kept = new Set(page);
    return apart(page, other.filter((line) => !kept.has(line))).join("\n");
  }
  const toPage = matches(start, page);
  const toOther = matches(start, other);
  const out: string[] = [];
  let b = 0;
  let p = 0;
  let o = 0;
  // A line of the starting text both sides kept anchors the walk; between
  // two anchors each side's stretch is compared with the start's.
  for (let at = 0; at <= start.length; at += 1) {
    const end = at === start.length;
    if (!end && !(toPage.has(at) && toOther.has(at))) continue;
    const pageAt = end ? page.length : toPage.get(at)!;
    const otherAt = end ? other.length : toOther.get(at)!;
    const was = start.slice(b, at);
    const ours = page.slice(p, pageAt);
    const yours = other.slice(o, otherAt);
    if (same(ours, was)) out.push(...yours);
    else if (same(yours, was) || same(ours, yours)) out.push(...ours);
    else out.push(...both(ours, yours));
    if (!end) out.push(start[at]);
    b = at + 1;
    p = pageAt + 1;
    o = otherAt + 1;
  }
  return out.join("\n");
}
