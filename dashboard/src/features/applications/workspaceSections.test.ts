import { beforeEach, describe, expect, it } from "vitest";
import { viewChoicesNow } from "../../hooks/viewChoices";
import { readViewChoices } from "../../hooks/viewChoicesRead";
import { applicationCardFixture } from "../../test/fixtures";
import { fakeViewChoiceServer } from "../../test/viewChoicesServer";
import { hiddenSections, layoutOf, saveLayout, sectionOrder, standsBeside, workspaceStage } from "./workspaceSections";

/* What the person did to a stage's Workspace (blocks moved, blocks hidden)
 * is one of their view choices, saved with their settings: it comes back on
 * the next visit, in any browser, for that stage only, and never leaves a
 * stage with a block missing or none shown. */

let server: ReturnType<typeof fakeViewChoiceServer>;

beforeEach(() => {
  server = fakeViewChoiceServer();
});

describe("a stage's blocks", () => {
  it("keep the next steps for an accepted offer, which still owes some, and drop them for any other ending", () => {
    const accepted = workspaceStage(applicationCardFixture({ stage: "accepted" }));
    expect(sectionOrder(accepted)).toContain("next");
    for (const stage of ["rejected", "withdrawn", "declined", "role_closed"] as const) {
      expect(sectionOrder(workspaceStage(applicationCardFixture({ stage }))), stage).not.toContain("next");
    }
  });

  it("have no block that says how a role ended: the stage facts beside the Workspace say it", () => {
    for (const stage of ["accepted", "rejected", "withdrawn", "declined", "role_closed"] as const) {
      expect(sectionOrder(workspaceStage(applicationCardFixture({ stage }))), stage).not.toContain("outcome");
    }
  });

  it("read a layout saved while an ended role had an Outcome block without it, the other blocks in their saved order", () => {
    const ended = workspaceStage(applicationCardFixture({ stage: "rejected" }));
    expect(sectionOrder(ended, { order: ["activity", "outcome", "notes"] })).toEqual(["activity", "notes"]);
    expect(hiddenSections(ended, { hidden: ["outcome", "notes"] })).toEqual(["notes"]);
  });

  it("stand the short lists beside the writing, and the writing in the main column", () => {
    expect((["next", "interviews"] as const).map(standsBeside)).toEqual([true, true]);
    expect((["notes", "activity"] as const).map(standsBeside)).toEqual([false, false]);
  });
});

describe("a stage's block order", () => {
  it("is the stage's own until the person moves a block", () => {
    expect(sectionOrder("applied")).toEqual(["next", "notes", "activity"]);
    expect(sectionOrder("interviewing")).toEqual(["interviews", "next", "notes", "activity"]);
  });

  it("drops a block the stage does not offer, and names each block once", () => {
    expect(sectionOrder("applied", { order: ["outcome", "notes", "notes", "next", "activity", 7] })).toEqual(["notes", "next", "activity"]);
  });

  it("keeps a block the saved order does not name, after the block it follows on the stage", () => {
    // Saved before the stage offered Interviews: it takes its own first place.
    expect(sectionOrder("interviewing", { order: ["notes", "next", "activity"] })).toEqual(["interviews", "notes", "next", "activity"]);
    // A missing middle block lands right after the one it follows.
    expect(sectionOrder("interviewing", { order: ["activity", "interviews", "notes"] })).toEqual(["activity", "interviews", "next", "notes"]);
  });
});

describe("a stage's hidden blocks", () => {
  it("never hide every block: a list that would is read as none", () => {
    expect(hiddenSections("applied", { hidden: ["next", "notes", "activity"] })).toEqual([]);
    expect(hiddenSections("applied", { hidden: ["notes", "calendar"] })).toEqual(["notes"]);
  });
});

describe("the layout kept with the person's settings", () => {
  it("answers each stage with what was saved for it, and its own layout otherwise", async () => {
    server.hold({ "workspace.applied": { hidden: ["notes"], order: ["activity", "next", "notes"] } });
    await readViewChoices();
    expect(layoutOf("applied", viewChoicesNow())).toEqual({ hidden: ["notes"], order: ["activity", "next", "notes"] });
    expect(layoutOf("offer", viewChoicesNow())).toEqual({ hidden: [], order: ["next", "notes", "activity"] });
  });

  it("reads a saved layout that no longer fits as the stage's own", async () => {
    server.hold({ "workspace.applied": { hidden: "notes", order: 7 }, "workspace.offer": "all" });
    await readViewChoices();
    expect(layoutOf("applied", viewChoicesNow())).toEqual({ hidden: [], order: ["next", "notes", "activity"] });
    expect(layoutOf("offer", viewChoicesNow())).toEqual({ hidden: [], order: ["next", "notes", "activity"] });
  });

  it("shows a change at once and saves it for that stage only", async () => {
    server.hold({ "workspace.offer": { hidden: [], order: ["activity", "next", "notes"] } });
    await readViewChoices();
    const done = saveLayout("applied", (was) => ({ ...was, hidden: ["notes"] }));
    expect(layoutOf("applied", viewChoicesNow()).hidden, "shown before the save answers").toEqual(["notes"]);
    expect(await done).toBe(true);
    expect(server.saved()).toEqual({
      "workspace.offer": { hidden: [], order: ["activity", "next", "notes"] },
      "workspace.applied": { hidden: ["notes"], order: ["next", "notes", "activity"] },
    });
  });

  it("says a save failed, and keeps the change on the page until it is reloaded", async () => {
    await readViewChoices();
    server.save.mockRejectedValueOnce(new Error("offline"));
    expect(await saveLayout("offer", (was) => ({ ...was, hidden: ["activity"] }))).toBe(false);
    expect(layoutOf("offer", viewChoicesNow()).hidden).toEqual(["activity"]);
    expect(server.saved()).toEqual({});
  });
});
