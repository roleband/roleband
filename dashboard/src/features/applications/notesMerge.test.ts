import { describe, expect, it } from "vitest";
import { mergeNotes } from "./notesMerge";

const page = (...lines: string[]) => lines.join("\n");

const base = page("# Prep", "", "- Read the posting", "", "Recruiter is Sam");

describe("notes written in two places at once", () => {
  it("takes the other side's notes when the page changed nothing, and the page's when the other side did not", () => {
    const theirs = page("# Prep", "", "- Read the posting", "", "Recruiter is Sam", "", "Comp band: 210-240k");
    expect(mergeNotes(base, base, theirs)).toBe(theirs);
    expect(mergeNotes(base, theirs, base)).toBe(theirs);
  });

  it("keeps a line the page added and a line written elsewhere in another place, each where it was written", () => {
    const mine = page("# Prep", "", "- Read the posting", "- Ask about the team", "", "Recruiter is Sam");
    const theirs = page("# Prep", "", "- Read the posting", "", "Recruiter is Sam", "", "Comp band: 210-240k");
    expect(mergeNotes(base, mine, theirs)).toBe(
      page("# Prep", "", "- Read the posting", "- Ask about the team", "", "Recruiter is Sam", "", "Comp band: 210-240k"),
    );
  });

  it("keeps both versions of a line both sides changed differently, the page's first, apart", () => {
    const mine = page("# Prep", "", "- Read the posting", "", "Recruiter is Sam Lee, call Friday");
    const theirs = page("# Prep", "", "- Read the posting", "", "Recruiter is Sam (sam@example.test)");
    expect(mergeNotes(base, mine, theirs)).toBe(
      page("# Prep", "", "- Read the posting", "", "Recruiter is Sam Lee, call Friday", "", "Recruiter is Sam (sam@example.test)"),
    );
  });

  it("writes a change both sides made the same way once", () => {
    const both = page("# Prep", "", "- Read the posting", "", "Recruiter is Sam Lee");
    expect(mergeNotes(base, both, both)).toBe(both);
    const mine = page("# Prep", "", "- Read the posting", "", "Recruiter is Sam Lee", "", "- Ask about the team");
    expect(mergeNotes(base, mine, both)).toBe(mine);
  });

  it("drops a line one side deleted when the other left it as it was", () => {
    const mine = page("# Prep", "", "Recruiter is Sam");
    const theirs = page("# Prep", "", "- Read the posting", "", "Recruiter is Sam", "", "Panel on Friday");
    expect(mergeNotes(base, mine, theirs)).toBe(page("# Prep", "", "Recruiter is Sam", "", "Panel on Friday"));
  });

  it("keeps both pages whole when each started from nothing", () => {
    expect(mergeNotes("", "Mine", "Written elsewhere")).toBe(page("Mine", "", "Written elsewhere"));
  });

  it("keeps every line of both sides for notes too long to match line by line", () => {
    const long = (prefix: string) => Array.from({ length: 2_100 }, (_, at) => `${prefix} ${at}`);
    const start = long("line").join("\n");
    const mine = [...long("line"), "mine"].join("\n");
    const theirs = ["theirs", ...long("line")].join("\n");
    const merged = mergeNotes(start, mine, theirs).split("\n");
    expect(merged).toContain("mine");
    expect(merged).toContain("theirs");
    expect(merged.filter((line) => line === "line 7")).toHaveLength(1);
  });

  it("keeps the page's lines, then the other side's it lacks, for long notes both started from nothing", () => {
    const long = (prefix: string) => Array.from({ length: 2_100 }, (_, at) => `${prefix} ${at}`);
    // The other side ends on the page's first line: matched line by line, its
    // own lines would come first.
    const mine = long("mine");
    const theirs = [...long("theirs"), "mine 0"];
    const merged = mergeNotes("", mine.join("\n"), theirs.join("\n")).split("\n");
    expect(merged).toEqual([...mine, "", ...long("theirs")]);
  });
});
