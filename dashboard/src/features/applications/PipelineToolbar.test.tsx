import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { msg } from "../../test/msg";
import { PipelineToolbar } from "./PipelineToolbar";
import type { BoardFilter } from "./filters";

vi.mock("../../context/MissionState", () => ({
  useMissionActions: () => ({ screenSearchRef: { current: null } }),
}));

const NONE: BoardFilter = { query: "", quick: [], mode: "only" };

/** A view whose filter lives in an address that changes a moment after it is
 *  asked to, as the router's does: the toolbar is told the new query late. */
function SlowView({ lag, onQuery }: { lag: number; onQuery: (query: string) => void }) {
  const [filter, setFilter] = useState(NONE);
  return (
    <PipelineToolbar
      filter={filter}
      quickCounts={[]}
      onFilter={(next) => {
        window.setTimeout(() => {
          setFilter((was) => ({ ...was, ...next }));
          if (next.query != null) onQuery(next.query);
        }, lag);
      }}
    />
  );
}

const search = () => screen.getByRole("searchbox", { name: msg("applications-search-label") });

describe("the pipeline's search", () => {
  it("keeps every letter typed faster than the address changes", async () => {
    const queries: string[] = [];
    render(<SlowView lag={30} onQuery={(query) => queries.push(query)} />);
    // No pause between keys: each arrives before the address has taken the one before.
    await userEvent.type(search(), "accenture");
    expect(search()).toHaveValue("accenture");
    await vi.waitFor(() => expect(queries[queries.length - 1]).toBe("accenture"));
    expect(search(), "the late answers do not rewind the field").toHaveValue("accenture");
  });

  it("takes a query that changed elsewhere, as Reset all and the browser's Back do", async () => {
    function Outside() {
      const [filter, setFilter] = useState<BoardFilter>({ ...NONE, query: "stripe" });
      return (
        <>
          <button type="button" onClick={() => setFilter(NONE)}>elsewhere</button>
          <PipelineToolbar filter={filter} quickCounts={[]} onFilter={(next) => setFilter((was) => ({ ...was, ...next }))} />
        </>
      );
    }
    render(<Outside />);
    expect(search()).toHaveValue("stripe");
    await userEvent.click(screen.getByRole("button", { name: "elsewhere" }));
    expect(search()).toHaveValue("");
  });
});
