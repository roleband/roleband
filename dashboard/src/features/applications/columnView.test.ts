import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { readHiddenColumns, writeHiddenColumns } from "./columnView";

/* Hidden columns are this browser's preference: kept in board order, never
 * all of them, and until chosen, or when storage cannot be read, the board
 * hides Considering, Decided and Closed. */

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

  it("start with Considering, Decided and Closed hidden, until the person chooses", () => {
    expect(readHiddenColumns()).toEqual(["saved", "decided", "closed"]);
    writeHiddenColumns([]);
    expect(readHiddenColumns()).toEqual([]);
    writeHiddenColumns(["decided"]);
    expect(readHiddenColumns()).toEqual(["decided"]);
  });

  it("clear the Closed choice a browser kept before, once the person chooses", () => {
    localStorage.setItem("roleband.pipeline-closed-hidden", "1");
    expect(readHiddenColumns()).toEqual(["saved", "decided", "closed"]);
    writeHiddenColumns(["saved"]);
    expect(readHiddenColumns()).toEqual(["saved"]);
    expect(localStorage.getItem("roleband.pipeline-closed-hidden")).toBeNull();
  });

  it("hide the starting columns when storage cannot be read, or holds something else", () => {
    localStorage.setItem("roleband.pipeline-hidden-columns", "{not json");
    expect(readHiddenColumns()).toEqual(["saved", "decided", "closed"]);
    localStorage.setItem("roleband.pipeline-hidden-columns", JSON.stringify({ closed: true }));
    expect(readHiddenColumns()).toEqual(["saved", "decided", "closed"]);
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(readHiddenColumns()).toEqual(["saved", "decided", "closed"]);
  });

  it("drop a write that storage refuses, without throwing", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("full");
    });
    expect(() => writeHiddenColumns(["closed"])).not.toThrow();
  });
});
