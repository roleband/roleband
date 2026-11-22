import { useState } from "react";
import type { ApplicationCard, ApplicationInterview } from "../../api";
import { Button, Content, ExternalLink, Icon, Menu, MenuGroup, MenuItem } from "../../ui";
import {
  applicationsInterviewAdd,
  applicationsInterviewEditLabel,
  applicationsNextInterviewJoin,
  applicationsNextInterviewJoinLabel,
  applicationsNextInterviewMeta,
  applicationsNextInterviewNone,
  applicationsUpnextOutcomeLabel,
  applicationsWsAskOutcome,
  applicationsWsRoundPrepare,
} from "../../copy/gen/applications";
import { AddToCalendar } from "./AddToCalendar";
import { FORMAT_LABEL, OUTCOME_LABEL, interviewPast, interviewWhen } from "./interviewWords";

export type Outcome = NonNullable<ApplicationInterview["outcome"]>;

function OutcomeAsk({ interview, onOutcome }: { interview: ApplicationInterview; onOutcome: (outcome: Outcome) => void }) {
  const [anchor, setAnchor] = useState<HTMLButtonElement | null>(null);
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button
        ref={setAnchor}
        variant="link"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen((was) => !was)}
      >
        {applicationsWsAskOutcome()}
      </Button>
      <Menu isOpen={open} onClose={() => setOpen(false)} anchor={anchor} label={applicationsUpnextOutcomeLabel({ label: interview.label })}>
        <MenuGroup>
          {(Object.keys(OUTCOME_LABEL) as Outcome[]).map((outcome) => (
            <MenuItem
              key={outcome}
              onSelect={() => {
                setOpen(false);
                onOutcome(outcome);
              }}
            >
              {OUTCOME_LABEL[outcome]()}
            </MenuItem>
          ))}
        </MenuGroup>
      </Menu>
    </>
  );
}

/** Every round: the ones to come first, soonest first, then the past ones,
 *  latest first. A round to come offers a file for the person's calendar and
 *  its call link, and with nothing written yet, the outline its notes start
 *  from; a past one asks how it went until the person says. */
export function Interviews({ interviews, role, now, onEdit, onOutcome }: {
  interviews: readonly ApplicationInterview[];
  role: Pick<ApplicationCard, "job_id" | "company" | "title">;
  now: Date;
  onEdit: (interview: ApplicationInterview, at?: "notes") => void;
  onOutcome: (interview: ApplicationInterview, outcome: Outcome) => void;
}) {
  const at = (one: ApplicationInterview) => new Date(one.scheduled_at).getTime();
  const coming = interviews.filter((one) => !interviewPast(one, now)).sort((a, b) => at(a) - at(b));
  const past = interviews.filter((one) => interviewPast(one, now)).sort((a, b) => at(b) - at(a));

  if (interviews.length === 0) return <p className="app-next-empty">{applicationsNextInterviewNone()}</p>;

  return (
    <ul className="app-ws-rounds">
      {[...coming, ...past].map((interview) => {
          const upcoming = !interviewPast(interview, now);
          const when = interview.format
            ? applicationsNextInterviewMeta({ when: interviewWhen(interview, now), format: FORMAT_LABEL[interview.format]() })
            : interviewWhen(interview, now);
          return (
            <li key={interview.id} className="app-ws-round" data-past={upcoming ? undefined : true}>
              <div className="app-ws-round-head">
                <span className="app-ws-round-name"><Content text={interview.label} /></span>
                <span className="app-ws-round-when">{when}</span>
                <Button
                  variant="icon"
                  size="sm"
                  className="app-row-tool"
                  aria-label={applicationsInterviewEditLabel({ label: interview.label })}
                  onClick={() => onEdit(interview)}
                >
                  <Icon name="edit" size={14} />
                </Button>
                <span className="app-tile-spacer" />
                {upcoming && <AddToCalendar interview={interview} role={role} />}
                {upcoming && interview.link && (
                  <ExternalLink href={interview.link} label={applicationsNextInterviewJoinLabel({ label: interview.label })}>
                    {applicationsNextInterviewJoin()}
                  </ExternalLink>
                )}
                {!upcoming && !interview.outcome && <OutcomeAsk interview={interview} onOutcome={(outcome) => onOutcome(interview, outcome)} />}
                {interview.outcome && <span className="app-ws-round-outcome">{OUTCOME_LABEL[interview.outcome]()}</span>}
              </div>
              {interview.notes ? (
                <p className="app-ws-round-notes"><Content text={interview.notes} /></p>
              ) : upcoming && (
                <Button variant="link" className="ui-btn-quiet app-ws-round-prepare" onClick={() => onEdit(interview, "notes")}>
                  {applicationsWsRoundPrepare()}
                </Button>
              )}
            </li>
          );
        })}
    </ul>
  );
}

/** The Interviews block's one action, at the card's top right. */
export function AddInterview({ onAdd }: { onAdd: () => void }) {
  return (
    <Button variant="link" className="ui-btn-quiet app-ws-action" onClick={onAdd}>
      <Icon name="plus" size={14} />
      {applicationsInterviewAdd()}
    </Button>
  );
}
