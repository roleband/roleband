import type { Job } from "../../api";
import { WORKPLACE_LABEL, companyName } from "../../format";

/* What the Details rows say. A row is shown only when the posting states the
   fact: an empty row reads as a fact that is missing, and a column of them
   hides the rows that do say something. */

const same = (a: string, b: string) => a.trim().toLowerCase() === b.trim().toLowerCase();

/** The team the posting names, else its department, or null when it names
 *  neither. Some employers fill a field with their own name, which says
 *  nothing the page's heading does not, so such a field counts as empty and
 *  the other one is read. */
export function postingTeam(job: Pick<Job, "team" | "department" | "company">): string | null {
  const says = (field: string | null | undefined) => {
    const value = field?.trim();
    return value && !same(value, job.company) && !same(value, companyName(job.company)) ? value : null;
  };
  return says(job.team) ?? says(job.department);
}

/** Where the work happens, in the reader's words, or null when the posting
 *  does not say. */
export function postingWorkplace(job: Pick<Job, "workplace_type">): string | null {
  if (job.workplace_type === "unknown") return null;
  return WORKPLACE_LABEL[job.workplace_type] ?? null;
}
