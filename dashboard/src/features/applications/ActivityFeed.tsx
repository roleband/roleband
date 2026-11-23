import { FormEvent, useEffect, useLayoutEffect, useRef, useState } from "react";
import type { ActivityItem, ApplicationDetail } from "../../api";
import { date as formatDate, list, relative, timestamp } from "../../copy/format";
import { recordDay } from "./recordDays";
import { Button, Content, Icon, Menu, MenuGroup, MenuItem, ResourceLoadState, useEscapeLayer } from "../../ui";
import {
  applicationsCommentAuthorAgent,
  applicationsCommentAuthorYou,
  applicationsCommentDelete,
  applicationsCommentDeleteConfirm,
  applicationsCommentDeleteLabel,
  applicationsCommentEdit,
  applicationsCommentEdited,
  applicationsCommentLabel,
  applicationsCommentPlaceholder,
  applicationsCommentSave,
  applicationsCommentSubmit,
  applicationsInterviewCancel,
  applicationsFeedByAgent,
  applicationsFeedEmpty,
  applicationsFeedLoadFailed,
  applicationsFeedFold,
  applicationsFeedJumpApplied,
  applicationsFeedJumpBeginning,
  applicationsFeedJumpComments,
  applicationsFeedJumpInterview,
  applicationsFeedJumpLabel,
  applicationsFeedJumpMonth,
  applicationsFeedJumpOffer,
  applicationsFeedJumpRecent,
} from "../../copy/gen/applications";
import { useFocusAfter, useFocusWhen } from "./focusAfter";
import { GrowField } from "./GrowField";
import {
  eventChanges,
  feedMonths,
  itemKey,
  jumpPoints,
  runChanges,
  runOpened,
  type ActivityComment,
  type ActivityEvent,
  type JumpKind,
} from "./activity";

/** How long a jump's entry wears its ring; `app-feed-landed` fades over the same span. */
const LANDED_MS = 2400;

const JUMP_LABEL: Record<JumpKind, () => string> = {
  recent: applicationsFeedJumpRecent,
  applied: applicationsFeedJumpApplied,
  interview: applicationsFeedJumpInterview,
  offer: applicationsFeedJumpOffer,
  beginning: applicationsFeedJumpBeginning,
};

/** A month's name, with its year only when that is not this year's. */
const monthName = (start: Date, now: Date) =>
  timestamp(start, start.getFullYear() === now.getFullYear() ? { month: "long" } : { month: "long", year: "numeric" });

const ago = (iso: string, now: Date) => relative((new Date(iso).getTime() - now.getTime()) / 1000);

function When({ iso, now }: { iso: string; now: Date }) {
  return <time className="app-feed-when" dateTime={iso} title={formatDate(iso, "full")}>{ago(iso, now)}</time>;
}

function EventLine({ event, now }: { event: ActivityEvent; now: Date }) {
  return (
    <li className="app-event" data-feed={itemKey(event)} tabIndex={-1}>
      <Icon name="activity" size={12} />
      <span className="app-event-text">
        {list(eventChanges(event))}
        {event.actor === "agent" && <span className="app-event-actor">{applicationsFeedByAgent()}</span>}
      </span>
      <When iso={event.created_at} now={now} />
    </li>
  );
}

/** Whether the browser can search text it keeps hidden (`hidden="until-found"`)
 *  and says when a match is found in it. */
const findsHidden = () => typeof HTMLElement !== "undefined" && "onbeforematch" in HTMLElement.prototype;

/** A run's changes. Folded, they stay on the page hidden in a way the
 *  browser's find still searches, and a match there opens the run; a browser
 *  that cannot search hidden text leaves them out until the run opens. React
 *  writes `hidden` as a plain on or off, so the value is set on the element. */
function RunChanges({ events, open, onFound, now }: {
  events: readonly ActivityEvent[];
  open: boolean;
  onFound: () => void;
  now: Date;
}) {
  const list = useRef<HTMLOListElement>(null);
  useLayoutEffect(() => {
    const element = list.current;
    if (!element) return;
    if (open) {
      element.removeAttribute("hidden");
      return;
    }
    element.setAttribute("hidden", "until-found");
    element.addEventListener("beforematch", onFound);
    return () => element.removeEventListener("beforematch", onFound);
  }, [open, onFound]);
  if (!open && !findsHidden()) return null;
  return (
    <ol ref={list} className="app-feed-list app-event-changes">
      {events.map((event) => <EventLine key={`event-${event.id}`} event={event} now={now} />)}
    </ol>
  );
}

export interface ActivityFeedProps {
  items: readonly ActivityItem[];
  /** Set when the feed could not be read: said in place of the feed, never
   *  as an empty one, with `onRetry` to read it again. */
  failed?: Error | null;
  onRetry?: () => void;
  /** When the application reached each stage, and its interviews: the
   *  moments the jump menu offers. */
  detail: Pick<ApplicationDetail, "stages_reached" | "interviews">;
  now: Date;
  onAdd: (body: string) => Promise<boolean>;
  onEdit: (id: number, body: string) => Promise<boolean>;
  onDelete: (id: number) => Promise<boolean>;
}

/** The application's whole history as one stream: comments and recorded
 *  changes, newest first, with the field to write in above the newest.
 *  Comments read whole; the changes between two comments fold into one line
 *  that opens and folds again where it stands, so the person never picks a
 *  view first. Once the history runs past one month, each month has a
 *  divider that stays at the top while its entries pass, and opens a menu
 *  that jumps to another month or to a moment of the application. Nothing is
 *  held back, so the browser's own find reaches every entry. */
export function ActivityFeed({ items, failed, onRetry, detail, now, onAdd, onEdit, onDelete }: ActivityFeedProps) {
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  // Read by the handler, not the render: two quick Enters see one post.
  const posting = useRef(false);
  // The ids of the changes in every run the reader opened.
  const [opened, setOpened] = useState<ReadonlySet<number>>(new Set());
  const months = feedMonths(items);
  const dated = months.length > 1;
  const points = jumpPoints(items, detail, now);
  // The divider whose menu is open, and the entry the last jump asked for.
  const [jumpFrom, setJumpFrom] = useState<HTMLElement | null>(null);
  const [landing, setLanding] = useState<{ key: string; turn: number } | null>(null);
  const feedList = useRef<HTMLDivElement>(null);

  const jump = (item: ActivityItem) => {
    setJumpFrom(null);
    setLanding((was) => ({ key: itemKey(item), turn: (was?.turn ?? 0) + 1 }));
  };

  // After the menu has closed and handed focus back to its divider: a folded
  // run is found by any change inside it, so a jump to one change lands on
  // its fold. The entry takes focus, so its own controls are a Tab away.
  useEffect(() => {
    if (!landing) return;
    const target = [...(feedList.current?.querySelectorAll<HTMLElement>("[data-feed]") ?? [])]
      .find((element) => element.dataset.feed?.split(" ").includes(landing.key));
    if (!target) return;
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    target.scrollIntoView?.({ block: "start", behavior: reduced ? "auto" : "smooth" });
    target.focus({ preventScroll: true });
    target.removeAttribute("data-landed");
    void target.offsetWidth;
    target.setAttribute("data-landed", "");
    // A timer, not animationend: under reduced motion the ring holds still
    // and has no animation to end.
    const done = window.setTimeout(() => target.removeAttribute("data-landed"), LANDED_MS);
    return () => {
      window.clearTimeout(done);
      target.removeAttribute("data-landed");
    };
  }, [landing]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!draft.trim() || posting.current) return;
    posting.current = true;
    setSending(true);
    try {
      if (await onAdd(draft)) setDraft("");
    } finally {
      posting.current = false;
      setSending(false);
    }
  };
  const toggleRun = (events: readonly ActivityEvent[], open: boolean) => setOpened((was) => {
    const next = new Set(was);
    for (const event of events) {
      if (open) next.add(event.id);
      else next.delete(event.id);
    }
    return next;
  });

  const entries = (month: (typeof months)[number]) => month.entries.map((entry) => {
    if (entry.kind === "comment") {
      return <CommentItem key={`comment-${entry.comment.id}`} comment={entry.comment} now={now} onEdit={onEdit} onDelete={onDelete} />;
    }
    if (entry.events.length === 1) return <EventLine key={`event-${entry.events[0].id}`} event={entry.events[0]} now={now} />;
    const open = runOpened(entry.events, opened);
    return (
      <li key={entry.key} className="app-event-run" data-open={open || undefined}>
        <div className="app-event app-event-fold" data-feed={entry.events.map(itemKey).join(" ")} tabIndex={-1}>
          <Icon name="activity" size={12} />
          <Button variant="link" className="ui-btn-quiet app-event-toggle" aria-expanded={open} onClick={() => toggleRun(entry.events, !open)}>
            {applicationsFeedFold({ count: entry.events.length, changes: list(runChanges(entry.events)) })}
          </Button>
          <When iso={entry.events[0].created_at} now={now} />
          <Icon name={open ? "chevronDown" : "chevronRight"} size={12} />
        </div>
        <RunChanges events={entry.events} open={open} onFound={() => toggleRun(entry.events, true)} now={now} />
      </li>
    );
  });

  return (
    <div className="app-feed">
      <form className="app-composer" data-writing={draft.trim() ? "" : undefined} onSubmit={submit}>
        <GrowField
          aria-label={applicationsCommentLabel()}
          placeholder={applicationsCommentPlaceholder()}
          rows={1}
          maxLength={20_000}
          value={draft}
          onChange={setDraft}
        />
        {draft.trim() && (
          <Button variant="primary" size="sm" type="submit" disabled={sending}>
            {applicationsCommentSubmit()}
          </Button>
        )}
      </form>
      {failed ? (
        <ResourceLoadState error={failed} failed={applicationsFeedLoadFailed()} onRetry={onRetry} />
      ) : months.length === 0 ? (
        <p className="app-next-empty">{applicationsFeedEmpty()}</p>
      ) : (
        <div className="app-feed-months" ref={feedList}>
          {months.map((month) => {
            const name = monthName(month.start, now);
            return (
              <section key={month.key} className="app-feed-month" aria-label={dated ? name : undefined} data-month={month.key}>
                {dated && (
                  <div className="app-feed-divider">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="app-feed-divider-button"
                      aria-haspopup="dialog"
                      aria-expanded={jumpFrom?.dataset.month === month.key}
                      aria-label={applicationsFeedJumpMonth({ month: name })}
                      data-month={month.key}
                      onClick={(event) => setJumpFrom(event.currentTarget)}
                    >
                      {name}
                      <Icon name="chevronDown" size={12} />
                    </Button>
                  </div>
                )}
                <ol className="app-feed-list">{entries(month)}</ol>
              </section>
            );
          })}
        </div>
      )}
      <Menu isOpen={jumpFrom != null} onClose={() => setJumpFrom(null)} anchor={jumpFrom} label={applicationsFeedJumpLabel()} align="start">
        <MenuGroup>
          {points.filter((point) => point.kind !== "beginning").map((point) => (
            <MenuItem key={point.kind} onSelect={() => jump(point.item)} detail={recordDay(point.at, now)}>
              {JUMP_LABEL[point.kind]()}
            </MenuItem>
          ))}
        </MenuGroup>
        <MenuGroup>
          {months.map((month) => (
            <MenuItem
              key={month.key}
              onSelect={() => jump(month.items[0])}
              current={jumpFrom?.dataset.month === month.key}
              detail={month.comments > 0 ? applicationsFeedJumpComments({ count: month.comments }) : undefined}
            >
              {monthName(month.start, now)}
            </MenuItem>
          ))}
        </MenuGroup>
        {points.filter((point) => point.kind === "beginning").map((point) => (
          <MenuGroup key={point.kind}>
            <MenuItem onSelect={() => jump(point.item)} detail={formatDate(point.at, "full")}>
              {JUMP_LABEL[point.kind]()}
            </MenuItem>
          </MenuGroup>
        ))}
      </Menu>
    </div>
  );
}

function CommentItem({ comment, now, onEdit, onDelete }: {
  comment: ActivityComment;
  now: Date;
  onEdit: (id: number, body: string) => Promise<boolean>;
  onDelete: (id: number) => Promise<boolean>;
}) {
  const [editing, setEditing] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const field = useFocusWhen<HTMLTextAreaElement>(editing != null);
  const editButton = useRef<HTMLButtonElement>(null);
  const focusAfter = useFocusAfter();
  const saving = useRef(false);
  // Moves on each time the edit opens or closes: a save that lands after the
  // edit was left and opened again closes nothing.
  const session = useRef(0);
  const open = () => {
    session.current += 1;
    setEditing(comment.body);
  };
  const close = () => {
    session.current += 1;
    focusAfter(() => editButton.current);
    setEditing(null);
  };
  // While an edit or its delete question is open, Escape leaves just that,
  // and the posting under it stays.
  useEscapeLayer(editing != null, close);
  useEscapeLayer(confirming, () => setConfirming(false));
  // An agent's comment is the agent's record: the person reads it, and does not rewrite it.
  const own = comment.actor === "user";

  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (editing == null || !editing.trim() || saving.current) return;
    saving.current = true;
    const mine = session.current;
    try {
      if ((await onEdit(comment.id, editing)) && session.current === mine) close();
    } finally {
      saving.current = false;
    }
  };

  return (
    <li className="app-comment" data-comment-id={comment.id} data-feed={itemKey(comment)} tabIndex={-1}>
      <div className="app-comment-head">
        <span className="app-comment-author">
          {own ? applicationsCommentAuthorYou() : applicationsCommentAuthorAgent()}
        </span>
        <When iso={comment.created_at} now={now} />
        {comment.edited_at && <span className="app-comment-edited">{applicationsCommentEdited()}</span>}
        <span className="app-tile-spacer" />
        {own && editing == null && (
          <>
            <Button ref={editButton} variant="icon" size="sm" className="app-row-tool" aria-label={applicationsCommentEdit()} onClick={open}>
              <Icon name="edit" size={14} />
            </Button>
            <Button variant="icon" size="sm" className="app-row-tool" aria-label={applicationsCommentDeleteLabel()} onClick={() => setConfirming(true)}>
              <Icon name="trash" size={14} />
            </Button>
          </>
        )}
      </div>
      {editing != null ? (
        <form className="app-composer" onSubmit={save}>
          <GrowField
            aria-label={applicationsCommentLabel()}
            fieldRef={field}
            rows={3}
            maxLength={20_000}
            value={editing}
            onChange={setEditing}
          />
          <div className="app-next-actions">
            <Button variant="ghost" size="sm" onClick={close}>{applicationsInterviewCancel()}</Button>
            <Button variant="ghost" size="sm" className="ui-btn-strong" type="submit">{applicationsCommentSave()}</Button>
          </div>
        </form>
      ) : (
        <p className="app-comment-body"><Content text={comment.body} /></p>
      )}
      {confirming && (
        <div className="app-comment-confirm" role="group" aria-label={applicationsCommentDeleteConfirm()}>
          <span>{applicationsCommentDeleteConfirm()}</span>
          <Button variant="ghost" size="sm" onClick={() => setConfirming(false)}>{applicationsInterviewCancel()}</Button>
          <Button
            variant="danger"
            size="sm"
            onClick={() => {
              setConfirming(false);
              void onDelete(comment.id);
            }}
          >
            {applicationsCommentDelete()}
          </Button>
        </div>
      )}
    </li>
  );
}
