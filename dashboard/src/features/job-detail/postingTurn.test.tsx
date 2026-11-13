import { act, render, renderHook, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Job } from "../../api";
import { ErrorBoundary } from "../../ui/ErrorBoundary";
import { jobFixture } from "../../test/fixtures";
import { forgetTurnSpeed, turnPosting, useHeld, useShownPosting } from "./postingTurn";

const first: Job = { ...jobFixture, id: 101, title: "First" };
const second: Job = { ...jobFixture, id: 202, title: "Second" };

type Inputs = { fresh: Job | null; wanted: number; loading: boolean; failed?: boolean; place?: number | null; returning?: boolean };

/** The hook over a real scroll box, as the posting screen uses it. */
function shownPosting(initial: Inputs) {
  const box = { current: document.createElement("div") };
  document.body.appendChild(box.current);
  const hook = renderHook(
    ({ fresh, wanted, loading, failed = false, place = null, returning = false }: Inputs) =>
      useShownPosting(fresh, { wanted, loading, failed, place, box, returning }),
    { initialProps: initial },
  );
  return { ...hook, box: box.current };
}

afterEach(() => {
  forgetTurnSpeed();
  document.body.replaceChildren();
  delete document.documentElement.dataset.postingTurn;
  vi.restoreAllMocks();
  Reflect.deleteProperty(document, "startViewTransition");
});

describe("useShownPosting", () => {
  it("draws nothing while the first posting loads, then that posting", () => {
    const { result, rerender } = shownPosting({ fresh: null, wanted: 101, loading: true });
    expect(result.current).toEqual({ job: null, turning: false });
    rerender({ fresh: first, wanted: 101, loading: false });
    expect(result.current).toEqual({ job: first, turning: false });
  });

  it("keeps the posting on show while the next one loads, then turns to it at its top", async () => {
    const { result, rerender, box } = shownPosting({ fresh: first, wanted: 101, loading: false });
    box.scrollTop = 300;

    rerender({ fresh: null, wanted: 202, loading: true });
    expect(result.current, "the old posting, for the eye only").toEqual({ job: first, turning: true });
    expect(box.scrollTop, "where it was read to").toBe(300);

    await act(async () => {
      rerender({ fresh: second, wanted: 202, loading: false });
    });
    expect(result.current).toEqual({ job: second, turning: false });
    expect(box.scrollTop).toBe(0);
  });

  it("a posting gone back to opens where it was left; one stepped to again opens at its top", async () => {
    const { result, rerender, box } = shownPosting({ fresh: first, wanted: 101, loading: false });
    const turnTo = async (inputs: Inputs) => {
      await act(async () => {
        rerender(inputs);
      });
    };
    box.scrollTop = 300;
    await turnTo({ fresh: second, wanted: 202, loading: false });
    expect(box.scrollTop).toBe(0);
    box.scrollTop = 120;

    // Back in history: the first posting, where it was read to.
    await turnTo({ fresh: first, wanted: 101, loading: false, returning: true });
    expect(result.current.job).toBe(first);
    expect(box.scrollTop).toBe(300);
    // Forward: the second, where that one was left.
    await turnTo({ fresh: second, wanted: 202, loading: false, returning: true });
    expect(box.scrollTop).toBe(120);
    // Opened again by a link, not by history: its top.
    box.scrollTop = 50;
    await turnTo({ fresh: first, wanted: 101, loading: false });
    expect(box.scrollTop).toBe(0);
  });

  it("follows the same posting changed in place at once, with no turn", () => {
    const { result, rerender, box } = shownPosting({ fresh: first, wanted: 101, loading: false });
    box.scrollTop = 300;
    const starred = { ...first, is_favorite: true };
    rerender({ fresh: starred, wanted: 101, loading: false });
    expect(result.current).toEqual({ job: starred, turning: false });
    expect(box.scrollTop, "nothing sent the reader back to the top").toBe(300);
  });

  it("holds nothing over a posting that failed to load", async () => {
    const { result, rerender } = shownPosting({ fresh: first, wanted: 101, loading: false });
    rerender({ fresh: null, wanted: 202, loading: false, failed: true });
    expect(result.current, "the failure is shown, not the old posting").toEqual({ job: null, turning: false });
    // And the one after it starts from nothing: no old posting comes back for a frame.
    rerender({ fresh: null, wanted: 303, loading: true });
    expect(result.current.job).toBeNull();
  });

  it("steps along the list the way the list runs, and opens a link with no way", async () => {
    const ways: string[] = [];
    Object.defineProperty(document, "startViewTransition", {
      configurable: true,
      value: (update: () => Promise<void>) => {
        ways.push(document.documentElement.dataset.postingTurn ?? "none");
        const done = Promise.resolve().then(update);
        return { ready: done, finished: done, updateCallbackDone: done, skipTransition: () => undefined };
      },
    });
    const third: Job = { ...jobFixture, id: 303, title: "Third" };
    const { result, rerender } = shownPosting({ fresh: first, wanted: 101, loading: false, place: 4 });
    const turnTo = async (inputs: Inputs) => {
      vi.useFakeTimers();
      rerender(inputs);
      await act(async () => {
        await vi.runAllTimersAsync();
      });
      vi.useRealTimers();
    };
    await turnTo({ fresh: second, wanted: 202, loading: false, place: 5 });
    await turnTo({ fresh: first, wanted: 101, loading: false, place: 4 });
    // Opened from a link on the posting: it has no place in a list.
    await turnTo({ fresh: third, wanted: 303, loading: false, place: null });
    expect(ways).toEqual(["next", "previous", "open"]);
    expect(result.current.job).toBe(third);
    expect(document.documentElement.dataset.postingTurn, "nothing left on the root").toBeUndefined();
  });
});

describe("turnPosting", () => {
  it("names only the reading area that turns, and only for the turn", async () => {
    let update: (() => Promise<void>) | null = null;
    let end = () => {};
    const finished = new Promise<void>((resolve) => { end = resolve; });
    Object.defineProperty(document, "startViewTransition", {
      configurable: true,
      value: (callback: () => Promise<void>) => {
        update = callback;
        return { ready: finished, finished, updateCallbackDone: finished, skipTransition: () => undefined };
      },
    });
    const box = document.body.appendChild(document.createElement("div"));
    const other = document.body.appendChild(document.createElement("div"));
    const commit = vi.fn();
    turnPosting(box, "next", commit);
    expect(box.style.getPropertyValue("view-transition-name")).toBe("posting");
    expect(other.style.getPropertyValue("view-transition-name")).toBe("");
    expect(commit, "the document changes inside the turn").not.toHaveBeenCalled();

    vi.useFakeTimers();
    const updated = update!();
    await vi.runAllTimersAsync();
    await updated;
    vi.useRealTimers();
    expect(commit).toHaveBeenCalledTimes(1);

    end();
    await finished;
    await Promise.resolve();
    expect(box.style.getPropertyValue("view-transition-name")).toBe("");
  });

  it("a turn another has overtaken never commits", async () => {
    const updates: (() => Promise<void>)[] = [];
    const skipped: number[] = [];
    Object.defineProperty(document, "startViewTransition", {
      configurable: true,
      value: (callback: () => Promise<void>) => {
        const at = updates.push(callback) - 1;
        const done = Promise.resolve();
        return { ready: done, finished: done, updateCallbackDone: done, skipTransition: () => skipped.push(at) };
      },
    });
    const box = document.body.appendChild(document.createElement("div"));
    const commit = vi.fn();
    const cancel = turnPosting(box, "next", commit);
    cancel();
    expect(skipped).toEqual([0]);
    await updates[0]();
    expect(commit).not.toHaveBeenCalled();
  });

  it("the caller's own redraw after the change leaves the turn to finish", async () => {
    let update: (() => Promise<void>) | null = null;
    const skip = vi.fn();
    Object.defineProperty(document, "startViewTransition", {
      configurable: true,
      value: (callback: () => Promise<void>) => {
        update = callback;
        const done = Promise.resolve();
        return { ready: done, finished: done, updateCallbackDone: done, skipTransition: skip };
      },
    });
    const commit = vi.fn();
    const cancel = turnPosting(document.body.appendChild(document.createElement("div")), "next", commit);
    vi.useFakeTimers();
    const updated = update!();
    // What React does when the change is drawn: the effect that began the turn cleans up.
    cancel();
    await vi.runAllTimersAsync();
    await updated;
    vi.useRealTimers();
    expect(commit).toHaveBeenCalledTimes(1);
    expect(skip, "a skipped turn would show no motion at all").not.toHaveBeenCalled();
  });

  it("a browser that held the page still before a turn began gets no more turns", async () => {
    const started = vi.fn();
    let update: (() => Promise<void>) | null = null;
    Object.defineProperty(document, "startViewTransition", {
      configurable: true,
      value: (callback: () => Promise<void>) => {
        started();
        update = callback;
        const done = Promise.resolve();
        return { ready: done, finished: done, updateCallbackDone: done, skipTransition: () => undefined };
      },
    });
    const box = document.body.appendChild(document.createElement("div"));
    vi.useFakeTimers();
    // Begun on time: the next one is a turn too.
    turnPosting(box, "next", () => undefined);
    vi.advanceTimersByTime(20);
    void update!();
    await vi.runAllTimersAsync();
    turnPosting(box, "next", () => undefined);
    expect(started).toHaveBeenCalledTimes(2);
    // Two seconds with nothing running, not even the timer that guards the turn.
    vi.setSystemTime(Date.now() + 2000);
    const now = vi.spyOn(performance, "now").mockReturnValue(performance.now() + 2000);
    void update!();
    await vi.runAllTimersAsync();
    now.mockRestore();
    vi.useRealTimers();

    const commit = vi.fn();
    turnPosting(box, "next", commit);
    expect(started, "no third turn was asked for").toHaveBeenCalledTimes(2);
    expect(commit, "the posting changes at once").toHaveBeenCalledTimes(1);
  });

  it("skips a turn the browser has not begun in time, which runs its change at once", () => {
    const skip = vi.fn();
    Object.defineProperty(document, "startViewTransition", {
      configurable: true,
      value: () => {
        const never = new Promise<void>(() => undefined);
        return { ready: never, finished: never, updateCallbackDone: never, skipTransition: skip };
      },
    });
    vi.useFakeTimers();
    turnPosting(document.body.appendChild(document.createElement("div")), "open", () => undefined);
    vi.advanceTimersByTime(150);
    expect(skip).not.toHaveBeenCalled();
    vi.advanceTimersByTime(100);
    expect(skip).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });

  it("with no view transitions, changes the posting at once", () => {
    const commit = vi.fn();
    turnPosting(document.body.appendChild(document.createElement("div")), "next", commit);
    expect(commit).toHaveBeenCalledTimes(1);
  });

  /* A turn is started from a control the turn itself takes away (the next
     posting at the foot, a link under More like this), so something has to
     hold the keyboard afterwards. As an overlay the dialog does; as the page
     there is none, and focus would fall to the body. */
  it.each([
    ["an overlay", "dialog"],
    ["the page", null],
  ] as const)("leaves the keyboard on the posting when the turn is %s", async (_name, role) => {
    const holder = document.body.appendChild(document.createElement("main"));
    holder.className = "cover";
    holder.tabIndex = -1;
    if (role) holder.setAttribute("role", role);
    const box = holder.appendChild(document.createElement("div"));
    const gone = box.appendChild(document.createElement("button"));
    gone.focus();
    expect(document.activeElement).toBe(gone);

    turnPosting(box, "next", () => gone.remove());
    await Promise.resolve();

    expect(document.activeElement).toBe(holder);
  });

  it("leaves focus where it is when it never left the posting", async () => {
    const holder = document.body.appendChild(document.createElement("main"));
    holder.className = "cover";
    holder.tabIndex = -1;
    const box = holder.appendChild(document.createElement("div"));
    // The pager lives in the bar, outside the reading area and inside the
    // cover: it survives the turn, so it keeps the keyboard.
    const pager = holder.appendChild(document.createElement("button"));
    pager.focus();

    turnPosting(box, "next", () => undefined);
    await Promise.resolve();

    expect(document.activeElement).toBe(pager);
  });
});

describe("useHeld", () => {
  it("keeps the last value from before the hold, and lets go with it", () => {
    const { result, rerender } = renderHook(({ value, hold }: { value: string | null; hold: boolean }) => useHeld(value, hold), {
      initialProps: { value: "rows of the first" as string | null, hold: false },
    });
    rerender({ value: null, hold: true });
    expect(result.current).toBe("rows of the first");
    rerender({ value: "rows of the second", hold: false });
    expect(result.current).toBe("rows of the second");
  });
});

describe("ErrorBoundary resetKey", () => {
  function Posting({ broken }: { broken: boolean }) {
    if (broken) throw new Error("could not draw");
    return <p>the next posting</p>;
  }

  it("drops a caught error when the thing shown changes, and keeps it while it does not", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const view = (resetKey: string, broken: boolean) => (
      <ErrorBoundary resetKey={resetKey} fallback={() => <p>failed</p>}>
        <Posting broken={broken} />
      </ErrorBoundary>
    );
    const { rerender } = render(view("position:1", true));
    expect(screen.getByText("failed")).toBeInTheDocument();
    // The same posting drawn again: a healthy child does not clear the boundary by itself.
    rerender(view("position:1", false));
    expect(screen.getByText("failed")).toBeInTheDocument();
    rerender(view("position:2", false));
    expect(screen.getByText("the next posting")).toBeInTheDocument();
    expect(screen.queryByText("failed")).toBeNull();
  });
});
