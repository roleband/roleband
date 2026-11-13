import { render } from "@testing-library/react";
import { createRef } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { activate } from "../../copy/activate";
import { LedgerToolbar } from "./RegisterChrome";

const counts = vi.hoisted(() => ({
  trackedTotal: 0,
  catalogTotal: 0,
  trackedOpenRoles: 0 as number | null,
  trackedLive: 0,
  trackedReady: 0,
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

  it("writes every figure with the region's grouping, not only open roles", () => {
    Object.assign(counts, {
      trackedTotal: 4512,
      catalogTotal: 12034,
      trackedOpenRoles: 98765,
      trackedLive: 4100,
      trackedReady: 1002,
    });
    render(<LedgerToolbar toolbarRef={createRef()} />);
    const text = stats();
    for (const figure of ["4,512", "12,034", "98,765", "4,100", "1,002"]) {
      expect(text).toContain(figure);
    }
    expect(text).not.toMatch(/\b(4512|12034|4100|1002)\b/);
  });

  it("follows the region, so a Spanish reader in Spain sees dots", async () => {
    await activate("es", { region: "ES" });
    Object.assign(counts, {
      trackedTotal: 45120,
      catalogTotal: 120340,
      trackedOpenRoles: null,
      trackedLive: 41000,
      trackedReady: 10020,
    });
    render(<LedgerToolbar toolbarRef={createRef()} />);
    const text = stats();
    for (const figure of ["45.120", "120.340", "41.000", "10.020"]) {
      expect(text).toContain(figure);
    }
  });
});
