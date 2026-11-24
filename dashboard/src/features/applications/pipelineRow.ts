import { createContext } from "react";

/** The Pipeline's one row: its views at the start, and after them the tools
 *  of the view on screen. The place draws the row and keeps it while views
 *  change, so the tabs keep focus through a change of view; each view still
 *  owns its tools and draws them into `slot`. Both are null until the row is
 *  on the page. Undefined where a view stands with no place around it: its
 *  toolbar is then a row of its own. */
export interface PipelineRow {
  row: HTMLElement | null;
  slot: HTMLElement | null;
}

export const PipelineRowContext = createContext<PipelineRow | undefined>(undefined);
