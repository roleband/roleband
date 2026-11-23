import { beforeEach, describe, expect, it } from "vitest";
import { readViewChoices } from "../../hooks/viewChoicesRead";
import { fakeViewChoiceServer } from "../../test/viewChoicesServer";
import { readHiddenColumns, writeHiddenColumns } from "./columnView";

/* Hidden columns are one of the person's view choices, saved with their
 * settings: kept in board order, never all of them, and until chosen, or when
 * what was saved no longer fits, the board hides Considering, Decided and
 * Closed. */

let server: ReturnType<typeof fakeViewChoiceServer>;

beforeEach(async () => {
  server = fakeViewChoiceServer();
  await readViewChoices();
});

const settle = () => new Promise((done) => setTimeout(done, 0));

describe("hidden columns", () => {
  it("come back in board order, saved with the person's settings", async () => {
    writeHiddenColumns(["closed", "saved"]);
    expect(readHiddenColumns()).toEqual(["saved", "closed"]);
    await settle();
    expect(server.saved()).toEqual({ "pipeline.board-hidden": ["saved", "closed"] });
  });

  it("drop names the board does not have, and never hide every column", async () => {
    fakeViewChoiceServer({ "pipeline.board-hidden": ["decided", "networking", "nonsense"] });
    await readViewChoices();
    expect(readHiddenColumns()).toEqual(["decided"]);
    writeHiddenColumns(["saved", "researching", "applied", "interviewing", "offer", "decided", "closed"]);
    expect(readHiddenColumns()).toEqual([]);
  });

  it("start with Considering, Decided and Closed hidden, until the person chooses", () => {
    expect(readHiddenColumns()).toEqual(["saved", "decided", "closed"]);
    writeHiddenColumns([]);
    expect(readHiddenColumns()).toEqual([]);
    writeHiddenColumns(["decided"]);
    expect(readHiddenColumns()).toEqual(["decided"]);
  });

  it("hide the starting columns when what was saved is not a list of columns", async () => {
    fakeViewChoiceServer({ "pipeline.board-hidden": { closed: true } });
    await readViewChoices();
    expect(readHiddenColumns()).toEqual(["saved", "decided", "closed"]);
  });
});
