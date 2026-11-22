import { useLocation } from "react-router-dom";
import type { ApplicationCard } from "../../api";
import { coverBackground, positionPath } from "../../routing/paths";
import { boardStage } from "./board";

export type RoleTab = "posting" | "workspace";

/** The tab a role opens on from the pipeline: its posting while it is being
 *  considered, the person's own work on it from then on. */
const firstTab = (card: Pick<ApplicationCard, "stage">): RoleTab =>
  boardStage(card.stage) === "saved" ? "posting" : "workspace";

/** A role's address when its company may not be known yet: the short form
 *  then, which rewrites itself to `positionPath` once the posting loads. */
export function roleAddress(id: number | string, companySlug?: string | null): string {
  return companySlug ? positionPath(companySlug, id) : `/job/${id}`;
}

/** The way to a role from a pipeline view: its posting, opened over the view
 *  so Back returns to the view as it was left. The tab is in the address, so
 *  the link names it. */
export function useRoleLink() {
  const location = useLocation();
  return (card: Pick<ApplicationCard, "job_id" | "company" | "stage">, tab: RoleTab = firstTab(card)) => ({
    to: { pathname: positionPath(card.company, card.job_id), search: `?tab=${tab}` },
    state: { backgroundLocation: coverBackground(location) },
  });
}
