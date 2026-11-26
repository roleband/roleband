import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { msg } from "../test/msg";
import { COPIED_MS, CopyField } from "./CopyField";

const SENTENCE = "Run `roleband connect --apply`, then set up my top picks.";
const writeText = vi.fn<(text: string) => Promise<void>>();

beforeEach(() => {
  writeText.mockReset().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  window.getSelection()?.removeAllRanges();
});

const field = () => screen.getByRole("button", { name: msg("shared-copy-text", { text: SENTENCE }) });

async function press() {
  fireEvent.click(field());
  // The copy settles on a microtask after the press.
  await act(async () => {});
}

describe("CopyField", () => {
  it("is one control named by the text it copies, showing the whole text", () => {
    render(<CopyField text={SENTENCE} />);
    expect(field()).toHaveTextContent(SENTENCE);
    expect(screen.queryByText(msg("shared-copied"))).toBeNull();
  });

  it("copies exactly its text on a press and says so for two seconds, then rests", async () => {
    render(<CopyField text={SENTENCE} />);
    await press();
    expect(writeText).toHaveBeenCalledExactlyOnceWith(SENTENCE);
    expect(field()).toHaveClass("is-copied");
    expect(screen.getByRole("status")).toHaveTextContent(msg("shared-copied"));

    act(() => vi.advanceTimersByTime(COPIED_MS - 1));
    expect(field()).toHaveClass("is-copied");
    act(() => vi.advanceTimersByTime(1));
    expect(field()).not.toHaveClass("is-copied");
    expect(screen.getByRole("status")).toHaveTextContent("");
  });

  it("starts the two seconds again on a second press within them", async () => {
    render(<CopyField text={SENTENCE} />);
    await press();
    act(() => vi.advanceTimersByTime(COPIED_MS - 500));
    await press();
    act(() => vi.advanceTimersByTime(COPIED_MS - 1));
    expect(field()).toHaveClass("is-copied");
    act(() => vi.advanceTimersByTime(1));
    expect(field()).not.toHaveClass("is-copied");
  });

  it("when the browser refuses the clipboard, selects the text and says to copy it, never that it was copied", async () => {
    writeText.mockRejectedValue(new DOMException("denied", "NotAllowedError"));
    render(<CopyField text={SENTENCE} />);
    await press();
    expect(screen.getByRole("alert")).toHaveTextContent(msg("shared-copy-failed"));
    expect(window.getSelection()?.toString()).toBe(SENTENCE);
    expect(field()).not.toHaveClass("is-copied");
    expect(screen.getByRole("status")).toHaveTextContent("");
  });

  it("treats a browser with no clipboard at all as a refusal", async () => {
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: undefined });
    render(<CopyField text={SENTENCE} />);
    await press();
    expect(screen.getByRole("alert")).toHaveTextContent(msg("shared-copy-failed"));
  });

  it("clears the refusal once a later press copies", async () => {
    writeText.mockRejectedValueOnce(new DOMException("denied", "NotAllowedError"));
    render(<CopyField text={SENTENCE} />);
    await press();
    await press();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(field()).toHaveClass("is-copied");
  });
});
