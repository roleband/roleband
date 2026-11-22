import { beforeEach, describe, expect, it } from "vitest";
import { fakeViewChoiceServer } from "../test/viewChoicesServer";
import { setViewChoice, viewChoice, viewChoicesNow } from "./viewChoices";
import { readViewChoices } from "./viewChoicesRead";

/* How the person arranged the screens is kept in the database: read once per
 * page, shown at once when changed, saved in the background with the last
 * change winning, and moved out of the browser that used to keep it. */

let server: ReturnType<typeof fakeViewChoiceServer>;
const settle = () => new Promise((done) => setTimeout(done, 0));

beforeEach(() => {
  localStorage.clear();
  server = fakeViewChoiceServer();
});

describe("the person's view choices", () => {
  it("are read once per page, and a choice never made reads as nothing", async () => {
    server.hold({ "posting.similar-folded": true });
    await readViewChoices();
    await readViewChoices();
    expect(viewChoice("posting.similar-folded")).toBe(true);
    expect(viewChoice("pipeline.board-hidden")).toBeUndefined();
    expect(server.read).toHaveBeenCalledTimes(1);
  });

  it("show a change at once and save it, leaving every other choice as it was", async () => {
    server.hold({ "posting.similar-folded": true });
    await readViewChoices();
    const done = setViewChoice("pipeline.board-hidden", ["closed"]);
    expect(viewChoice("pipeline.board-hidden"), "shown before the save answers").toEqual(["closed"]);
    expect(await done).toBe(true);
    expect(server.saved()).toEqual({ "posting.similar-folded": true, "pipeline.board-hidden": ["closed"] });
  });

  it("save a burst of changes as two saves, and the database keeps the last", async () => {
    await readViewChoices();
    let answerFirst!: () => void;
    server.save.mockImplementationOnce((name, value) => new Promise((resolve) => {
      answerFirst = () => {
        server.hold({ ...server.saved(), [name]: value });
        resolve({ name, value: value as never });
      };
    }));
    const saves = ["a", "b", "c", "d"].map((key) => setViewChoice("filters.board", { company: [key] }));
    await settle();
    expect(server.save, "the others wait behind the first").toHaveBeenCalledTimes(1);
    answerFirst();
    expect(await Promise.all(saves)).toEqual([true, true, true, true]);
    expect(server.save).toHaveBeenCalledTimes(2);
    expect(server.saved()["filters.board"]).toEqual({ company: ["d"] });
  });

  it("say a save failed, and keep the change on the page until it is reloaded", async () => {
    await readViewChoices();
    server.save.mockRejectedValueOnce(new Error("offline"));
    expect(await setViewChoice("posting.similar-folded", true)).toBe(false);
    expect(viewChoice("posting.similar-folded")).toBe(true);
    expect(server.saved()).toEqual({});
  });

  it("keep a choice made before the read answered over the one the read brings", async () => {
    server.hold({ "posting.similar-folded": true, "pipeline.board-hidden": ["saved"] });
    expect(viewChoice("posting.similar-folded"), "nothing until the read answers").toBeUndefined();
    void setViewChoice("posting.similar-folded", false);
    await readViewChoices();
    await settle();
    expect(viewChoice("posting.similar-folded")).toBe(false);
    expect(viewChoice("pipeline.board-hidden")).toEqual(["saved"]);
  });

  it("show each screen's defaults when the read fails, and are read again when a screen asks", async () => {
    server.read.mockRejectedValueOnce(new Error("offline"));
    expect(viewChoicesNow()).toEqual({});
    await settle();
    expect(viewChoicesNow(), "a render does not ask again").toEqual({});
    expect(server.read).toHaveBeenCalledTimes(1);
  });
});

describe("choices this browser still holds", () => {
  const BROWSER = {
    "roleband.pipeline-hidden-columns": JSON.stringify(["decided", "closed", "archive"]),
    "roleband.pipeline-closed-hidden": "1",
    "roleband.pipeline-list-columns": JSON.stringify({ order: ["pay", "role", "salary"], hidden: ["pay"] }),
    "roleband.pipeline-crossings-dismissed": JSON.stringify(["101:closed:2026-11-20T10:00:00Z", 7]),
    "roleband.posting-similar-folded": "1",
    "roleband.insights-view": "advanced",
    "roleband.pipeline-workspace-hidden": JSON.stringify({ applied: ["notes"] }),
    "roleband.pipeline-workspace-order": JSON.stringify({ applied: ["activity", "notes", "next"], interviewing: ["notes", "interviews"] }),
    "roleband.filters.v1:board": JSON.stringify({ company: ["openai"] }),
    "roleband.filters.v1:notifications:params": JSON.stringify({ status: ["unread"] }),
  };
  const MOVED = {
    "pipeline.board-hidden": ["decided", "closed"],
    "pipeline.list-layout": { order: ["pay", "role"], hidden: ["pay"] },
    "pipeline.crossings-dismissed": ["101:closed:2026-11-20T10:00:00Z"],
    "posting.similar-folded": true,
    "insights.view": "advanced",
    "workspace.applied": { hidden: ["notes"], order: ["activity", "notes", "next"] },
    "workspace.interviewing": { hidden: [], order: ["notes", "interviews"] },
    "filters.board": { company: ["openai"] },
    "filters.notifications:params": { status: ["unread"] },
  };
  const seed = () => Object.entries(BROWSER).forEach(([key, text]) => localStorage.setItem(key, text));
  /** The page loads: the read answers, a screen asks for its choices, and
   *  the saves that follow land. */
  const open = async () => {
    await readViewChoices();
    viewChoicesNow();
    await settle();
  };

  it("move to the database when it holds none, show at once, and leave the browser", async () => {
    seed();
    await readViewChoices();
    expect(viewChoicesNow()).toEqual(MOVED);
    await settle();
    expect(server.saved()).toEqual(MOVED);
    expect(Object.keys(BROWSER).filter((key) => localStorage.getItem(key) !== null)).toEqual([]);
  });

  it("give way to what the database holds, and leave the browser", async () => {
    seed();
    server.hold({ "posting.similar-folded": false, "workspace.applied": { hidden: [], order: ["notes"] } });
    await open();
    expect(viewChoice("posting.similar-folded")).toBe(false);
    expect(viewChoice("workspace.applied")).toEqual({ hidden: [], order: ["notes"] });
    expect(viewChoice("workspace.interviewing"), "a stage the database lacks still moves").toEqual(MOVED["workspace.interviewing"]);
    expect(server.save.mock.calls.map(([name]) => name)).not.toContain("posting.similar-folded");
    expect(localStorage.getItem("roleband.posting-similar-folded")).toBeNull();
  });

  it("stay in the browser while any choice they held failed to save, for the next visit to move", async () => {
    seed();
    server.save.mockImplementation(async (name, value) => {
      if (name === "workspace.interviewing") throw new Error("offline");
      server.hold({ ...server.saved(), [name]: value });
      return { name, value: value as never };
    });
    await open();
    expect(server.saved()["workspace.applied"]).toEqual(MOVED["workspace.applied"]);
    expect(localStorage.getItem("roleband.pipeline-workspace-order"), "it also holds the stage that failed").not.toBeNull();
    expect(localStorage.getItem("roleband.pipeline-list-columns")).toBeNull();
  });

  it("leave the browser when they hold nothing worth keeping", async () => {
    localStorage.setItem("roleband.pipeline-list-columns", "{not json");
    localStorage.setItem("roleband.posting-similar-folded", "0");
    localStorage.setItem("roleband.pipeline-closed-hidden", "1");
    await open();
    expect(server.save).not.toHaveBeenCalled();
    expect(viewChoicesNow()).toEqual({});
    expect(localStorage.length).toBe(0);
  });
});
