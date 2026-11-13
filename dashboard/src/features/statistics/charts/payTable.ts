import type { PayTableRow } from "../../../api";

/** A company's posted ranges as text, for the strip's screen-reader label:
 *  every distinct range it posts, widest-paying first, as the server orders
 *  them. The strip draws a picture; this says the same in words. */
export function payRanges(row: PayTableRow, money: (amount: number) => string): string {
  return row.ranges.map((r) => `${money(r.low)}–${money(r.high)}`).join(", ");
}

/** How many companies the row cap hides that post no range at this level, so
 *  the table can say they are hiring without one. Rows are sorted with every
 *  posted range first, so these are always the tail. */
export function silentBelow(matched: readonly PayTableRow[], shown: number): number {
  return matched.slice(shown).filter((row) => row.low == null).length;
}
