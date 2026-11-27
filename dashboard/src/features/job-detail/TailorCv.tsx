import { useEffect, useState } from "react";
import { api, type Job } from "../../api";
import type { AgentAccessState } from "../../api/intelligence";
import { companyName } from "../../format";
import { Button } from "../../ui/Button";
import { Icon } from "../../ui/Icon";
import { Popover } from "../../ui/Popover";
import { RouterLink } from "../../ui/RouterLink";
import {
  roleJobDetailTailorConnect,
  roleJobDetailTailorConnectLink,
  roleJobDetailTailorCopy,
  roleJobDetailTailorCopyBlocked,
  roleJobDetailTailorHeading,
  roleJobDetailTailorSay,
  roleJobDetailTailorSentence,
} from "../../copy/gen/role";

/** Settings › AI: where an assistant is connected. */
const SETTINGS_AI_PATH = "/settings/intelligence";

/** Whether an assistant can take the hand-off: access is on and one app is
 *  set up (an outdated one still answers), or the open door has been called.
 *  Null until the engine has answered. */
function useAssistantReady(asked: boolean): boolean | null {
  const [ready, setReady] = useState<boolean | null>(null);
  useEffect(() => {
    if (!asked) return;
    let live = true;
    api.agentAccess().then(
      (state) => { if (live) setReady(assistantReady(state)); },
      () => { if (live) setReady(null); },
    );
    return () => { live = false; };
  }, [asked]);
  return ready;
}

function assistantReady(state: AgentAccessState): boolean {
  if (!state.enabled) return false;
  return state.apps.some((app) =>
    app.app === "other" ? app.last_call_at != null : app.connection === "connected" || app.connection === "outdated");
}

/**
 * Tailor CV hands the role to the person's assistant: one sentence to say to
 * it, with Copy. The assistant reads the posting and the person's background
 * through the `roleband` command; no conversation happens here. The role's
 * number is in the sentence so the assistant reads this posting and no other.
 * With no assistant set up, the sentence gives way to the step that sets one up.
 */
export function TailorCvPopover({ job, anchor, onClose }: {
  job: Job;
  /** The control that opened it: the bar's Tailor CV or the end's first step. */
  anchor: HTMLElement | null;
  onClose: () => void;
}) {
  const open = anchor != null;
  const ready = useAssistantReady(open);
  const [copied, setCopied] = useState(false);
  const [blocked, setBlocked] = useState(false);
  useEffect(() => {
    if (!open) {
      setCopied(false);
      setBlocked(false);
    }
  }, [open]);
  const sentence = roleJobDetailTailorSentence({ id: job.id, title: job.title, company: companyName(job.company) });
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(sentence);
      setCopied(true);
      setBlocked(false);
    } catch {
      setBlocked(true);
    }
  };

  return (
    <Popover isOpen={open} onClose={onClose} anchor={anchor} align="end" label={roleJobDetailTailorHeading()} className="app-overlay jd-tailor-pop">
      <h2>{roleJobDetailTailorHeading()}</h2>
      {ready === false ? (
        <>
          <p>{roleJobDetailTailorConnect()}</p>
          <RouterLink to={SETTINGS_AI_PATH} variant="link" onClick={onClose}>
            {roleJobDetailTailorConnectLink()} <Icon name="arrowRight" size={13} />
          </RouterLink>
        </>
      ) : (
        <>
          <p>{roleJobDetailTailorSay()}</p>
          <div className="jd-tailor-say">
            <span>{sentence}</span>
            <Button size="sm" onClick={() => void copy()}>
              <Icon name={copied ? "check" : "copy"} size={13} />
              {roleJobDetailTailorCopy({ choice: copied ? "yes" : "no" })}
            </Button>
          </div>
          {blocked && <p role="alert">{roleJobDetailTailorCopyBlocked()}</p>}
        </>
      )}
    </Popover>
  );
}
