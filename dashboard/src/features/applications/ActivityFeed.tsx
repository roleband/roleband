import { FormEvent, useRef, useState } from "react";
import { date as formatDate, relative } from "../../copy/format";
import { Button, Content, Icon } from "../../ui";
import {
  applicationsCommentAuthorAgent,
  applicationsCommentAuthorYou,
  applicationsCommentDelete,
  applicationsCommentDeleteConfirm,
  applicationsCommentDeleteLabel,
  applicationsCommentEdit,
  applicationsCommentEdited,
  applicationsCommentLabel,
  applicationsCommentSave,
  applicationsInterviewCancel,
} from "../../copy/gen/applications";
import { useFocusAfter } from "./focusAfter";
import { useFocusWhen } from "./ApplicationPanels";
import { type ActivityComment } from "./activity";

const ago = (iso: string, now: Date) => relative((new Date(iso).getTime() - now.getTime()) / 1000);

function When({ iso, now }: { iso: string; now: Date }) {
  return <time className="app-feed-when" dateTime={iso} title={formatDate(iso, "full")}>{ago(iso, now)}</time>;
}

export function CommentItem({ comment, now, onEdit, onDelete }: {
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
