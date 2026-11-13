import { act, render } from "@testing-library/react";
import { MemoryRouter, useLocation, type Location } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api";
import { JobWorkspaceProvider, useJobActions } from "./JobWorkspace";

/* Where a posting opens, by where it was opened from. A list stays mounted
 * under the cover that opens over it. A posting that is the page itself has
 * nothing under it to keep, so the next posting takes its place as the page;
 * stacking a second cover there would open the screen again for every link
 * followed. */

vi.mock("../api", () => ({
  api: {
    markJobViewed: vi.fn().mockResolvedValue({}),
    compareSelection: vi.fn().mockResolvedValue({ job_ids: [] }),
    setCompareSelection: vi.fn(),
  },
}));

let verbs: ReturnType<typeof useJobActions>;
let here: Location;

function Probe() {
  verbs = useJobActions();
  here = useLocation();
  return null;
}

type Entry = string | { pathname: string; state: unknown };

function mountAt(entry: Entry) {
  render(
    <MemoryRouter initialEntries={[entry]}>
      <JobWorkspaceProvider>
        <Probe />
      </JobWorkspaceProvider>
    </MemoryRouter>,
  );
}

const state = () => here.state as { backgroundLocation?: { pathname: string }; steppedFrom?: string; postingList?: unknown } | null;

beforeEach(() => {
  vi.clearAllMocks();
});

describe("openJob", () => {
  it("from a list, opens a cover over that list and carries the list's rows", () => {
    mountAt("/");
    const list = [{ id: 7, company: "acme" }, { id: 8, company: "acme" }];
    act(() => verbs.openJob(7, "acme", list));
    expect(here.pathname).toBe("/company/acme/job/7");
    expect(state()?.backgroundLocation?.pathname).toBe("/");
    expect(state()?.postingList).toEqual(list);
    expect(state()?.steppedFrom).toBeUndefined();
    expect(api.markJobViewed).toHaveBeenCalledWith(7);
  });

  it("from a posting that is the page, takes its place as the page, one entry on", () => {
    mountAt("/company/acme/job/7");
    act(() => verbs.openJob(9, "globex"));
    expect(here.pathname).toBe("/company/globex/job/9");
    expect(state()?.backgroundLocation, "no cover over the first posting").toBeUndefined();
    expect(state()?.steppedFrom, "so Back knows the first posting is one entry back").toBe("posting");
  });

  it("the short address of a posting is the page too", () => {
    mountAt("/job/7");
    act(() => verbs.openJob(9));
    expect(here.pathname).toBe("/job/9");
    expect(state()?.backgroundLocation).toBeUndefined();
    expect(state()?.steppedFrom).toBe("posting");
  });

  it("from a posting's cover over a list, stays a cover over that list", () => {
    mountAt({ pathname: "/company/acme/job/7", state: { backgroundLocation: { pathname: "/pipeline", search: "", hash: "", state: null, key: "list" } } });
    act(() => verbs.openJob(9, "globex"));
    expect(here.pathname).toBe("/company/globex/job/9");
    expect(state()?.backgroundLocation?.pathname).toBe("/pipeline");
    expect(state()?.steppedFrom).toBeUndefined();
  });

  it("from the comparison, a role still stacks on it", () => {
    mountAt("/compare");
    act(() => verbs.openJob(9, "globex"));
    expect(state()?.backgroundLocation?.pathname).toBe("/compare");
    expect(state()?.steppedFrom).toBeUndefined();
  });
});
