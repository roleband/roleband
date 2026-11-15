import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import type { ActivityItem, ApplicationDetail } from "../../api";
import { date as formatDate, list, relative, timestamp } from "../../copy/format";
import { Button, Content, Icon, Menu, MenuGroup, MenuItem, Segmented } from "../../ui";
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
  applicationsFeedFold,
  applicationsFeedJumpApplied,
  applicationsFeedJumpBeginning,
  applicationsFeedJumpComments,
  applicationsFeedJumpInterview,
  applicationsFeedJumpLabel,
  applicationsFeedJumpMonth,
  applicationsFeedJumpOffer,
  applicationsFeedJumpRecent,
  applicationsFeedModeAll,
  applicationsFeedModeComments,
  applicationsFeedModeLabel,
  applicationsFeedTitle,
} from "../../copy/gen/applications";
import { useFocusAfter } from "./focusAfter";
import { useFocusWhen } from "./ApplicationPanels";
import {
  eventChanges,
  feedMonths,
  itemKey,
  jumpPoints,
  runChanges,
  runOpened,
  type ActivityComment,
  type ActivityEvent,
  type FeedMode,
  type JumpKind,
} from "./activity";

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

export interface ActivityFeedProps {
  items: readonly ActivityItem[];
  /** When the application reached each stage, and its interviews: the
   *  moments the jump menu offers. */
  detail: Pick<ApplicationDetail, "stages_reached" | "interviews">;
  now: Date;
  onAdd: (body: string) => Promise<boolean>;
  onEdit: (id: number, body: string) => Promise<boolean>;
  onDelete: (id: number) => Promise<boolean>;
}

/** The application's whole history: comments and recorded changes, newest
 *  first, with the composer above the newest. Comments lead; the changes
 *  between two comments fold into one line until opened, and All activity
 *  opens every one. Every month has a divider that stays at the top while
 *  its entries pass, and opens a menu that jumps to another month or to a
 *  moment of the application. Nothing is held back, so the browser's own
 *  find reaches every entry. */
export function ActivityFeed({ items, detail, now, onAdd, onEdit, onDelete }: ActivityFeedProps) {
  const [mode, setMode] = useState<FeedMode>("comments");
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  // The ids of the changes in every run the reader opened.
  const [opened, setOpened] = useState<ReadonlySet<number>>(new Set());
  const months = feedMonths(items, mode);
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
    const done = () => target.removeAttribute("data-landed");
    target.addEventListener("animationend", done, { once: true });
    return () => target.removeEventListener("animationend", done);
  }, [landing]);

  const post = async () => {
    if (!draft.trim() || sending) return;
    setSending(true);
    const saved = await onAdd(draft);
    setSending(false);
    if (saved) setDraft("");
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    void post();
  };
  // Cmd or Ctrl and Enter posts, as in every comment box that keeps Enter for a new line.
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      void post();
    }
  };

  return (
    <section className="app-panel app-feed" aria-labelledby="app-feed-title">
      <div className="app-panel-head">
        <h2 id="app-feed-title" className="app-panel-title">{applicationsFeedTitle()}</h2>
        <Segmented
          label={applicationsFeedModeLabel()}
          value={mode}
          onChange={setMode}
          options={[
            { value: "comments", label: applicationsFeedModeComments() },
            { value: "all", label: applicationsFeedModeAll() },
          ]}
        />
      </div>
      <form className="app-composer" onSubmit={submit}>
        <textarea
          aria-label={applicationsCommentLabel()}
          placeholder={applicationsCommentPlaceholder()}
          rows={2}
          maxLength={20_000}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={onKeyDown}
        />
        <Button variant="ghost" size="sm" className="ui-btn-strong" type="submit" disabled={!draft.trim() || sending}>
          {applicationsCommentSubmit()}
        </Button>
      </form>
      {months.length === 0 ? (
        <p className="app-next-empty">{applicationsFeedEmpty()}</p>
      ) : (
        <div className="app-feed-months" ref={feedList}>
          {months.map((month) => {
            const name = monthName(month.start, now);
            return (
              <section key={month.key} className="app-feed-month" aria-label={name} data-month={month.key}>
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
                <ol className="app-feed-list">
                  {month.entries.map((entry) => {
            if (entry.kind === "comment") {
              return (
                <CommentItem key={`comment-${entry.comment.id}`} comment={entry.comment} now={now} onEdit={onEdit} onDelete={onDelete} />
              );
            }
            const folded = mode === "comments" && entry.events.length > 1 && !runOpened(entry.events, opened);
            if (folded) {
              return (
                <li key={entry.key} className="app-event app-event-fold" data-feed={entry.events.map(itemKey).join(" ")} tabIndex={-1}>
                  <Icon name="activity" size={12} />
                  <Button
                    variant="link"
                    className="ui-btn-quiet"
                    aria-expanded={false}
                    onClick={() => setOpened((open) => new Set([...open, ...entry.events.map((event) => event.id)]))}
                  >
                    {applicationsFeedFold({ count: entry.events.length, changes: list(runChanges(entry.events)) })}
                  </Button>
                </li>
              );
            }
            return entry.events.map((event) => <EventLine key={`event-${event.id}`} event={event} now={now} />);
                  })}
                </ol>
              </section>
            );
          })}
        </div>
      )}
      <Menu isOpen={jumpFrom != null} onClose={() => setJumpFrom(null)} anchor={jumpFrom} label={applicationsFeedJumpLabel()} align="start">
        <MenuGroup>
          {points.filter((point) => point.kind !== "beginning").map((point) => (
            <MenuItem key={point.kind} onSelect={() => jump(point.item)} detail={formatDate(point.at, "day")}>
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
    </section>
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
  const close = () => {
    focusAfter(() => editButton.current);
    setEditing(null);
  };
  // An agent's comment is the agent's record: the person reads it, and does not rewrite it.
  const own = comment.actor === "user";

  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (editing == null || !editing.trim()) return;
    if (await onEdit(comment.id, editing)) close();
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
            <Button ref={editButton} variant="icon" size="sm" aria-label={applicationsCommentEdit()} onClick={() => setEditing(comment.body)}>
              <Icon name="edit" size={14} />
            </Button>
            <Button variant="icon" size="sm" aria-label={applicationsCommentDeleteLabel()} onClick={() => setConfirming(true)}>
              <Icon name="trash" size={14} />
            </Button>
          </>
        )}
      </div>
      {editing != null ? (
        <form className="app-composer" onSubmit={save}>
          <textarea
            aria-label={applicationsCommentLabel()}
            ref={field}
            rows={3}
            maxLength={20_000}
            value={editing}
            onChange={(event) => setEditing(event.target.value)}
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
