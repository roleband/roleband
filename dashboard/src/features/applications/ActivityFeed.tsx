import { FormEvent, KeyboardEvent, useState } from "react";
import type { ActivityItem } from "../../api";
import { date as formatDate, list, relative } from "../../copy/format";
import { Button, Content, Icon, Segmented } from "../../ui";
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
  applicationsFeedModeAll,
  applicationsFeedModeComments,
  applicationsFeedModeLabel,
  applicationsFeedTitle,
} from "../../copy/gen/applications";
import { useFocusWhen } from "./ApplicationPanels";
import { eventChanges, feedEntries, runChanges, runOpened, type ActivityComment, type ActivityEvent, type FeedMode } from "./activity";

const ago = (iso: string, now: Date) => relative((new Date(iso).getTime() - now.getTime()) / 1000);

function When({ iso, now }: { iso: string; now: Date }) {
  return <time className="app-feed-when" dateTime={iso} title={formatDate(iso, "full")}>{ago(iso, now)}</time>;
}

function EventLine({ event, now }: { event: ActivityEvent; now: Date }) {
  return (
    <li className="app-event">
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
  now: Date;
  onAdd: (body: string) => Promise<boolean>;
  onEdit: (id: number, body: string) => Promise<boolean>;
  onDelete: (id: number) => Promise<boolean>;
}

/** The application's history: comments and recorded changes, newest first,
 *  with the composer above the newest. Comments lead; the changes between
 *  two comments fold into one line until opened, and All activity opens
 *  every one. */
export function ActivityFeed({ items, now, onAdd, onEdit, onDelete }: ActivityFeedProps) {
  const [mode, setMode] = useState<FeedMode>("comments");
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  // The ids of the changes in every run the reader opened.
  const [opened, setOpened] = useState<ReadonlySet<number>>(new Set());
  const entries = feedEntries(items, mode);

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
      {entries.length === 0 ? (
        <p className="app-next-empty">{applicationsFeedEmpty()}</p>
      ) : (
        <ol className="app-feed-list">
          {entries.map((entry) => {
            if (entry.kind === "comment") {
              return (
                <CommentItem key={`comment-${entry.comment.id}`} comment={entry.comment} now={now} onEdit={onEdit} onDelete={onDelete} />
              );
            }
            const folded = mode === "comments" && entry.events.length > 1 && !runOpened(entry.events, opened);
            if (folded) {
              return (
                <li key={entry.key} className="app-event app-event-fold">
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
      )}
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
  // An agent's comment is the agent's record: the person reads it, and does not rewrite it.
  const own = comment.actor === "user";

  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (editing == null || !editing.trim()) return;
    if (await onEdit(comment.id, editing)) setEditing(null);
  };

  return (
    <li className="app-comment" data-comment-id={comment.id}>
      <div className="app-comment-head">
        <span className="app-comment-author">
          {own ? applicationsCommentAuthorYou() : applicationsCommentAuthorAgent()}
        </span>
        <When iso={comment.created_at} now={now} />
        {comment.edited_at && <span className="app-comment-edited">{applicationsCommentEdited()}</span>}
        <span className="app-tile-spacer" />
        {own && editing == null && (
          <>
            <Button variant="icon" size="sm" aria-label={applicationsCommentEdit()} onClick={() => setEditing(comment.body)}>
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
            <Button variant="ghost" size="sm" onClick={() => setEditing(null)}>{applicationsInterviewCancel()}</Button>
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
