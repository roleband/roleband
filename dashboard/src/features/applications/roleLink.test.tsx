import { renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { useRoleLink } from "./roleLink";

/* A role opened from a pipeline view opens its posting over the view, on the
 * tab its stage asks for, and carries nothing else. */

const card = (job_id: number, company = "acme", stage: "saved" | "applied" = "applied") => ({ job_id, company, stage });

function link() {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <MemoryRouter initialEntries={["/pipeline/board"]}>{children}</MemoryRouter>
  );
  return renderHook(() => useRoleLink(), { wrapper }).result.current;
}

describe("a role's link from a pipeline view", () => {
  it("opens the role's posting over the view, and carries no list to step along", () => {
    const to = link()(card(1, "a"));
    expect(to.to).toEqual({ pathname: "/company/a/job/1", search: "?tab=workspace" });
    expect(to.state.backgroundLocation).toMatchObject({ pathname: "/pipeline/board" });
    expect(Object.keys(to.state), "the view's order is not handed to the cover").toEqual(["backgroundLocation"]);
  });

  it("opens a saved role on its posting and a pursued one on the person's own work", () => {
    expect(link()(card(1, "a", "saved")).to.search).toBe("?tab=posting");
    expect(link()(card(1, "a", "applied")).to.search).toBe("?tab=workspace");
  });

  it("takes the tab it is asked for", () => {
    expect(link()(card(1, "a", "applied"), "posting").to.search).toBe("?tab=posting");
  });
});
