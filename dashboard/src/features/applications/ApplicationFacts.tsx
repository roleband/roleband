import type { ReactNode } from "react";
import type { ApplicationCard, ApplicationDetail, ApplicationInterview, JobDetail } from "../../api";
import { date as formatDate, list, relative } from "../../copy/format";
import { fmtCompIn, relDays } from "../../format";
import { JobLinkRow } from "../../patterns/jobs/JobLinkRow";
import { postingPlaces } from "../../patterns/jobs/location";
import { Badge, Button, Content, Icon, Segmented } from "../../ui";
import {
  applicationsFactApplied,
  applicationsFactAppliedNot,
  applicationsFactDays,
  applicationsFactDaysValue,
  applicationsFactFirstSeen,
  applicationsFactLastActivity,
  applicationsFactListedFor,
  applicationsFactLocation,
  applicationsFactLocationMore,
  applicationsFactPay,
  applicationsFactPayChanged,
  applicationsFactPayNone,
  applicationsFactPriority,
  applicationsFactStarred,
  applicationsFactStarredNo,
  applicationsFactStarredYes,
  applicationsFactStatus,
  applicationsFactStatusClosed,
  applicationsFactStatusOpen,
  applicationsFactsApplication,
  applicationsFactsInterviews,
  applicationsFactsPosting,
  applicationsInterviewAdd,
  applicationsInterviewEditLabel,
  applicationsInterviewOutcomeCancelled,
  applicationsInterviewOutcomeNotPassed,
  applicationsInterviewOutcomePassed,
  applicationsReadPosting,
} from "../../copy/gen/applications";
import { interviewWhen } from "./ApplicationPanels";
import { daysInStage } from "./board";
import { payChangedSinceApplied } from "./crossings";

const PRIORITIES = ["1", "2", "3", "4", "5"] as const;

const OUTCOME: Record<NonNullable<ApplicationInterview["outcome"]>, { tone: "success" | "danger" | "neutral"; label: () => string }> = {
  passed: { tone: "success", label: applicationsInterviewOutcomePassed },
  not_passed: { tone: "danger", label: applicationsInterviewOutcomeNotPassed },
  cancelled: { tone: "neutral", label: applicationsInterviewOutcomeCancelled },
};

function Fact({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div className="app-fact">
      <dt>{term}</dt>
      <dd>{children}</dd>
    </div>
  );
}

/** The posting's stated pay band, in its own currency. */
function postedPay(posting: JobDetail): string | null {
  const band = posting.disclosed_comp;
  const currency = band?.currency;
  if (!band || !currency || (band.base_min == null && band.base_max == null)) return null;
  const ends = [band.base_min, band.base_max].filter((value): value is number => value != null);
  const [low, high] = [ends[0], ends[ends.length - 1]];
  return low === high ? fmtCompIn(low, currency) : `${fmtCompIn(low, currency)}–${fmtCompIn(high, currency)}`;
}

export interface ApplicationFactsProps {
  card: ApplicationCard;
  detail: ApplicationDetail;
  posting: JobDetail | null;
  now: Date;
  onPriority: (priority: number) => void;
  onOpenPosting: (jobId: number, company?: string | null) => void;
  onAddInterview: () => void;
  onEditInterview: (interview: ApplicationInterview) => void;
}

/** The page's right column: the application's own facts, the posting's,
 *  and every interview. Each property edits where it stands. */
export function ApplicationFacts({
  card, detail, posting, now, onPriority, onOpenPosting, onAddInterview, onEditInterview,
}: ApplicationFactsProps) {
  const days = daysInStage(card, now);
  const applied = detail.stages_reached.find((step) => step.stage === "applied");
  const pay = posting ? postedPay(posting) : null;
  const places = posting ? postingPlaces(posting.locations) : [];
  const interviews = [...detail.interviews].sort(
    (a, b) => new Date(b.scheduled_at).getTime() - new Date(a.scheduled_at).getTime(),
  );

  return (
    <aside className="app-facts">
      <section className="app-facts-group" aria-labelledby="app-facts-application">
        <h2 id="app-facts-application" className="app-panel-title">{applicationsFactsApplication()}</h2>
        <dl>
          <Fact term={applicationsFactPriority()}>
            <Segmented
              className="app-priority"
              label={applicationsFactPriority()}
              value={String(card.priority) as (typeof PRIORITIES)[number]}
              onChange={(value) => onPriority(Number(value))}
              options={PRIORITIES.map((value) => ({ value, label: value }))}
            />
          </Fact>
          {days != null && <Fact term={applicationsFactDays()}>{applicationsFactDaysValue({ days })}</Fact>}
          <Fact term={applicationsFactApplied()}>
            {applied ? formatDate(applied.at, "full") : applicationsFactAppliedNot()}
          </Fact>
          <Fact term={applicationsFactStarred()}>
            {card.starred ? applicationsFactStarredYes() : applicationsFactStarredNo()}
          </Fact>
          {card.last_activity_at && (
            <Fact term={applicationsFactLastActivity()}>
              {relative((new Date(card.last_activity_at).getTime() - now.getTime()) / 1000)}
            </Fact>
          )}
        </dl>
      </section>

      <section className="app-facts-group" aria-labelledby="app-facts-posting">
        <h2 id="app-facts-posting" className="app-panel-title">{applicationsFactsPosting()}</h2>
        <dl>
          <Fact term={applicationsFactStatus()}>
            {card.posting_status === "closed"
              ? <Badge tone="warning" variant="tint" size="sm">{applicationsFactStatusClosed()}</Badge>
              : applicationsFactStatusOpen()}
          </Fact>
          {posting && (
            <>
              <Fact term={applicationsFactPay()}>
                {pay ?? applicationsFactPayNone()}
                {pay && payChangedSinceApplied(posting.lifecycle, detail.stages_reached) && (
                  <Badge tone="warning" variant="tint" size="sm" className="app-fact-tag">{applicationsFactPayChanged()}</Badge>
                )}
              </Fact>
              {places.length > 0 && (
                <Fact term={applicationsFactLocation()}>
                  <Content text={places[0]} />
                  {places.length > 1 && (
                    <span className="app-fact-more" title={list(places)}>
                      {applicationsFactLocationMore({ count: places.length - 1 })}
                    </span>
                  )}
                </Fact>
              )}
              <Fact term={applicationsFactFirstSeen()}>{formatDate(posting.first_seen, "full")}</Fact>
              {posting.listed_days != null && (
                <Fact term={applicationsFactListedFor()}>{relDays(posting.listed_days)}</Fact>
              )}
            </>
          )}
        </dl>
        <JobLinkRow
          jobId={card.job_id}
          company={card.company}
          onOpen={onOpenPosting}
          className="ui-btn ui-btn-ghost ui-btn-sm ui-btn-strong app-read-posting"
        >
          {applicationsReadPosting()}
        </JobLinkRow>
      </section>

      <section className="app-facts-group" aria-labelledby="app-facts-interviews">
        <div className="app-panel-head">
          <h2 id="app-facts-interviews" className="app-panel-title">{applicationsFactsInterviews()}</h2>
          <Button variant="icon" size="sm" aria-label={applicationsInterviewAdd()} aria-keyshortcuts="i" onClick={onAddInterview}>
            <Icon name="plus" size={14} />
          </Button>
        </div>
        {/* With none, the heading and its plus stand alone: Next says no
            interview is booked, beside the way to add one. */}
        {interviews.length > 0 && (
          <ul className="app-interviews">
            {interviews.map((interview) => (
              <li key={interview.id} className="app-interview">
                <div className="app-interview-what">
                  <span className="app-next-name"><Content text={interview.label} /></span>
                  <span className="app-next-meta">{interviewWhen(interview)}</span>
                </div>
                {interview.outcome && (
                  <Badge tone={OUTCOME[interview.outcome].tone} variant="tint" size="sm">
                    {OUTCOME[interview.outcome].label()}
                  </Badge>
                )}
                <Button
                  variant="icon"
                  size="sm"
                  aria-label={applicationsInterviewEditLabel({ label: interview.label })}
                  onClick={() => onEditInterview(interview)}
                >
                  <Icon name="edit" size={14} />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </aside>
  );
}
