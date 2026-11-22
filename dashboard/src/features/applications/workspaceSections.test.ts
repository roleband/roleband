import { beforeEach, describe, expect, it, vi } from "vitest";
import { applicationCardFixture } from "../../test/fixtures";
import { readHiddenSections, readSectionOrder, workspaceStage, writeHiddenSections, writeSectionOrder } from "./workspaceSections";

/* What the person did to a stage's Workspace (blocks moved, blocks hidden)
 * comes back on the next visit, for that stage only, and never leaves a
 * stage with a block missing or none shown. */

const ORDER_KEY = "roleband.pipeline-workspace-order";

beforeEach(() => localStorage.clear());

describe("a stage's blocks", () => {
  it("keep the next steps for an accepted offer, which still owes some, and drop them for any other ending", () => {
    const accepted = workspaceStage(applicationCardFixture({ stage: "accepted" }));
    expect(readSectionOrder(accepted)).toContain("next");
    expect(readSectionOrder(accepted)[0], "how it ended leads").toBe("outcome");
    for (const stage of ["rejected", "withdrawn", "declined", "role_closed"] as const) {
      expect(readSectionOrder(workspaceStage(applicationCardFixture({ stage }))), stage).not.toContain("next");
    }
  });
});

describe("a stage's block order", () => {
  it("is the stage's own until the person moves a block", () => {
    expect(readSectionOrder("applied")).toEqual(["next", "notes", "activity"]);
    expect(readSectionOrder("interviewing")).toEqual(["interviews", "next", "notes", "activity"]);
  });

  it("comes back as the person left it, for that stage only", () => {
    writeSectionOrder("applied", ["activity", "next", "notes"]);
    expect(readSectionOrder("applied")).toEqual(["activity", "next", "notes"]);
    expect(readSectionOrder("offer")).toEqual(["next", "notes", "activity"]);
  });

  it("drops a block the stage does not offer, and names each block once", () => {
    localStorage.setItem(ORDER_KEY, JSON.stringify({ applied: ["outcome", "notes", "notes", "next", "activity", 7] }));
    expect(readSectionOrder("applied")).toEqual(["notes", "next", "activity"]);
  });

  it("keeps a block the stored order does not name, after the block it follows on the stage", () => {
    // Stored before the stage offered Interviews: it takes its own first place.
    localStorage.setItem(ORDER_KEY, JSON.stringify({ interviewing: ["notes", "next", "activity"] }));
    expect(readSectionOrder("interviewing")).toEqual(["interviews", "notes", "next", "activity"]);
    // A missing middle block lands right after the one it follows.
    localStorage.setItem(ORDER_KEY, JSON.stringify({ interviewing: ["activity", "interviews", "notes"] }));
    expect(readSectionOrder("interviewing")).toEqual(["activity", "interviews", "next", "notes"]);
  });

  it("falls back to the stage's own order when storage is unreadable or broken", () => {
    localStorage.setItem(ORDER_KEY, "{not json");
    expect(readSectionOrder("applied")).toEqual(["next", "notes", "activity"]);
    const spy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(readSectionOrder("applied")).toEqual(["next", "notes", "activity"]);
    spy.mockRestore();
  });
});

describe("a stage's hidden blocks", () => {
  it("come back for that stage only", () => {
    writeHiddenSections("applied", ["notes"]);
    expect(readHiddenSections("applied")).toEqual(["notes"]);
    expect(readHiddenSections("offer")).toEqual([]);
  });

  it("never hide every block: a list that would is read as none", () => {
    writeHiddenSections("applied", ["next", "notes", "activity"]);
    expect(readHiddenSections("applied")).toEqual([]);
  });
});
