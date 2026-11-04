import type { ReactNode } from "react";
import { jobsSortBy, jobsSortByAscending, jobsSortByDescending } from "../../copy/gen/jobs";
import { Icon } from "../../ui";
import "./job-row.css";

/** A column header that sorts its list: the label, and an arrow for the
 *  direction while it is the sort in force. Pressed while in force, with the
 *  direction in the name, which every reader announces. A real table puts
 *  `aria-sort` on its header cell as well; a header strip of divs cannot. */
export function SortButton({ shown, spoken, active, order, onSort }: {
  /** What the header shows: its words, or an abbreviation of them. */
  shown: ReactNode;
  /** The words the name says. */
  spoken: string;
  active: boolean;
  order: "asc" | "desc";
  onSort: () => void;
}) {
  return (
    <button
      type="button"
      className="col-sort"
      aria-pressed={active}
      aria-label={active ? (order === "asc" ? jobsSortByAscending : jobsSortByDescending)({ label: spoken }) : jobsSortBy({ label: spoken })}
      onClick={onSort}
    >
      {shown}
      <span className="col-sort-arrow" aria-hidden="true">
        {active && <Icon name={order === "asc" ? "arrowUp" : "arrowDown"} size={11} />}
      </span>
    </button>
  );
}
