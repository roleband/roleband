import { act, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { PicksState } from "../api";
import { picksStateFixture } from "../test/fixtures";
import { msg } from "../test/msg";
import { NavRail } from "./NavRail";
import { forgetPicksDot, picksOpened } from "../hooks/picksDot";

vi.mock("../context/MissionState", () => ({
  useMissionStats: () => ({ notif_unread: 0, review_pending: 0 }),
}));

const picksState = vi.fn<() => Promise<PicksState>>();
const picksOpenedCall = vi.fn<() => Promise<PicksState>>();
vi.mock("../api", () => ({
  api: {
    picksState: () => picksState(),
    picksOpened: () => picksOpenedCall(),
  },
}));

const unseen = (unseen_pick: boolean) => picksStateFixture({ state: "on", unseen_pick });

/** A promise the test settles when it chooses. */
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const rail = () =>
  render(
    <MemoryRouter>
      <NavRail expanded={false} onToggleExpanded={vi.fn()} theme="dark" onToggleTheme={vi.fn()} />
    </MemoryRouter>,
  );

const label = () => msg("shell-nav-top-picks");
const litName = () => msg("shell-rail-item-count", { label: label(), badge: msg("shell-rail-picks-unseen") });
const nav = () => within(screen.getByRole("navigation", { name: msg("shell-rail-aria") }));

beforeEach(() => {
  forgetPicksDot();
  picksState.mockReset();
  picksOpenedCall.mockReset();
});

describe("the Top picks rail item", () => {
  it("stands directly after the Radar", () => {
    picksState.mockResolvedValue(unseen(false));
    rail();
    const names = nav().getAllByRole("link").map((link) => link.getAttribute("aria-label"));
    expect(names.slice(0, 2)).toEqual([msg("shell-nav-radar"), label()]);
    expect(nav().getByRole("link", { name: label() })).toHaveAttribute("href", "/top-picks");
  });

  it("wears a dot, never a number, while a pick is unseen, and says so in its name", async () => {
    picksState.mockResolvedValue(unseen(true));
    rail();
    const item = await nav().findByRole("link", { name: litName() });
    expect(item).toHaveAttribute("data-tip", litName());
    const badge = item.querySelector(".rail-badge")!;
    expect(badge).toHaveClass("rail-badge-dot");
    expect(badge).toHaveTextContent(/^$/);
  });

  it("stays plain while nothing is unseen", async () => {
    picksState.mockResolvedValue(unseen(false));
    rail();
    await waitFor(() => expect(picksState).toHaveBeenCalled());
    const item = nav().getByRole("link", { name: label() });
    expect(item.querySelector(".rail-badge")).toBeNull();
  });

  it("goes out the moment Top picks opens, and stays out on the engine's answer", async () => {
    picksState.mockResolvedValue(unseen(true));
    rail();
    await nav().findByRole("link", { name: litName() });
    const answer = deferred<PicksState>();
    picksOpenedCall.mockReturnValue(answer.promise);
    act(() => picksOpened());
    expect(nav().getByRole("link", { name: label() }).querySelector(".rail-badge")).toBeNull();
    await act(async () => answer.resolve(unseen(false)));
    expect(nav().getByRole("link", { name: label() }).querySelector(".rail-badge")).toBeNull();
    expect(picksOpenedCall).toHaveBeenCalledOnce();
  });

  it("is not lit again by a read that left before the screen opened", async () => {
    const early = deferred<PicksState>();
    picksState.mockReturnValue(early.promise);
    rail();
    await waitFor(() => expect(picksState).toHaveBeenCalled());
    picksOpenedCall.mockResolvedValue(unseen(false));
    await act(async () => picksOpened());
    await act(async () => early.resolve(unseen(true)));
    expect(nav().getByRole("link", { name: label() }).querySelector(".rail-badge")).toBeNull();
  });

  it("lights again on the next read when the opening was not recorded", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      picksState.mockResolvedValue(unseen(true));
      rail();
      await nav().findByRole("link", { name: litName() });
      picksOpenedCall.mockRejectedValue(new Error("engine away"));
      await act(async () => picksOpened());
      expect(nav().getByRole("link", { name: label() }).querySelector(".rail-badge")).toBeNull();
      await act(async () => {
        await vi.advanceTimersByTimeAsync(60_000);
      });
      expect(await nav().findByRole("link", { name: litName() })).toBeTruthy();
    } finally {
      vi.useRealTimers();
    }
  });
});
