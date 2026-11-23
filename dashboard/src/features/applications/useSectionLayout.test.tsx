import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { readViewChoices } from "../../hooks/viewChoicesRead";
import { fakeViewChoiceServer } from "../../test/viewChoicesServer";
import { useSectionLayout } from "./useSectionLayout";
import { sectionOrder } from "./workspaceSections";

/* The Workspace's layout is kept per stage, with the person's settings. A
 * render for a stage holds that stage's own order and hidden blocks, never
 * the previous stage's for a frame; and a late Undo changes the stage it was
 * made in. */

let server: ReturnType<typeof fakeViewChoiceServer>;
/** The Workspace's layouts as the database holds them, by stage. */
const saved = (stage: string) => server.saved()[`workspace.${stage}`] as { hidden: string[]; order: string[] } | undefined;

beforeEach(() => {
  server = fakeViewChoiceServer();
});

const read = async () => {
  await act(() => readViewChoices().then(() => undefined));
};

describe("the Workspace's section layout", () => {
  it("draws nothing until the saved layout is read", async () => {
    server.hold({ "workspace.applied": { hidden: [], order: ["activity", "notes", "next"] } });
    const { result } = renderHook(() => useSectionLayout("applied", vi.fn()));
    expect(result.current.ready).toBe(false);
    await waitFor(() => expect(result.current.ready).toBe(true));
    expect(result.current.shown).toEqual(["activity", "notes", "next"]);
  });

  it("never draws a stage with the previous stage's order, not even for one render", async () => {
    server.hold({
      "workspace.applied": { hidden: [], order: ["activity", "notes", "next"] },
      "workspace.offer": { hidden: [], order: ["activity", "next", "notes"] },
    });
    await read();
    const seen: { stage: string; shown: string }[] = [];
    const { rerender } = renderHook(({ stage }) => {
      const layout = useSectionLayout(stage, vi.fn());
      seen.push({ stage, shown: layout.shown.join() });
      return layout;
    }, { initialProps: { stage: "applied" as "applied" | "offer" } });

    rerender({ stage: "offer" });

    const forOffer = seen.filter((one) => one.stage === "offer");
    expect(forOffer.length).toBeGreaterThan(0);
    for (const one of forOffer) expect(one.shown).toBe("activity,next,notes");
    expect(seen.find((one) => one.stage === "applied")?.shown).toBe("activity,notes,next");
  });

  it("saves an Undo to the stage it hid in, and leaves the stage now shown as it is", async () => {
    await read();
    const { result, rerender } = renderHook(({ stage }) => useSectionLayout(stage, vi.fn()), {
      initialProps: { stage: "applied" as "applied" | "offer" },
    });
    act(() => {
      result.current.hide("notes");
    });
    const undo = result.current.show;

    rerender({ stage: "offer" });
    act(() => {
      result.current.hide("activity");
    });
    const shownForOffer = result.current.shown.join();
    act(() => undo("notes"));

    await waitFor(() => expect(saved("applied")?.hidden).toEqual([]));
    expect(saved("offer")?.hidden).toEqual(["activity"]);
    expect(result.current.shown.join()).toBe(shownForOffer);
    expect(result.current.shown).not.toContain("activity");
    rerender({ stage: "applied" });
    expect(result.current.shown).toContain("notes");
  });

  it("saves a block moved, with the hidden ones kept in their places", async () => {
    server.hold({ "workspace.interviewing": { hidden: ["next"], order: sectionOrder("interviewing") } });
    await read();
    const { result } = renderHook(() => useSectionLayout("interviewing", vi.fn()));
    act(() => {
      result.current.step("interviews", 1);
    });
    expect(result.current.shown).toEqual(["notes", "interviews", "activity"]);
    await waitFor(() => expect(saved("interviewing")).toEqual({ hidden: ["next"], order: ["next", "notes", "interviews", "activity"] }));
  });

  it("keeps the last block shown", async () => {
    await read();
    const { result } = renderHook(() => useSectionLayout("applied", vi.fn()));
    for (const section of ["notes", "activity", "next"] as const) {
      act(() => {
        result.current.hide(section);
      });
    }
    expect(result.current.shown).toHaveLength(1);
  });

  it("keeps the last block shown when hides come before the page draws again", async () => {
    await read();
    const { result } = renderHook(() => useSectionLayout("applied", vi.fn()));
    const hid: boolean[] = [];
    act(() => {
      for (const section of ["notes", "activity", "next"] as const) hid.push(result.current.hide(section));
    });
    expect(hid).toEqual([true, true, false]);
    expect(result.current.shown).toEqual(["next"]);
    await waitFor(() => expect(saved("applied")?.hidden).toEqual(["notes", "activity"]));
  });

  it("says when a change was not saved, and keeps it on the page", async () => {
    await read();
    const failed = vi.fn();
    server.save.mockRejectedValueOnce(new Error("offline"));
    const { result } = renderHook(() => useSectionLayout("applied", failed));
    act(() => {
      result.current.hide("notes");
    });
    await waitFor(() => expect(failed).toHaveBeenCalledTimes(1));
    expect(result.current.shown).not.toContain("notes");
  });
});
