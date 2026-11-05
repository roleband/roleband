import { Link } from "react-router-dom";
import { applicationsEmpty, applicationsEmptyHint, applicationsEmptyRadar, applicationsNoMatches } from "../../copy/gen/applications";
import { EmptyState } from "../../ui";

/* The pipeline's two empty states, the same in the Board, the List and Up
 * next: nothing saved yet, and filters that leave nothing to show. */

/** Nothing saved or pursued: where a role comes from, and the way there. */
export function PipelineEmpty() {
  return (
    <EmptyState
      title={applicationsEmpty()}
      actions={<Link className="ui-btn ui-btn-link" to="/">{applicationsEmptyRadar()}</Link>}
    >
      {applicationsEmptyHint()}
    </EmptyState>
  );
}

/** The view's filters leave nothing. The way back is the toolbar's Reset
 *  all, drawn whenever a filter is on, so the line carries no second one. */
export function NoMatches() {
  return <p className="app-no-matches">{applicationsNoMatches()}</p>;
}
