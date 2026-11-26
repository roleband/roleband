// Customize: what assistant apps may read and change, for the few who want
// less than everything. The card's switch is the one consent; this dialog only
// narrows it. Each choice is a column heading said once, and each row a radio
// group, so a choice is never repeated row after row. A click is stored at
// once, as Settings switches are, so the dialog has no Save.
import type { AgentAccessChoices, AgentAccessState } from "../../api";
import { Button, Dialog, InfoTip } from "../../ui";
import {
  aiAccessDialogAnyModel,
  aiAccessDialogCell,
  aiAccessDialogChanges,
  aiAccessDialogControllingCollection,
  aiAccessDialogData,
  aiAccessDialogKeepingFindings,
  aiAccessDialogLocalOnly,
  aiAccessDialogLocalOnlyTip,
  aiAccessDialogMarketStatistics,
  aiAccessDialogNotShared,
  aiAccessDialogOff,
  aiAccessDialogOffer,
  aiAccessDialogOn,
  aiAccessDialogPostings,
  aiAccessDialogProfile,
  aiAccessDialogProgressAndNotes,
  aiAccessDialogShareEverything,
  aiAccessDialogTitle,
  aiAccessDialogTrackingProgress,
  aiAccessDialogTuningTheRadar,
  aiAssistantsCardDone,
} from "../../copy/gen/ai";

export type Category = "public_posting" | "market_statistic" | "private_pursuit" | "offer" | "candidate";
export type CategoryChoice = "any_model" | "local_only" | "not_shared";
export type Group = "tracking_progress" | "keeping_findings" | "tuning_radar" | "controlling_collection";
export type GroupChoice = "on" | "off";

/** Every data category, in the order the engine declares them
 *  (`DataClass` in `backend/tracker/agents/operations/descriptor.py`). */
export const CATEGORIES: readonly { id: Category; name: () => string }[] = [
  { id: "public_posting", name: aiAccessDialogPostings },
  { id: "market_statistic", name: aiAccessDialogMarketStatistics },
  { id: "private_pursuit", name: aiAccessDialogProgressAndNotes },
  { id: "offer", name: aiAccessDialogOffer },
  { id: "candidate", name: aiAccessDialogProfile },
];

/** Every action group, in the engine's order (`ActionGroup`). */
export const GROUPS: readonly { id: Group; name: () => string }[] = [
  { id: "tracking_progress", name: aiAccessDialogTrackingProgress },
  { id: "keeping_findings", name: aiAccessDialogKeepingFindings },
  { id: "tuning_radar", name: aiAccessDialogTuningTheRadar },
  { id: "controlling_collection", name: aiAccessDialogControllingCollection },
];

const CATEGORY_CHOICES: readonly { id: CategoryChoice; name: () => string; tip?: () => string }[] = [
  { id: "any_model", name: aiAccessDialogAnyModel },
  { id: "local_only", name: aiAccessDialogLocalOnly, tip: aiAccessDialogLocalOnlyTip },
  { id: "not_shared", name: aiAccessDialogNotShared },
];

const GROUP_CHOICES: readonly { id: GroupChoice; name: () => string }[] = [
  { id: "on", name: aiAccessDialogOn },
  { id: "off", name: aiAccessDialogOff },
];

/** Both grids have this many choice columns, the shorter padded on the right,
 *  so their first choices share a column and the row lines run the same length. */
const COLUMNS = Math.max(CATEGORY_CHOICES.length, GROUP_CHOICES.length);

/** What the engine reads a missing choice as: open. */
const SHARED: CategoryChoice = "any_model";
const ALLOWED: GroupChoice = "on";

/** A category's choice, or a group's, as the engine reads it. */
export const categoryChoice = (state: AgentAccessState, id: Category): CategoryChoice =>
  state.categories[id] ?? SHARED;
export const groupChoice = (state: AgentAccessState, id: Group): GroupChoice =>
  state.groups[id] ?? ALLOWED;

/** Whether every category is shared with any model and every group is on. */
function everythingOpen(state: AgentAccessState): boolean {
  return (
    CATEGORIES.every((c) => categoryChoice(state, c.id) === "any_model") &&
    GROUPS.every((g) => groupChoice(state, g.id) === "on")
  );
}

const OPEN: AgentAccessChoices = {
  categories: Object.fromEntries(CATEGORIES.map((c) => [c.id, "any_model"])) as Record<Category, CategoryChoice>,
  groups: Object.fromEntries(GROUPS.map((g) => [g.id, "on"])) as Record<Group, GroupChoice>,
};

export function AgentAccessDialog({
  state,
  saving,
  error,
  onChange,
  onClose,
}: {
  state: AgentAccessState;
  saving: boolean;
  error: string | null;
  onChange: (choices: AgentAccessChoices) => void;
  onClose: () => void;
}) {
  const setCategory = (id: Category, choice: CategoryChoice) =>
    onChange({ categories: { [id]: choice } });
  const setGroup = (id: Group, choice: GroupChoice) => onChange({ groups: { [id]: choice } });

  return (
    <Dialog isOpen onClose={onClose} label={aiAccessDialogTitle()} width={720} className="app-overlay">
      <div className="ledger-form intel-access">
        <div>
          <h3>{aiAccessDialogTitle()}</h3>
        </div>

        <ChoiceGrid
          span={COLUMNS}
          caption={aiAccessDialogData()}
          rows={CATEGORIES}
          choices={CATEGORY_CHOICES}
          value={(id) => categoryChoice(state, id)}
          onPick={setCategory}
          disabled={saving}
        />
        <ChoiceGrid
          span={COLUMNS}
          caption={aiAccessDialogChanges()}
          rows={GROUPS}
          choices={GROUP_CHOICES}
          value={(id) => groupChoice(state, id)}
          onPick={setGroup}
          disabled={saving}
        />

        {error && (
          <p className="intel-error" role="alert">
            {error}
          </p>
        )}

        <div className="ledger-form-actions intel-access-actions">
          {!everythingOpen(state) && (
            <Button variant="link" disabled={saving} onClick={() => onChange(OPEN)}>
              {aiAccessDialogShareEverything()}
            </Button>
          )}
          <Button variant="primary" onClick={onClose}>
            {aiAssistantsCardDone()}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

/** One grid: a column per choice, headed once, and a row per category or
 *  group. A row's radios share a name, so arrow keys move along the row, and
 *  each is labelled with its row and column ("Offer: Not shared"), since a
 *  table row cannot also be a radio group. */
function ChoiceGrid<R extends string, C extends string>({
  span,
  caption,
  rows,
  choices,
  value,
  onPick,
  disabled,
}: {
  span: number;
  caption: string;
  rows: readonly { id: R; name: () => string }[];
  choices: readonly { id: C; name: () => string; tip?: () => string }[];
  value: (id: R) => C;
  onPick: (id: R, choice: C) => void;
  disabled: boolean;
}) {
  return (
    <table className="intel-access-grid">
      <caption>{caption}</caption>
      <thead>
        <tr>
          <td />
          {choices.map((choice) => (
            <th key={choice.id} scope="col">
              {choice.name()}
              {choice.tip && <InfoTip>{choice.tip()}</InfoTip>}
            </th>
          ))}
          {pad(span - choices.length)}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => {
          const name = row.name();
          return (
            <tr key={row.id}>
              <th scope="row">{name}</th>
              {choices.map((choice) => (
                <td key={choice.id}>
                  <input
                    type="radio"
                    className="intel-access-cell"
                    name={`access-${row.id}`}
                    checked={value(row.id) === choice.id}
                    disabled={disabled}
                    aria-label={aiAccessDialogCell({ row: name, column: choice.name() })}
                    onChange={() => onPick(row.id, choice.id)}
                  />
                </td>
              ))}
              {pad(span - choices.length)}
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

/** Empty choice columns that keep a shorter grid in step with the longer. */
const pad = (count: number) =>
  Array.from({ length: count }, (_, i) => <td key={`pad-${i}`} className="intel-access-pad" aria-hidden="true" />);
