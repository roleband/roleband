import { useViewChoices, useViewChoicesAnswered, viewChoicesNow } from "../../hooks/viewChoices";
import { layoutOf, saveLayout, type WorkspaceSection, type WorkspaceStage } from "./workspaceSections";

type Change = Parameters<typeof saveLayout>[1];

/** The Workspace's blocks for one stage: their order, and which are hidden,
 *  kept with the person's settings per stage. Every render reads the stage it
 *  is drawn for, so a stage never shows another's order, not for a frame.
 *  Every change names the stage it was made in: a late call (an Undo) changes
 *  that stage and leaves the one now shown as it is. `ready` is false until
 *  the person's view choices are read. */
export function useSectionLayout(stage: WorkspaceStage, onSaveFailed: () => void) {
  const choices = useViewChoices();
  const ready = useViewChoicesAnswered();
  const { hidden, order } = layoutOf(stage, choices);
  const shown = order.filter((section) => !hidden.includes(section));
  const offeredBack = order.filter((section) => hidden.includes(section));

  const keep = (change: Change) => {
    void saveLayout(stage, change).then((saved) => {
      if (!saved) onSaveFailed();
    });
  };

  /** Puts `section` on `side` of `target` in the full order, hidden blocks included. */
  const place = (section: WorkspaceSection, target: WorkspaceSection, side: "before" | "after") => {
    if (section === target) return;
    keep((was) => {
      const next = was.order.filter((one) => one !== section);
      next.splice(next.indexOf(target) + (side === "after" ? 1 : 0), 0, section);
      return { ...was, order: next };
    });
  };

  return {
    ready,
    shown,
    offeredBack,
    /** Hides a block; the Workspace always shows one, so the last stays.
     *  Counted from the layout as saved, not as drawn: a second hide before
     *  the next render sees the first. */
    hide: (section: WorkspaceSection) => {
      const now = layoutOf(stage, viewChoicesNow());
      if (now.order.filter((one) => one !== section && !now.hidden.includes(one)).length === 0) return false;
      keep((was) => ({ ...was, hidden: [...was.hidden, section] }));
      return true;
    },
    show: (section: WorkspaceSection) => keep((was) => ({ ...was, hidden: was.hidden.filter((one) => one !== section) })),
    /** Moves a block one place among those shown, past any hidden between. */
    step: (section: WorkspaceSection, by: -1 | 1) => {
      const neighbour = shown[shown.indexOf(section) + by];
      if (!neighbour) return false;
      place(section, neighbour, by > 0 ? "after" : "before");
      return true;
    },
    place,
  };
}
