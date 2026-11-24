import type { ApplicationCard, ApplicationInterview } from "../../api";
import { Button, Content, ExternalLink, Icon } from "../../ui";
import {
  applicationsInterviewAdd,
  applicationsInterviewEditLabel,
  applicationsNextInterviewJoin,
  applicationsNextInterviewJoinLabel,
  applicationsNextInterviewMeta,
  applicationsWsRoundPrepare,
} from "../../copy/gen/applications";
import { AddToCalendar } from "./AddToCalendar";
import { OutcomeAsk, type Outcome } from "./OutcomeAsk";
import { FORMAT_LABEL, OUTCOME_LABEL, interviewPast, interviewWhen } from "./interviewWords";


/** Every round: the ones to come first, soonest first, then the past ones,
 *  latest first. A round to come offers a file for the person's calendar and
 *  its call link, and with nothing written yet, the outline its notes start
 *  from; a past one asks how it went until the person says. */
export function Interviews({ interviews, role, now, onAdd, onEdit, onOutcome }: {
  interviews: readonly ApplicationInterview[];
  role: Pick<ApplicationCard, "job_id" | "company" | "title">;
  now: Date;
  onAdd: () => void;
  onEdit: (interview: ApplicationInterview, at?: "notes") => void;
  onOutcome: (interview: ApplicationInterview, outcome: Outcome) => void;
}) {
  const at = (one: ApplicationInterview) => new Date(one.scheduled_at).getTime();
  const coming = interviews.filter((one) => !interviewPast(one, now)).sort((a, b) => at(a) - at(b));
  const past = interviews.filter((one) => interviewPast(one, now)).sort((a, b) => at(b) - at(a));

  // With no round yet the block is its one line: the way to add one.
  if (interviews.length === 0) return <AddInterview onAdd={onAdd} />;

  return (
    <>
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
                {upcoming && <AddToCalendar interview={interview} role={role} />}
                <span className="app-tile-spacer" />
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
    <AddInterview onAdd={onAdd} />
    </>
  );
}

/** The Interviews block's one action, at the card's top right. */
/** The block's add line, under its rounds: a plus where a step's tick
 *  stands, and the words. */
function AddInterview({ onAdd }: { onAdd: () => void }) {
  return (
    <Button variant="link" className="ui-btn-quiet app-ws-addline" onClick={onAdd}>
      <Icon name="plus" size={14} />
      {applicationsInterviewAdd()}
    </Button>
  );
}
