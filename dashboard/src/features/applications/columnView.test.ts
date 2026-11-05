import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { readHiddenColumns, writeHiddenColumns } from "./columnView";

/* Hidden columns are this browser's preference: kept in board order, never
 * all of them, and a storage that throws shows every column. */

beforeEach(() => localStorage.clear());
afterEach(() => vi.restoreAllMocks());

describe("hidden columns", () => {
  it("come back in board order, without names the board does not have", () => {
    writeHiddenColumns(["closed", "saved"]);
    expect(readHiddenColumns()).toEqual(["saved", "closed"]);
    localStorage.setItem("roleband.pipeline-hidden-columns", JSON.stringify(["decided", "networking", "nonsense"]));
    expect(readHiddenColumns()).toEqual(["decided"]);
  });

  it("never hide every column", () => {
    localStorage.setItem("roleband.pipeline-hidden-columns",
      JSON.stringify(["saved", "researching", "applied", "interviewing", "offer", "decided", "closed"]));
    expect(readHiddenColumns()).toEqual([]);
  });

  it("carry over the Closed column a browser hid before, and stop reading it once written", () => {
    localStorage.setItem("roleband.pipeline-closed-hidden", "1");
    expect(readHiddenColumns()).toEqual(["closed"]);
    writeHiddenColumns([]);
    expect(readHiddenColumns()).toEqual([]);
    expect(localStorage.getItem("roleband.pipeline-closed-hidden")).toBeNull();
  });

  it("show every column when storage cannot be read, or holds something else", () => {
    localStorage.setItem("roleband.pipeline-hidden-columns", "{not json");
    expect(readHiddenColumns()).toEqual([]);
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(readHiddenColumns()).toEqual([]);
  });

  it("drop a write that storage refuses, without throwing", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("full");
    });
    expect(() => writeHiddenColumns(["closed"])).not.toThrow();
  });
});
