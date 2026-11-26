import { describe, expect, it } from "vitest";
import { listed } from "./sideBar";

const duplicates = { choice: "sidebar.duplicates", shown: false };

describe("which places the side bar lists", () => {
  it("lists a place that is not optional whatever is saved", () => {
    expect(listed(undefined, { "sidebar.duplicates": false })).toBe(true);
  });

  it("follows the place's default until the person answers, then the answer", () => {
    expect(listed(duplicates, {})).toBe(false);
    expect(listed(duplicates, { "sidebar.duplicates": true })).toBe(true);
    expect(listed({ choice: "sidebar.insights", shown: true }, { "sidebar.insights": false })).toBe(false);
  });

  it("keeps the default when what is stored is not true or false", () => {
    expect(listed(duplicates, { "sidebar.duplicates": "yes" })).toBe(false);
    expect(listed(duplicates, { "sidebar.duplicates": null })).toBe(false);
  });
});
