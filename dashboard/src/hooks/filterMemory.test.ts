import { beforeEach, describe, expect, it } from "vitest";
import { fakeViewChoiceServer } from "../test/viewChoicesServer";
import {
  amount,
  decodeParams,
  decodeShape,
  encodeShape,
  flag,
  forgetEntry,
  oneOf,
  readEntry,
  slugs,
  text,
  writeEntry,
  type MemoryShape,
} from "./filterMemory";
import { readViewChoices } from "./viewChoicesRead";

/* What comes back from the store is DATA, not state. These are the contracts
 * that make restoring a stored blob safe: a shape is a whitelist as well as a
 * validator, every decoder refuses what it cannot vouch for, and no failure to
 * read or save may reach the screen. */

const key = "board";
let server: ReturnType<typeof fakeViewChoiceServer>;
const settle = () => new Promise((done) => setTimeout(done, 0));

beforeEach(async () => {
  server = fakeViewChoiceServer();
  await readViewChoices();
});

describe("the filter memory store", () => {
  it("keeps a screen's memory with the person's settings, under its own name", async () => {
    writeEntry(key, { company: ["openai"] });
    expect(readEntry(key)).toEqual({ company: ["openai"] });
    await settle();
    expect(server.saved()).toEqual({ "filters.board": { company: ["openai"] } });
  });

  it("reads a memory forgotten as nothing, and one left empty as empty", async () => {
    writeEntry("board:open", {});
    writeEntry(key, { company: ["openai"] });
    forgetEntry(key);
    expect(readEntry(key)).toBeNull();
    expect(readEntry("board:open")).toEqual({});
    await settle();
    expect(server.saved()).toEqual({ "filters.board": null, "filters.board:open": {} });
  });

  it("reads nothing before the person's choices have come back, and holds a write that fails to save", async () => {
    fakeViewChoiceServer({ "filters.board": { company: ["amazon"] } });
    expect(readEntry(key), "the read is on its way").toBeNull();
    await readViewChoices();
    expect(readEntry(key)).toEqual({ company: ["amazon"] });
    server = fakeViewChoiceServer();
    await readViewChoices();
    server.save.mockRejectedValue(new Error("offline"));
    expect(() => writeEntry(key, { a: 1 })).not.toThrow();
    await settle();
    expect(readEntry(key)).toEqual({ a: 1 });
  });
});

describe("the decoders", () => {
  it("keeps only the strings out of a slug list, and bounds what it keeps", () => {
    expect(slugs(["openai", "amazon"])).toEqual(["openai", "amazon"]);
    // A mixed array is a partial loss, not a total one: the good slugs still
    // narrow the list the reader left it narrowed to.
    expect(slugs(["openai", 7, null, "", "amazon"])).toEqual(["openai", "amazon"]);
    expect(slugs("openai")).toBeUndefined();
    expect(slugs({ 0: "openai" })).toBeUndefined();
    expect(slugs(Array.from({ length: 500 }, (_, i) => `co_${i}`))).toHaveLength(200);
    expect(slugs(["x".repeat(500)])).toEqual([]);
  });

  it("refuses a number that cannot reach the wire, and keeps an explicit null", () => {
    expect(amount(200000)).toBe(200000);
    expect(amount(null)).toBeNull();
    // `Infinity` and `NaN` survive a hand edit and serialize to garbage.
    expect(amount(Number.POSITIVE_INFINITY)).toBeUndefined();
    expect(amount(Number.NaN)).toBeUndefined();
    expect(amount("200000")).toBeUndefined();
  });

  it("answers only for a value still in the vocabulary", () => {
    const viewed = oneOf(["", "unread", "read"] as const);
    expect(viewed("unread")).toBe("unread");
    expect(viewed("")).toBe("");
    // A value retired since the write. This is the only decoder that can tell.
    expect(viewed("not-for-me")).toBeUndefined();
  });

  it("takes a boolean as itself and nothing else as one", () => {
    expect(flag(true)).toBe(true);
    expect(flag(false)).toBe(false);
    expect(flag("true")).toBeUndefined();
    expect(flag(1)).toBeUndefined();
    expect(text("relevance")).toBe("relevance");
    expect(text(7)).toBeUndefined();
  });
});

interface Sample {
  company: string[];
  discloses_pay: boolean;
  comp_min: number | null;
  q: string;
}

const shape: MemoryShape<Sample> = { company: slugs, discloses_pay: flag, comp_min: amount };

describe("the shape", () => {
  it("is the whitelist as well as the validator", () => {
    // `q` has no decoder, so it is neither restorable nor storable — which is
    // how a screen keeps its search box out of memory without a second list.
    const stored = { company: ["openai"], discloses_pay: true, comp_min: 200000, q: "staff" };
    expect(decodeShape(shape, stored)).toEqual({
      company: ["openai"],
      discloses_pay: true,
      comp_min: 200000,
    });
    expect(
      encodeShape(shape, { company: ["openai"], discloses_pay: false, comp_min: null, q: "staff" }),
    ).toEqual({ company: ["openai"], discloses_pay: false, comp_min: null });
  });

  it("lets a caller's default show through wherever the blob is wrong", () => {
    // Every key present, every one of the wrong type: the result is empty, so
    // `{...defaults, ...restored}` is exactly `defaults`.
    expect(decodeShape(shape, { company: "openai", discloses_pay: "yes", comp_min: "x" })).toEqual({});
    expect(decodeShape(shape, null)).toEqual({});
    expect(decodeShape(shape, ["company"])).toEqual({});
    // A key the blob does not carry is absent rather than undefined, or the
    // spread above would overwrite the default with nothing.
    expect("company" in decodeShape(shape, { discloses_pay: true })).toBe(false);
  });
});

describe("a remembered query string", () => {
  it("keeps every value of the keys it was asked for, and nothing else", () => {
    const stored = { status: ["unread"], category: ["sync_failed", "closed"], q: ["staff"] };
    expect(decodeParams(stored, ["status", "priority", "category"])).toEqual({
      status: ["unread"],
      category: ["sync_failed", "closed"],
    });
    // An empty list is not a remembered lens: it would write `?category=` and
    // mean something the screen never chose.
    expect(decodeParams({ status: [] }, ["status"])).toEqual({});
    expect(decodeParams("status=unread", ["status"])).toEqual({});
  });
});
