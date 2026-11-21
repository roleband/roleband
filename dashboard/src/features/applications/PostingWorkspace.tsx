import { useState } from "react";
import type { Job } from "../../api";
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
  job: Job;
  onShowPosting: () => void;
}) {
  const [dismissed, setDismissed] = useState(readDismissed);
  const lifecycle = "lifecycle" in job && Array.isArray(job.lifecycle) ? job.lifecycle : [];
  const crossing = latestCrossing(lifecycle, workspace.detail.stages_reached);
  const crossingId = crossing ? crossingKey(job.id, crossing) : null;
  const dismiss = (key: string) => {
    const next = new Set(dismissed).add(key);
    writeDismissed(next);
    setDismissed(next);
  };

  return (
    <>
      {crossing && crossingId && !dismissed.has(crossingId) && (
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
