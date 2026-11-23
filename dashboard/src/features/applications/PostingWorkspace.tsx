import type { Job, JobDetail } from "../../api";
import { useViewChoices, useViewChoicesAnswered } from "../../hooks/viewChoices";
import { Button, Icon } from "../../ui";
import {
  applicationsCrossingClosed,
  applicationsCrossingDismiss,
  applicationsCrossingPay,
  applicationsCrossingReopened,
  applicationsReadPosting,
} from "../../copy/gen/applications";
import { crossingKey, latestCrossing, readDismissed, writeDismissed, type Crossing } from "./crossings";
import { Workspace, type WorkspaceProps } from "./Workspace";
import "./applications.css";

const CROSSING_TEXT: Record<Crossing["kind"], (args: { days: number }) => string> = {
  closed: applicationsCrossingClosed,
  reopened: applicationsCrossingReopened,
  pay: applicationsCrossingPay,
};

/**
 * A posting's Workspace tab: what changed on the posting since the person
 * applied, when something did and they have not put it away, then their own
 * work on the role. Its own chunk, which carries the pipeline's stylesheet,
 * so a posting outside the pipeline loads none of it.
 */
export default function PostingWorkspace({ job, onShowPosting, ...workspace }: WorkspaceProps & {
  /** The detail carries the posting's lifecycle; the row alone has none. */
  job: Job | JobDetail;
  onShowPosting: () => void;
}) {
  // Read each render from the view choices: a read that answers late shows
  // what was put away. Until it answers the line waits, so putting one away
  // always adds to what was put away before and never replaces it.
  useViewChoices();
  const answered = useViewChoicesAnswered();
  const dismissed = readDismissed();
  const lifecycle = ("lifecycle" in job && job.lifecycle) || [];
  const crossing = latestCrossing(lifecycle, workspace.detail.stages_reached);
  const crossingId = crossing ? crossingKey(job.id, crossing) : null;
  const dismiss = (key: string) => writeDismissed(new Set(readDismissed()).add(key));

  return (
    <>
      {answered && crossing && crossingId && !dismissed.has(crossingId) && (
        <div className="app-alert" role="status">
          <Icon name="info" size={16} />
          <span className="app-alert-text">{CROSSING_TEXT[crossing.kind]({ days: crossing.days })}</span>
          <Button variant="link" onClick={onShowPosting}>{applicationsReadPosting()}</Button>
          <Button variant="icon" size="sm" aria-label={applicationsCrossingDismiss()} onClick={() => dismiss(crossingId)}>
            <Icon name="close" size={14} />
          </Button>
        </div>
      )}
      <Workspace {...workspace} />
    </>
  );
}
