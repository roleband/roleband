import { act, renderHook } from "@testing-library/react";
import { StrictMode, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, type Job, type PostingTextResult } from "../../api";
import { SLOW_AFTER_MS, usePostingText } from "./postingText";

/** A posting as the detail sends one that opened with no text. */
const blank = (id: number, readable = true) =>
  ({ id, company: "spotify", description_text: null, description_sections: [], description_readable: readable }) as unknown as Job;

const answer = (outcome: PostingTextResult["outcome"]): PostingTextResult => ({
  outcome,
  description_text: outcome === "read" || outcome === "already_read" ? "Lead the platform." : null,
  description_sections:
    outcome === "read" || outcome === "already_read"
      ? [{ key: "summary", title: "Summary", content: "Lead the platform." }]
      : [],
});

/** A request that answers when the test says so. */
function pending() {
  let settle!: (result: PostingTextResult) => void;
  let fail!: (error: Error) => void;
  const promise = new Promise<PostingTextResult>((resolve, reject) => {
    settle = resolve;
    fail = reject;
  });
  return { promise, settle, fail };
}

describe("usePostingText", () => {
  const show = vi.fn();
  const reread = vi.fn();

  beforeEach(() => {
    vi.useFakeTimers();
    show.mockReset();
    reread.mockReset();
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  const hook = (job: Job | null, wrapper?: ({ children }: { children: ReactNode }) => ReactNode) =>
    renderHook(({ posting }) => usePostingText(posting, show, reread), { initialProps: { posting: job }, wrapper });

  it("reads once, says it is reading from the first frame, then slow, then lands the text", async () => {
    const request = pending();
    const read = vi.spyOn(api, "readPostingText").mockReturnValue(request.promise);
    const { result, rerender } = hook(blank(7));

    expect(result.current.read?.phase).toBe("reading");
    expect(read).toHaveBeenCalledTimes(1);
    expect(read).toHaveBeenCalledWith(7, false);

    act(() => vi.advanceTimersByTime(SLOW_AFTER_MS));
    expect(result.current.read?.phase).toBe("slow");

    rerender({ posting: blank(7) });
    expect(read).toHaveBeenCalledTimes(1); // a re-render is not another open

    await act(async () => request.settle(answer("read")));
    expect(show).toHaveBeenCalledWith(7, answer("read"));
    expect(reread).toHaveBeenCalledTimes(1); // the text moves what the pay panel says
    // The screen writes the text into the posting, which is no longer readable.
    rerender({ posting: { ...blank(7, false), description_text: "Lead the platform." } as Job });
    expect(result.current.read).toBeNull();
    expect(result.current.arrived).toBe(true);
  });

  it("asks nothing for a posting that has nothing to read", () => {
    const read = vi.spyOn(api, "readPostingText");
    const { result } = hook(blank(7, false));
    expect(read).not.toHaveBeenCalled();
    expect(result.current.read).toBeNull();
  });

  it("text another writer stored is shown, and needs no second read of the posting", async () => {
    vi.spyOn(api, "readPostingText").mockResolvedValue(answer("already_read"));
    hook(blank(7));
    await act(async () => {});
    expect(show).toHaveBeenCalledWith(7, answer("already_read"));
    expect(reread).not.toHaveBeenCalled();
  });

  it("a failed read is said, and Try again asks again on purpose", async () => {
    const read = vi.spyOn(api, "readPostingText").mockResolvedValueOnce(answer("failed"));
    const { result } = hook(blank(7));
    await act(async () => {});
    expect(result.current.read?.phase).toBe("failed");
    expect(show).not.toHaveBeenCalled();

    const again = pending();
    read.mockReturnValueOnce(again.promise);
    act(() => result.current.read?.retry());
    expect(read).toHaveBeenLastCalledWith(7, true);
    expect(result.current.read?.phase).toBe("reading");

    await act(async () => again.settle(answer("read")));
    expect(show).toHaveBeenCalledWith(7, answer("read"));
  });

  it("a request that never answers is a failure, not a line that runs forever", async () => {
    const request = pending();
    vi.spyOn(api, "readPostingText").mockReturnValue(request.promise);
    const { result } = hook(blank(7));
    await act(async () => request.fail(new Error("offline")));
    expect(result.current.read?.phase).toBe("failed");
  });

  it("drops an answer for a posting no longer on screen", async () => {
    const first = pending();
    const read = vi.spyOn(api, "readPostingText").mockReturnValueOnce(first.promise);
    const { result, rerender } = hook(blank(7));

    read.mockReturnValueOnce(new Promise(() => {}));
    rerender({ posting: blank(8) }); // the pager turned to the next posting
    await act(async () => first.settle(answer("read")));

    expect(show).not.toHaveBeenCalled();
    expect(result.current.read?.phase).toBe("reading"); // posting 8's read
    expect(read).toHaveBeenLastCalledWith(8, false);
  });

  it("under StrictMode reads once and still lands the answer", async () => {
    // StrictMode unmounts and mounts again before the answer comes: a read
    // retired by that practice unmount would leave the line running forever.
    const request = pending();
    const read = vi.spyOn(api, "readPostingText").mockReturnValue(request.promise);
    hook(blank(7), ({ children }) => <StrictMode>{children}</StrictMode>);

    await act(async () => request.settle(answer("read")));
    expect(read).toHaveBeenCalledTimes(1);
    expect(show).toHaveBeenCalledWith(7, answer("read"));
  });
});
