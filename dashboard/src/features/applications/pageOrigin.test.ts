import { describe, expect, it } from "vitest";
import { msg } from "../../test/msg";
import { backOf, originState } from "./pageOrigin";

/* A role's page goes back to the pipeline view it came from, as it was left;
 * from anywhere else, to the board. */

describe("the way back from a role's page", () => {
  it("returns to the view, its query and its own history state, named by its tab", () => {
    const tabs = { pipelineTabsLeft: { board: "q=stripe" } };
    const state = originState({ pathname: "/pipeline/list", search: "?quick=stale", state: tabs });
    expect(backOf(state)).toEqual({
      pathname: "/pipeline/list", search: "?quick=stale", state: tabs, view: msg("shell-tab-pipeline-list"),
    });
    expect(backOf(originState({ pathname: "/pipeline/up-next", search: "", state: null })).view)
      .toBe(msg("shell-tab-pipeline-up-next"));
  });

  it("carries nothing from a place that is not a pipeline view, and then goes to the board", () => {
    expect(originState({ pathname: "/radar", search: "?q=x", state: null })).toBeUndefined();
    expect(originState({ pathname: "/pipeline/101", search: "", state: null })).toBeUndefined();
    const board = { pathname: "/pipeline/board", search: "", state: undefined, view: msg("shell-tab-pipeline-board") };
    expect(backOf(undefined)).toEqual(board);
    expect(backOf({ pipelineOrigin: { pathname: "/settings", search: "" } })).toEqual(board);
    expect(backOf({ pipelineOrigin: "garbage" })).toEqual(board);
  });
});
