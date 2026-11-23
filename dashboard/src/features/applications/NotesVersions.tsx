import { useEffect, useState } from "react";
import type { NotesVersion } from "../../api";
import { timestamp } from "../../copy/format";
import {
  applicationsCommentAuthorAgent,
  applicationsCommentAuthorYou,
  applicationsNotesVersionPutBack,
  applicationsNotesVersionPutBackLabel,
  applicationsNotesVersions,
  applicationsNotesVersionsFailed,
  applicationsNotesVersionsLoading,
  applicationsNotesVersionsNone,
} from "../../copy/gen/applications";
import { Button, Content, Icon, Popover, ResourceLoadState } from "../../ui";

/** A day and a time: several versions can come from one day. */
const SAVED_AT: Intl.DateTimeFormatOptions = { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" };

/** A version's first lines as plain words, the marks that start a line left
 *  out: enough to tell one version from another. */
function versionPreview(text: string): string {
  return text
    .split("\n")
    .map((line) => line.replace(/^\s*(?:#{1,3}|[-*+]|\d+\.|>)\s+(?:\[[ xX]\]\s+)?/, "").trim())
    .filter((line) => line && !/^(?:-{3,}|\*{3,})$/.test(line))
    .slice(0, 3)
    .join(" · ");
}

/** The notes' earlier versions, one per writing session, newest first, each
 *  put back onto the page by its button. Read when the list opens, so it
 *  holds the session that just ended too. */
export function NotesVersions({ load, onPutBack }: {
  load: () => Promise<NotesVersion[]>;
  /** Puts this text back on the page, as an edit of the page's own. */
  onPutBack: (text: string, when: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [anchor, setAnchor] = useState<HTMLButtonElement | null>(null);
  const [versions, setVersions] = useState<NotesVersion[] | "failed" | null>(null);

  useEffect(() => {
    if (!open) return;
    let live = true;
    setVersions(null);
    load().then(
      (read) => live && setVersions(read),
      () => live && setVersions("failed"),
    );
    return () => {
      live = false;
    };
  }, [open, load]);

  return (
    <>
      <Button
        ref={setAnchor}
        variant="link"
        className="ui-btn-quiet app-notes-versions-open"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen((was) => !was)}
      >
        <Icon name="clock" size={14} />
        {applicationsNotesVersions()}
      </Button>
      <Popover isOpen={open} onClose={() => setOpen(false)} anchor={anchor} label={applicationsNotesVersions()} className="app-overlay app-notes-versions">
        <h3>{applicationsNotesVersions()}</h3>
        {versions === null && <ResourceLoadState error={null} loading={applicationsNotesVersionsLoading()} />}
        {versions === "failed" && <p className="app-notes-versions-note" role="alert">{applicationsNotesVersionsFailed()}</p>}
        {Array.isArray(versions) && versions.length === 0 && <p className="app-notes-versions-note">{applicationsNotesVersionsNone()}</p>}
        {Array.isArray(versions) && versions.length > 0 && (
          <ul className="app-notes-versions-list">
            {versions.map((version) => {
              const when = timestamp(version.at, SAVED_AT);
              return (
                <li key={version.at} className="app-notes-version">
                  <p className="app-notes-version-head">
                    <time dateTime={version.at}>{when}</time>
                    <span>{version.actor === "agent" ? applicationsCommentAuthorAgent() : applicationsCommentAuthorYou()}</span>
                  </p>
                  <p className="app-notes-version-text"><Content text={versionPreview(version.text)} /></p>
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label={applicationsNotesVersionPutBackLabel({ when })}
                    onClick={() => {
                      setOpen(false);
                      onPutBack(version.text, when);
                    }}
                  >
                    {applicationsNotesVersionPutBack()}
                  </Button>
                </li>
              );
            })}
          </ul>
        )}
      </Popover>
    </>
  );
}
