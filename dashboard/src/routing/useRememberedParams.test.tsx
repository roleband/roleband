import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation, useSearchParams } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";
import { api } from "../api";
import { readEntry, writeEntry } from "../hooks/filterMemory";
import { forgetViewChoices } from "../hooks/viewChoices";
import { useRememberedParams } from "./useRememberedParams";

/* A screen whose lenses ARE the address. They already survive a reload; what
 * they never survived is leaving and coming back, because the nav rail lands
 * on a bare URL. */

const KEYS = ["status", "category"] as const;

function Harness() {
  useRememberedParams("spec", KEYS);
  const [params, setParams] = useSearchParams();
  const loc = useLocation();
  return (
    <>
      <div data-testid="search">{loc.search}</div>
      <div data-testid="status">{params.get("status") ?? ""}</div>
      <button
        onClick={() =>
          setParams(
            (prev) => {
              const next = new URLSearchParams(prev);
              next.set("status", "unread");
              next.append("category", "sync_failed");
              return next;
            },
            { replace: true },
          )
        }
      >
        narrow
      </button>
      <button
        onClick={() =>
          setParams(
            (prev) => {
              const next = new URLSearchParams(prev);
              for (const key of KEYS) next.delete(key);
              return next;
            },
            { replace: true },
          )
        }
      >
        reset
      </button>
    </>
  );
}

const arriveAt = (route: string) =>
  render(
    <MemoryRouter initialEntries={[route]}>
      <Harness />
    </MemoryRouter>,
  );

beforeEach(() => localStorage.clear());

describe("remembered query params", () => {
  it("records the lenses a reader chose, and puts them back on a bare address", async () => {
    const user = userEvent.setup();
    const first = arriveAt("/notifications");
    await user.click(screen.getByText("narrow"));
    await waitFor(() =>
      expect(readEntry("spec:params")).toEqual({ status: ["unread"], category: ["sync_failed"] }),
    );
    first.unmount();

    // The nav rail's own link: no query at all.
    arriveAt("/notifications");
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("unread"));
    expect(screen.getByTestId("search").textContent).toContain("category=sync_failed");
  });

  it("leaves an address that names a lens alone, memory or no memory", async () => {
    writeEntry("spec:params", { status: ["unread"], category: ["sync_failed"] });
    arriveAt("/notifications?status=all");
    // A link, a deep link, Back: an explicit choice made just now outranks one
    // made last night, and nothing is merged in beside it.
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("all"));
    expect(screen.getByTestId("search").textContent).not.toContain("category");
  });

  it("carries params it does not own through a restore untouched", async () => {
    writeEntry("spec:params", { status: ["unread"] });
    arriveAt("/notifications?tab=digest");
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("unread"));
    expect(screen.getByTestId("search").textContent).toContain("tab=digest");
  });

  it("remembers a reset as a choice, so it survives the trip too", async () => {
    const user = userEvent.setup();
    const first = arriveAt("/notifications");
    await user.click(screen.getByText("narrow"));
    await waitFor(() => expect(readEntry("spec:params")).not.toEqual({}));
    // Reset all is the reader saying "show me everything". Coming back to a
    // list still narrowed by what they just cleared would be the worst of both.
    await user.click(screen.getByText("reset"));
    await waitFor(() => expect(readEntry("spec:params")).toEqual({}));
    first.unmount();

    arriveAt("/notifications");
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent(""));
  });

  it("does not erase memory with the bare address it is in the middle of replacing", async () => {
    // The restore and the write both run in the mount commit, and the restore's
    // navigation has not landed yet — so the naive write half reads the bare
    // URL and stores `{}`, wiping exactly what it was restoring.
    writeEntry("spec:params", { status: ["unread"] });
    arriveAt("/notifications");
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("unread"));
    expect(readEntry("spec:params")).toEqual({ status: ["unread"] });
  });
});

/* The saved choices are read from the database once per page, and the first
 * render waits for that read only so long. A screen that opens before the
 * answer, or after a failed read, has not seen what the person remembered:
 * its bare address is not a choice, and must not be saved over the memory. */
describe("remembered query params before the saved choices answer", () => {
  const NAME = "filters.spec:params";
  let saves: MockInstance<typeof api.saveViewChoice>;

  beforeEach(() => {
    forgetViewChoices();
    saves = vi.spyOn(api, "saveViewChoice").mockImplementation(async (name: string, value: unknown) => ({
      name,
      value: value as never,
    }));
  });
  afterEach(() => vi.restoreAllMocks());

  /** A read that answers when the test says so. */
  const lateRead = () => {
    let answer!: (read: { choices: Record<string, unknown> }) => void;
    const read = new Promise<{ choices: Record<string, unknown> }>((resolve) => (answer = resolve));
    vi.spyOn(api, "viewChoices").mockImplementation(() => read as never);
    return (choices: Record<string, unknown>) => answer({ choices });
  };
  const savedFor = (name: string) => saves.mock.calls.filter(([saved]) => saved === name);

  it("puts the lenses back once a late read answers, and saves nothing over them", async () => {
    const answer = lateRead();
    arriveAt("/notifications");
    // The screen is up on its bare address while the read is still out.
    expect(screen.getByTestId("status")).toHaveTextContent("");
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(savedFor(NAME)).toEqual([]);

    answer({ [NAME]: { status: ["unread"] } });
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("unread"));
    expect(readEntry("spec:params")).toEqual({ status: ["unread"] });
    expect(savedFor(NAME).filter(([, value]) => JSON.stringify(value) === "{}")).toEqual([]);
  });

  it("leaves a lens the reader chose while the read was out in place when it answers", async () => {
    const user = userEvent.setup();
    const answer = lateRead();
    arriveAt("/notifications");
    await user.click(screen.getByText("narrow"));
    answer({ [NAME]: { status: ["read"] } });
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(screen.getByTestId("status")).toHaveTextContent("unread");
    expect(readEntry("spec:params")).toEqual({ status: ["unread"], category: ["sync_failed"] });
  });

  it("saves nothing over the memory when the read fails", async () => {
    vi.spyOn(api, "viewChoices").mockRejectedValue(new Error("engine starting"));
    arriveAt("/notifications");
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(screen.getByTestId("status")).toHaveTextContent("");
    expect(savedFor(NAME)).toEqual([]);
  });
});

