import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { useSectionLayout } from "./useSectionLayout";
import { readHiddenSections, readSectionOrder, writeSectionOrder } from "./workspaceSections";

/* The Workspace's layout is kept per stage. A render for a stage holds that
 * stage's own order and hidden blocks, never the previous stage's for a
 * frame; and a late Undo writes the stage it was made in. */

beforeEach(() => localStorage.clear());

describe("the Workspace's section layout", () => {
  it("never draws a stage with the previous stage's order, not even for one render", () => {
    writeSectionOrder("applied", ["activity", "notes", "next"]);
    writeSectionOrder("offer", ["next", "outcome", "notes", "activity"]);
    const seen: { stage: string; shown: string }[] = [];
    const { rerender } = renderHook(({ stage }) => {
      const layout = useSectionLayout(stage);
      seen.push({ stage, shown: layout.shown.join() });
      return layout;
    }, { initialProps: { stage: "applied" as "applied" | "offer" } });

    rerender({ stage: "offer" });

    const forOffer = seen.filter((one) => one.stage === "offer");
    expect(forOffer.length).toBeGreaterThan(0);
    for (const one of forOffer) expect(one.shown).toBe(readSectionOrder("offer").join());
    expect(seen.find((one) => one.stage === "applied")?.shown).toBe("activity,notes,next");
  });

  it("writes an Undo to the stage it hid in, and leaves the stage now shown as it is", () => {
    const { result, rerender } = renderHook(({ stage }) => useSectionLayout(stage), {
      initialProps: { stage: "applied" as "applied" | "offer" },
    });
    act(() => {
      result.current.hide("notes");
    });
    expect(readHiddenSections("applied")).toEqual(["notes"]);
    const undo = result.current.show;

    rerender({ stage: "offer" });
    act(() => {
      result.current.hide("activity");
    });
    const shownForOffer = result.current.shown.join();
    act(() => undo("notes"));

    expect(readHiddenSections("applied")).toEqual([]);
    expect(readHiddenSections("offer")).toEqual(["activity"]);
    expect(result.current.shown.join()).toBe(shownForOffer);
    expect(result.current.shown).not.toContain("activity");
    rerender({ stage: "applied" });
    expect(result.current.shown).toContain("notes");
  });

  it("keeps the last block shown", () => {
    const { result } = renderHook(() => useSectionLayout("applied"));
    for (const section of ["notes", "activity", "next"] as const) {
      act(() => {
        result.current.hide(section);
      });
    }
    expect(result.current.shown).toHaveLength(1);
  });
});
