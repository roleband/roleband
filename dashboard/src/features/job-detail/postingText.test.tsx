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
    rerender({ posting: blank(8) }); // a link turned the cover to the next posting
    await act(async () => first.settle(answer("read")));

    expect(show).not.toHaveBeenCalled();
    expect(result.current.read?.phase).toBe("reading"); // posting 8's read
    expect(read).toHaveBeenLastCalledWith(8, false);
  });

  it("asks again on return for a posting whose read failed while another was shown", async () => {
    // A's read fails while B, which has nothing to read, is on screen. Back on
    // A, a posting still with no text must be asked again, not left reading.
    const first = pending();
    const read = vi.spyOn(api, "readPostingText").mockReturnValueOnce(first.promise);
    const { result, rerender } = hook(blank(7));

    rerender({ posting: blank(8, false) });
    await act(async () => first.settle(answer("failed")));

    const again = pending();
    read.mockReturnValueOnce(again.promise);
    rerender({ posting: blank(7) });
    expect(read).toHaveBeenLastCalledWith(7, false);
    expect(read).toHaveBeenCalledTimes(2);

    await act(async () => again.settle(answer("read")));
    expect(show).toHaveBeenCalledWith(7, answer("read"));
    expect(result.current.read?.phase).toBe("reading"); // until the screen writes the text in
  });

  it("asks again on a new open of a posting whose read failed while it was shown", async () => {
    // Failed on 7, then 8 with nothing to read, then 7 again: the same as
    // passing through a posting that has something to read.
    const read = vi.spyOn(api, "readPostingText").mockResolvedValueOnce(answer("failed"));
    const { result, rerender } = hook(blank(7));
    await act(async () => {});
    expect(result.current.read?.phase).toBe("failed");

    rerender({ posting: blank(8, false) });
    expect(result.current.read).toBeNull();
    const again = pending();
    read.mockReturnValueOnce(again.promise);
    rerender({ posting: blank(7) });

    expect(read).toHaveBeenCalledTimes(2);
    expect(read).toHaveBeenLastCalledWith(7, false); // an open, not Try again
    expect(result.current.read?.phase).toBe("reading");
    await act(async () => again.settle(answer("read")));
    expect(show).toHaveBeenCalledWith(7, answer("read"));
  });

  it("does not ask twice for a posting shown again while its read still runs", async () => {
    const first = pending();
    const read = vi.spyOn(api, "readPostingText").mockReturnValueOnce(first.promise);
    const { rerender } = hook(blank(7));

    rerender({ posting: blank(8, false) });
    rerender({ posting: blank(7) });
    expect(read).toHaveBeenCalledTimes(1);

    await act(async () => first.settle(answer("read")));
    expect(show).toHaveBeenCalledWith(7, answer("read"));
  });

  it("keeps the read of a posting that another readable posting interrupted", async () => {
    // 7 is still being read when 8, which has its own read, is shown; back on
    // 7 before its answer, the first read is the one that lands.
    const first = pending();
    const read = vi.spyOn(api, "readPostingText").mockReturnValueOnce(first.promise);
    const { result, rerender } = hook(blank(7));

    read.mockReturnValueOnce(new Promise(() => {}));
    rerender({ posting: blank(8) });
    expect(read).toHaveBeenLastCalledWith(8, false);
    rerender({ posting: blank(7) });
    expect(read).toHaveBeenCalledTimes(2); // 7 once, 8 once
    expect(result.current.read?.phase).toBe("reading");

    await act(async () => first.settle(answer("read")));
    expect(show).toHaveBeenCalledWith(7, answer("read"));
  });

  it("back on a posting whose read went slow while away, says it is slow", () => {
    const read = vi.spyOn(api, "readPostingText").mockReturnValue(new Promise(() => {}));
    const { result, rerender } = hook(blank(7));

    rerender({ posting: blank(8) });
    act(() => vi.advanceTimersByTime(SLOW_AFTER_MS));
    expect(result.current.read?.phase).toBe("slow"); // 8's own read, also slow by now
    rerender({ posting: blank(7) });

    expect(result.current.read?.phase).toBe("slow"); // 7's read passed six seconds too
    expect(read).toHaveBeenCalledTimes(2); // 7 once, 8 once
  });

  it("back from a posting with nothing to read, a read that went slow meanwhile says slow", () => {
    const read = vi.spyOn(api, "readPostingText").mockReturnValue(new Promise(() => {}));
    const { result, rerender } = hook(blank(7));

    rerender({ posting: blank(8, false) });
    act(() => vi.advanceTimersByTime(SLOW_AFTER_MS));
    expect(result.current.read).toBeNull();
    rerender({ posting: blank(7) });

    expect(result.current.read?.phase).toBe("slow");
    expect(read).toHaveBeenCalledTimes(1);
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
