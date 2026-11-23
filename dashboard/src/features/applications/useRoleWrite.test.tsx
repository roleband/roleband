import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useJobActions } from "../../context/JobWorkspace";
import { useMissionActions } from "../../context/MissionState";
import { useRoleWrite } from "./useRoleWrite";

/* A pursuit write that does not land hands the role back to `failed`, so a
 * screen that painted ahead reads it again, whether it failed as the newest
 * write or behind a newer one. The ordering underneath is the real save
 * command; only its announcements are stubbed. */

vi.mock("../../context/JobWorkspace", () => ({ useJobActions: vi.fn() }));
vi.mock("../../context/MissionState", () => ({ useMissionActions: vi.fn() }));

beforeEach(() => {
  vi.mocked(useMissionActions).mockReturnValue({ refreshStats: vi.fn() } as never);
  vi.mocked(useJobActions).mockReturnValue({ savedChanged: vi.fn() } as never);
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

const ROLE = { job_id: 41, starred: true };

describe("useRoleWrite", () => {
  it("hands back a write that failed behind a newer one, and the newer one's success stays its own", async () => {
    const failed = vi.fn();
    const { result } = renderHook(() => useRoleWrite({ failed }));
    const stage = deferred<unknown>();
    const landed = (write: Promise<void>) => write.then(() => true, () => false);
    let first!: Promise<boolean>;
    let second!: Promise<boolean>;
    act(() => {
      first = landed(result.current.writeRole(ROLE, () => stage.promise));
      second = landed(result.current.writeRole(ROLE, () => Promise.resolve({})));
    });

    await act(async () => stage.reject(new Error("offline")));

    expect([await first, await second]).toEqual([false, true]);
    expect(failed).toHaveBeenCalledExactlyOnceWith(41);
  });

  it("hands back the newest write when it fails, and nothing when every write lands", async () => {
    const failed = vi.fn();
    const { result } = renderHook(() => useRoleWrite({ failed }));

    await act(async () => {
      await result.current.writeRole(ROLE, () => Promise.resolve({}));
    });
    expect(failed).not.toHaveBeenCalled();

    await act(async () => {
      await expect(result.current.writeRole(ROLE, () => Promise.reject(new Error("offline")))).rejects.toThrow();
    });
    expect(failed).toHaveBeenCalledExactlyOnceWith(41);
  });
});
