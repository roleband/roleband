import { describe, expect, it } from "vitest";
import { listedFor } from "./ageCopy";

describe("age captions", () => {
  it("captions one posting's listed age, and never as days open", () => {
    expect(listedFor(null)).toBeNull();
    expect(listedFor(0)).toBe("Listed today");
    expect(listedFor(1)).toBe("Listed for 1 day");
    expect(listedFor(170)).toBe("Listed for 170 days");
  });
});
