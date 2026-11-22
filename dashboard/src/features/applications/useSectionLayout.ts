import { useState } from "react";
import {
  readHiddenSections,
  readSectionOrder,
  writeHiddenSections,
  writeSectionOrder,
  type WorkspaceSection,
  type WorkspaceStage,
} from "./workspaceSections";

interface Layout {
  stage: WorkspaceStage;
  hidden: WorkspaceSection[];
  order: WorkspaceSection[];
}

const readLayout = (stage: WorkspaceStage): Layout => ({
  stage,
  hidden: readHiddenSections(stage),
  order: readSectionOrder(stage),
});

/** The Workspace's blocks for one stage: their order, and which are hidden,
 *  kept in this browser per stage. The state is keyed by the stage it was
 *  read for, so the render that first sees another stage already holds that
 *  stage's own choice, never the previous one's. Every write names the stage
 *  it was made in: a late call (an Undo) writes that stage's storage and
 *  touches the state only while that stage is still the one shown. */
export function useSectionLayout(stage: WorkspaceStage) {
  const [held, setHeld] = useState(() => readLayout(stage));
  let layout = held;
  if (held.stage !== stage) {
    layout = readLayout(stage);
    setHeld(layout);
  }
  const { hidden, order } = layout;
  const shown = order.filter((section) => !hidden.includes(section));
  const offeredBack = order.filter((section) => hidden.includes(section));

  const keepHidden = (next: WorkspaceSection[]) => {
    writeHiddenSections(stage, next);
    setHeld((was) => (was.stage === stage ? { ...was, hidden: next } : was));
  };
  const keepOrder = (next: WorkspaceSection[]) => {
    writeSectionOrder(stage, next);
    setHeld((was) => (was.stage === stage ? { ...was, order: next } : was));
  };

  /** Puts `section` on `side` of `target` in the full order, hidden blocks included. */
  const place = (section: WorkspaceSection, target: WorkspaceSection, side: "before" | "after") => {
    if (section === target) return;
    const next = order.filter((one) => one !== section);
    next.splice(next.indexOf(target) + (side === "after" ? 1 : 0), 0, section);
    keepOrder(next);
  };

  return {
    shown,
    offeredBack,
    /** Hides a block; the Workspace always shows one, so the last stays. */
    hide: (section: WorkspaceSection) => {
      if (shown.length <= 1) return false;
      keepHidden([...hidden, section]);
      return true;
    },
    show: (section: WorkspaceSection) => keepHidden(readHiddenSections(stage).filter((one) => one !== section)),
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
