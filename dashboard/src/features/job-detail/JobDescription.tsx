import { useRef, type ReactNode } from "react";
import type { JobDescriptionSection } from "../../api";
import { commonTryAgain } from "../../copy/gen/common";
import {
  roleJobDescriptionArrived,
  roleJobDescriptionNoDescriptionCaptured,
  roleJobDescriptionOpenPosting,
  roleJobDescriptionReadFailed,
  roleJobDescriptionReading,
  roleJobDescriptionReadingProgress,
  roleJobDescriptionReadingSlow,
} from "../../copy/gen/role";
import { ownHeading } from "../../copy/vocab";
import { Button } from "../../ui/Button";
import { Content } from "../../ui/Content";
import { ExternalLink } from "../../ui/ExternalLink";
import { ProgressBar } from "../../ui/ProgressBar";
import { shapeBlocks } from "./descriptionShape";
import type { TextRead } from "./postingText";
import { useStuckHeadings } from "./stuckHeadings";

const LIST_SECTIONS = new Set(["minimum_qualifications", "preferred_qualifications"]);

export function JobDescription({
  sections,
  fallback,
  read = null,
  arrived = false,
  company,
  postingUrl,
}: {
  sections?: JobDescriptionSection[];
  fallback?: string | null;
  /** The posting opened with no text and its text is being read: shown in
   *  the text's place until it lands (`usePostingText`). */
  read?: TextRead | null;
  /** The text landed from a read made while the posting was open: it comes
   *  in, rather than standing there as if it always had. */
  arrived?: boolean;
  /** The company's name, for the lines said while the text is read. */
  company?: string;
  /** The posting on the employer's site, offered when the read is slow or failed. */
  postingUrl?: string | null;
}) {
  const list = useRef<HTMLDivElement>(null);
  useStuckHeadings(list, sections);
  const landing = arrived ? " jd-arrived" : "";
  const hasText = Boolean(sections?.length || fallback);
  // One live region from the read's first line to the text: it stays mounted
  // where the line stood, so the change that matters most, the text coming in,
  // is said too. The text itself stays out of it; a region reads all it holds.
  const said = !hasText && read
    ? <TextReadState read={read} company={company ?? ""} postingUrl={postingUrl} />
    : hasText && arrived
      ? <span className="sr-only">{roleJobDescriptionArrived({ company: company ?? "" })}</span>
      : null;
  const status = (read || arrived) && <div className="jd-status" role="status">{said}</div>;

  let body: ReactNode = null;
  if (sections?.length) {
    body = (
      <div className={`jd-sections${landing}`} ref={list}>
        {sections.map((section, index) => (
          <section className={`jd-section jd-section-${section.key}`} key={`${section.key}-${index}`}>
            <h2>{ownHeading(section.key, section.title) ?? <Content text={section.title} />}</h2>
            {LIST_SECTIONS.has(section.key) ? (
              <ul>
                {section.content
                  .split(/\n+/)
                  .map((line) => line.trim())
                  .filter(Boolean)
                  .map((line, lineIndex) => <li key={lineIndex}><Content text={line} /></li>)}
              </ul>
            ) : (
              shapeBlocks(section.content).map((block, blockIndex) => {
                if (block.kind === "heading") return <h3 key={blockIndex}><Content text={block.text} /></h3>;
                if (block.kind === "list") {
                  return (
                    <ul key={blockIndex}>
                      {block.items.map((item, itemIndex) => <li key={itemIndex}><Content text={item} /></li>)}
                    </ul>
                  );
                }
                return (
                  <p key={blockIndex}>
                    {block.lines.map((line, lineIndex) => (
                      <span key={lineIndex}>
                        {lineIndex > 0 && <br />}
                        <Content text={line} />
                      </span>
                    ))}
                  </p>
                );
              })
            )}
          </section>
        ))}
      </div>
    );
  } else if (fallback) {
    body = <div className={`jd jd-fallback${landing}`}><Content text={fallback} /></div>;
  } else if (!read) {
    body = <p className="jd-empty">{roleJobDescriptionNoDescriptionCaptured()}</p>;
  }
  return (
    <>
      {body}
      {status}
    </>
  );
}

/** The text's place while it is read: a running line and what is happening,
 *  then, once the site is slow, the posting on it, and once the read failed,
 *  Try again beside it. It stands in the description's live region, so a
 *  screen reader hears each change of what is said and not the moving line.
 *  Drawn after 200 ms, the app's moment for any loading state, so a quick
 *  read never flashes it. */
function TextReadState({ read, company, postingUrl }: { read: TextRead; company: string; postingUrl?: string | null }) {
  const waiting = read.phase !== "failed";
  const line =
    read.phase === "reading"
      ? roleJobDescriptionReading({ company })
      : read.phase === "slow"
        ? roleJobDescriptionReadingSlow({ company })
        : roleJobDescriptionReadFailed({ company });
  return (
    <div className="jd-read" data-phase={read.phase}>
      {waiting && <ProgressBar label={roleJobDescriptionReadingProgress()} />}
      <p className="jd-read-line">{line}</p>
      {read.phase !== "reading" && (
        <div className="jd-read-actions">
          {read.phase === "failed" && (
            <Button size="sm" onClick={read.retry}>{commonTryAgain()}</Button>
          )}
          {postingUrl && <ExternalLink href={postingUrl}>{roleJobDescriptionOpenPosting({ company })}</ExternalLink>}
        </div>
      )}
    </div>
  );
}
