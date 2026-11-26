import { render } from "@testing-library/react";
import { createRef } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { activate } from "../../copy/activate";
import { LedgerToolbar } from "./RegisterChrome";

const counts = vi.hoisted(() => ({
  trackedTotal: 0,
  catalogTotal: 0,
}));

vi.mock("./CompaniesData", () => ({
  useCompaniesQuery: () => ({ query: "", setQuery: () => {} }),
  useCompanies: () => ({
    searching: false,
    trackedOnly: false,
    setTrackedOnly: () => {},
    showPlanned: false,
    setShowPlanned: () => {},
    listAction: null,
    requestListAction: () => {},
    ...counts,
  }),
}));

const stats = () => document.querySelector(".ledger-stats")!.textContent!;

describe("LedgerToolbar counts", () => {
  afterEach(() => activate("en"));

  /* Only what this screen decides: how many are followed, of all. Open roles,
     live and ready answered other questions and are gone, so the line is
     pinned whole rather than by the figures it contains. */
  it("says only how many are followed, of every company, with the region's grouping", () => {
    Object.assign(counts, { trackedTotal: 4512, catalogTotal: 12034 });
    render(<LedgerToolbar toolbarRef={createRef()} />);
    expect(stats()).toBe("4,512 of 12,034 followed");
  });

  it("follows the region, so a Spanish reader in Spain sees dots", async () => {
    await activate("es", { region: "ES" });
    Object.assign(counts, {
      trackedTotal: 45120,
      catalogTotal: 120340,
    });
    render(<LedgerToolbar toolbarRef={createRef()} />);
    expect(stats()).toBe("45.120/120.340 seguidas");
  });
});
