import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { listed, useSideBarExpanded } from "./sideBar";
import { fakeViewChoiceServer } from "../test/viewChoicesServer";

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

describe("whether the side bar shows its labels", () => {
  it("starts collapsed, and opens and closes as the person leaves it, saved with the account", async () => {
    const server = fakeViewChoiceServer();
    const { result } = renderHook(() => useSideBarExpanded());
    await waitFor(() => expect(server.read).toHaveBeenCalled());
    expect(result.current[0]).toBe(false);

    act(() => result.current[1]());
    expect(result.current[0]).toBe(true);
    await waitFor(() => expect(server.saved()["sidebar.expanded"]).toBe(true));

    act(() => result.current[1]());
    expect(result.current[0]).toBe(false);
    await waitFor(() => expect(server.saved()["sidebar.expanded"]).toBe(false));
  });

  it("opens expanded on the next visit, in any browser, when the person left it so", async () => {
    fakeViewChoiceServer({ "sidebar.expanded": true });
    const { result } = renderHook(() => useSideBarExpanded());
    await waitFor(() => expect(result.current[0]).toBe(true));
  });

  it("stays collapsed when what is stored is not true or false", async () => {
    const server = fakeViewChoiceServer({ "sidebar.expanded": "yes" });
    const { result } = renderHook(() => useSideBarExpanded());
    await waitFor(() => expect(server.read).toHaveBeenCalled());
    expect(result.current[0]).toBe(false);
  });
});
