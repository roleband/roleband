import { useEffect, useState } from "react";
import { api, type Job } from "../../api";
import type { AgentAccessState } from "../../api/intelligence";
import { companyName } from "../../format";
import { CopyField } from "../../ui/CopyField";
import { Icon } from "../../ui/Icon";
import { Popover } from "../../ui/Popover";
import { RouterLink } from "../../ui/RouterLink";
import {
  roleJobDetailTailorConnect,
  roleJobDetailTailorConnectLink,
  roleJobDetailTailorHeading,
  roleJobDetailTailorSay,
  roleJobDetailTailorSentence,
} from "../../copy/gen/role";

/** Settings › AI: where an assistant is connected. */
const SETTINGS_AI_PATH = "/settings/intelligence";

/** What the engine said about the person's assistant: one can take the
 *  hand-off, none is set up, or the engine could not be asked. Null while it
 *  has not answered. */
type Readiness = "ready" | "none" | "unknown";

function useAssistantReadiness(asked: boolean): Readiness | null {
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  useEffect(() => {
    if (!asked) return;
    let live = true;
    setReadiness(null);
    api.agentAccess().then(
      (state) => { if (live) setReadiness(assistantReady(state) ? "ready" : "none"); },
      () => { if (live) setReadiness("unknown"); },
    );
    return () => { live = false; };
  }, [asked]);
  return readiness;
}

/** Access is on and one app is set up (an outdated one still answers), or the
 *  open door has been called. */
function assistantReady(state: AgentAccessState): boolean {
  if (!state.enabled) return false;
  return state.apps.some((app) =>
    app.app === "other" ? app.last_call_at != null : app.connection === "connected" || app.connection === "outdated");
}

/**
 * Tailor CV hands the role to the person's assistant: one sentence to say to
 * it, in the copy control. The assistant reads the posting and the person's
 * background through the `roleband` command; no conversation happens here.
 * The role's number is in the sentence so the assistant reads this posting and
 * no other. With no assistant set up, the sentence gives way to the step that
 * sets one up; when the engine could not say, both show.
 */
export function TailorCvPopover({ job, anchor, onClose }: {
  job: Job;
  /** The control that opened it: the bar's Tailor CV or the end's first step. */
  anchor: HTMLElement | null;
  onClose: () => void;
}) {
  const open = anchor != null;
  const readiness = useAssistantReadiness(open);
  const sentence = roleJobDetailTailorSentence({ id: job.id, title: job.title, company: companyName(job.company) });
  const connect = (
    <RouterLink to={SETTINGS_AI_PATH} variant="link" onClick={onClose}>
      {roleJobDetailTailorConnectLink()} <Icon name="arrowRight" size={13} />
    </RouterLink>
  );

  return (
    <Popover isOpen={open} onClose={onClose} anchor={anchor} align="end" label={roleJobDetailTailorHeading()} className="app-overlay jd-tailor-pop">
      <h2>{roleJobDetailTailorHeading()}</h2>
      {readiness === "none" && (
        <>
          <p>{roleJobDetailTailorConnect()}</p>
          {connect}
        </>
      )}
      {(readiness === "ready" || readiness === "unknown") && (
        <>
          <p>{roleJobDetailTailorSay()}</p>
          <CopyField text={sentence} />
          {readiness === "unknown" && connect}
        </>
      )}
    </Popover>
  );
}
