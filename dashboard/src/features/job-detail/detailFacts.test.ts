import { describe, expect, it } from "vitest";
import { msg } from "../../test/msg";
import { postingTeam, postingWorkplace } from "./detailFacts";

const posting = (over: { team?: string | null; department?: string | null; company?: string } = {}) => ({
  team: null, department: null, company: "google", ...over,
});

describe("postingTeam", () => {
  it("names the team, and falls back to the department", () => {
    expect(postingTeam(posting({ team: "Search Quality", department: "Product" }))).toBe("Search Quality");
    expect(postingTeam(posting({ department: "Product" }))).toBe("Product");
  });

  it("says nothing when the posting names neither", () => {
    expect(postingTeam(posting())).toBeNull();
    expect(postingTeam(posting({ team: "  ", department: "" }))).toBeNull();
  });

  it("says nothing when the field only repeats the company, by its name or its slug", () => {
    expect(postingTeam(posting({ team: "Google" }))).toBeNull();
    expect(postingTeam(posting({ team: " google " }))).toBeNull();
    expect(postingTeam(posting({ department: "GOOGLE" }))).toBeNull();
  });

  it("reads the department when the team field is blank or only repeats the company", () => {
    expect(postingTeam(posting({ team: "  ", department: "Product" }))).toBe("Product");
    expect(postingTeam(posting({ team: "Google", department: "Product" }))).toBe("Product");
    expect(postingTeam(posting({ team: "Google", department: "Google" }))).toBeNull();
  });

  it("keeps a team that only starts with the company's name", () => {
    expect(postingTeam(posting({ team: "Google Cloud" }))).toBe("Google Cloud");
  });
});

describe("postingWorkplace", () => {
  it("says where the work happens in the reader's words", () => {
    expect(postingWorkplace({ workplace_type: "remote" })).toBe(msg("taxonomy-workplace-remote"));
    expect(postingWorkplace({ workplace_type: "hybrid" })).toBe(msg("taxonomy-workplace-hybrid"));
    expect(postingWorkplace({ workplace_type: "onsite" })).toBe(msg("taxonomy-workplace-onsite"));
  });

  it("says nothing when the posting does not say, never a dash", () => {
    expect(postingWorkplace({ workplace_type: "unknown" })).toBeNull();
    expect(postingWorkplace({ workplace_type: "somewhere_new" })).toBeNull();
  });
});
