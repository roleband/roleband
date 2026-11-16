import type { ActivityEntry } from "../../../api/agentActivity";
import { list } from "../../../copy/format";
import { formatWhen } from "../../../format";
import { categoryName, entryText, fieldName, fieldValue, groupName } from "./activityText";
import {
  activityFactAskedFor,
  activityFactGroup,
  activityFactNothing,
  activityFactOperation,
  activityFactRead,
  activityInspector,
  activityInspectorWhen,
  activityKindChange,
  activityKindRead,
  activityKindRefusal,
  activityValueCleared,
  activityWhatChanged,
} from "../../../copy/gen/activity";

const KIND_NAME = { read: activityKindRead, change: activityKindChange, refused: activityKindRefusal };

/** The picked entry: what it was and when, what it changed (the old value
 *  struck through), and what it read. */
export function ActivityInspector({ entry }: { entry: ActivityEntry }) {
  const categories = entry.categories.map(categoryName);
  return (
    <aside className="activity-inspector" aria-label={activityInspector()}>
      <div className="activity-inspector-head">
        <span className="eyebrow">
          {activityInspectorWhen({
            kind: KIND_NAME[entry.kind](),
            when: formatWhen(entry.occurred_at),
          })}
        </span>
        <h2 className="activity-inspector-title">{entryText(entry, { plain: true })}</h2>
      </div>

      {entry.changes.length > 0 && (
        <dl className="activity-diff" aria-label={activityWhatChanged()}>
          {entry.changes.map((change) => (
            <div key={change.field} className="activity-diff-row">
              <dt>{fieldName(change.field)}</dt>
              <dd>
                {change.before != null && (
                  <><s className="activity-old">{fieldValue(change.field, change.before)}</s>{" → "}</>
                )}
                {change.after != null ? fieldValue(change.field, change.after) : activityValueCleared()}
              </dd>
            </div>
          ))}
        </dl>
      )}

      <dl className="activity-facts">
        {entry.action_group && (
          <>
            <dt>{activityFactGroup()}</dt>
            <dd>{groupName(entry.action_group)}</dd>
          </>
        )}
        <dt>{activityFactOperation()}</dt>
        <dd><code className="activity-operation">{entry.operation}</code></dd>
        <dt>{entry.kind === "refused" ? activityFactAskedFor() : activityFactRead()}</dt>
        <dd>{categories.length > 0 ? list(categories) : activityFactNothing()}</dd>
      </dl>
    </aside>
  );
}
