import { useId, useState } from "react";
import type { Job } from "../../api";
import { domainName } from "../../copy/vocab";
import { Button } from "../../ui/Button";
import { Icon } from "../../ui/Icon";
import {
  roleJobDetailAdvisoryBasis,
  roleJobDetailAdvisoryUnclear,
  roleJobDetailHardToPlace,
  roleJobDetailLikelyOutsideYourWorlds,
  roleJobDetailLikelyYourKindOfRole,
  roleJobDetailRadarSRead,
} from "../../copy/gen/role";

type Review = NonNullable<Job["relevance_review"]>;

function verdict(review: Review): string {
  if (review.relevance === "relevant") return roleJobDetailLikelyYourKindOfRole();
  if (review.relevance === "irrelevant") return roleJobDetailLikelyOutsideYourWorlds();
  return roleJobDetailHardToPlace();
}

/** The verdict with its world, as the card heads it and the fold names it. */
function Verdict({ review }: { review: Review }) {
  return (
    <>
      {verdict(review)}
      {review.domain && <span className="jd-advisory-domain"> · {domainName(review.domain)}</span>}
    </>
  );
}

/** The read's card. Under its fold the verdict is already the fold's words,
 *  so the card opens on what follows it. */
function Advisory({ review, id, headed = true }: { review: Review; id?: string; headed?: boolean }) {
  return (
    // Advisory only: it never gates anything. The stored rationale, model and
    // confidence stay in the API for the bench; the confidence is
    // margin-derived, not a probability, so no figure reaches the reader.
    <div className="jd-advisory" data-relevance={review.relevance} id={id}>
      {headed && (
        <div className="jd-advisory-verdict">
          <Verdict review={review} />
        </div>
      )}
      {review.relevance === "uncertain" && <p className="jd-advisory-rationale">{roleJobDetailAdvisoryUnclear()}</p>}
      <div className="jd-advisory-meta">{roleJobDetailAdvisoryBasis()}</div>
    </div>
  );
}

/**
 * The radar's read of a posting: a guess that helps the person decide. While
 * they decide it leads the side column in full; once they have applied it has
 * done its work, and `folded` says only its verdict, opening on a press.
 */
export function RadarRead({ review, folded }: { review: Review; folded: boolean }) {
  const [open, setOpen] = useState(false);
  const panel = useId();
  return (
    <>
      <div className="section-title">{roleJobDetailRadarSRead()}</div>
      {folded ? (
        <>
          <Button
            variant="ghost"
            size="sm"
            className="jd-advisory-fold"
            aria-expanded={open}
            aria-controls={open ? panel : undefined}
            onClick={() => setOpen((was) => !was)}
          >
            <Verdict review={review} />
            <Icon name={open ? "chevronUp" : "chevronDown"} size={13} />
          </Button>
          {open && <Advisory review={review} id={panel} headed={false} />}
        </>
      ) : (
        <Advisory review={review} />
      )}
    </>
  );
}
