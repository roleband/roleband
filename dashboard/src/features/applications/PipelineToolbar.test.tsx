import { act, render, screen } from "@testing-library/react";
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

/** A view whose filter lives in an address that answers when the test says
 *  so, as the router's does a render later: each change waits in `answers`. */
const answers: (() => void)[] = [];
function HeldView() {
  const [filter, setFilter] = useState(NONE);
  return (
    <PipelineToolbar
      filter={filter}
      quickCounts={[]}
      onFilter={(next) => {
        answers.push(() => setFilter((was) => ({ ...was, ...next })));
      }}
    />
  );
}

const search = () => screen.getByRole("searchbox", { name: msg("applications-search-label") });

describe("the pipeline's search", () => {
  it("keeps every letter typed before the address has answered, and is not rewound when it does", async () => {
    answers.length = 0;
    render(<HeldView />);
    // Every key arrives while the address still holds the word before it.
    await userEvent.type(search(), "accenture");
    expect(answers).toHaveLength("accenture".length);
    expect(search()).toHaveValue("accenture");
    // The address catches up one word at a time: "a", "ac", ... Each is a
    // word the field already passed.
    for (const answer of answers.splice(0)) {
      act(answer);
      expect(search()).toHaveValue("accenture");
    }
  });

  it("is not rewound by the answers to a word typed, deleted and typed on from", async () => {
    answers.length = 0;
    render(<HeldView />);
    // "a", "ab", "a" again, "ac": the word "a" is on its way twice.
    await userEvent.type(search(), "ab{Backspace}c");
    expect(search()).toHaveValue("ac");
    expect(answers).toHaveLength(4);
    // The first answer, "a", is the first "a"'s: "ab" is still to come, and
    // when it does it is an older word, not one written elsewhere.
    for (const answer of answers.splice(0)) {
      act(answer);
      expect(search()).toHaveValue("ac");
    }
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
