import type { ApplicationCard, ApplicationInterview } from "../../api";
import { applicationsInterviewCalendar, applicationsInterviewCalendarLabel } from "../../copy/gen/applications";
import { Button, Icon } from "../../ui";
import { interviewCalendar, interviewCalendarName, saveCalendarFile } from "./interviewCalendar";

/** Saves one round to come as a file the person's calendar app imports. */
export function AddToCalendar({ interview, role }: {
  interview: Pick<ApplicationInterview, "id" | "label" | "scheduled_at" | "all_day" | "format" | "link">;
  role: Pick<ApplicationCard, "job_id" | "company" | "title">;
}) {
  return (
    <Button
      variant="link"
      className="ui-btn-quiet"
      aria-label={applicationsInterviewCalendarLabel({ label: interview.label })}
      onClick={() => saveCalendarFile(
        interviewCalendarName(interview, role),
        interviewCalendar(interview, role, window.location.origin, new Date()),
      )}
    >
      <Icon name="calendar" size={14} />
      {applicationsInterviewCalendar()}
    </Button>
  );
}
