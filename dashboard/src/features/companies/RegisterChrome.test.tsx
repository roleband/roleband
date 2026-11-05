import { render, screen, waitFor } from "@testing-library/react";
import { useRef } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { CompanyDiscoveryCompany, CompanyDiscoveryState } from "../../api";
import { api } from "../../api";
import { activate } from "../../copy/activate";
import { AppProviders } from "../../context/AppProviders";
import { msg } from "../../test/msg";
import { statsFixture, statusFixture } from "../../test/fixtures";
import { ToastProvider } from "../../ui/Toast";
import { CompaniesDataProvider } from "./CompaniesData";
import { LedgerToolbar } from "./RegisterChrome";

vi.mock("../../api", () => ({
  api: {
    companyDiscovery: vi.fn(),
    companyOpenCounts: vi.fn(),
    searchCompanyDirectory: vi.fn(),
    companyDirectoryStatus: vi.fn(),
    followCompanyDirectory: vi.fn(),
    setCompanySelection: vi.fn(),
    addCompany: vi.fn(),
    updateCompany: vi.fn(),
    syncTargets: vi.fn(),
    sync: vi.fn(),
    cancelSync: vi.fn(),
    status: vi.fn(),
    stats: vi.fn(),
    compareSelection: vi.fn().mockResolvedValue({ job_ids: [] }),
    setCompareSelection: vi.fn((_scope: string, jobIds: number[]) => Promise.resolve({ job_ids: jobIds })),
  },
}));

/* A radar past a thousand companies: every figure the toolbar prints is above
 * 999 and distinct from the others, so an ungrouped one shows as four bare
 * digits and cannot hide behind a figure that happens to be grouped. */
const company = (slug: string, over: Partial<CompanyDiscoveryCompany>): CompanyDiscoveryCompany => ({
  slug,
  display: slug,
  careers_url: `https://example.com/${slug}/careers`,
  sectors: ["technology"],
  aliases: [],
  connector_state: "planned",
  parked_reason: null,
  selectable: true,
  tracked: false,
  enabled: false,
  visible: true,
  builtin: false,
  curated: false,
  directory: true,
  wall: null,
  consented: false,
  status: null,
  ...over,
});
const many = (count: number, prefix: string, over: Partial<CompanyDiscoveryCompany>) =>
  Array.from({ length: count }, (_, i) => company(`${prefix}-${i}`, over));

const followedLive = many(1234, "live", { connector_state: "live", tracked: true, enabled: true, status: "active" });
const followedReady = many(1050, "ready", { connector_state: "ready", tracked: true, enabled: true });
const notFollowed = many(770, "planned", {});
const state: CompanyDiscoveryState = {
  sectors: [{ slug: "technology", company_count: 3054, ready_count: 1050, selected_count: 2284 }],
  companies: [...followedLive, ...followedReady, ...notFollowed],
};
// 25 open roles at every live company: 30,850 across the radar. The ones you
// do not follow carry roles too, which the toolbar must leave out.
const openCounts = {
  counts: Object.fromEntries([...followedLive, ...notFollowed].map((entry) => [entry.slug, 25])),
  not_counted: {},
  unplaced: {},
  unsorted: {},
  last_read: {},
};

function Toolbar() {
  const toolbarRef = useRef<HTMLDivElement>(null);
  return <LedgerToolbar toolbarRef={toolbarRef} />;
}

function renderToolbar() {
  render(
    <MemoryRouter initialEntries={["/settings/companies"]}>
      <AppProviders>
        <ToastProvider>
          <CompaniesDataProvider>
            <Toolbar />
          </CompaniesDataProvider>
        </ToastProvider>
      </AppProviders>
    </MemoryRouter>,
  );
}

/** The toolbar the search box sits in, as a person reads it. */
const toolbar = async () =>
  (await screen.findByRole("searchbox", { name: msg("companies-register-chrome-search-companies") })).closest(
    ".ledger-toolbar",
  ) as HTMLElement;

const stats = (figures: { followed: string; total: string; openRoles: string; live: string; ready: string }) =>
  msg("companies-register-chrome-toolbar-stats", { ...figures, sep: "·" });

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.companyDiscovery).mockResolvedValue(state);
  vi.mocked(api.companyOpenCounts).mockResolvedValue(openCounts);
  vi.mocked(api.searchCompanyDirectory).mockResolvedValue({ size: 0, match_count: 0, matches: [] });
  vi.mocked(api.companyDirectoryStatus).mockResolvedValue({
    size: 0, following: false, since: null, checked: 0, to_check: 0, with_roles: 0, waiting_for_power: false,
  });
  vi.mocked(api.syncTargets).mockResolvedValue({ companies: [], freshness_max_hours: 26 });
  vi.mocked(api.status).mockResolvedValue(statusFixture);
  vi.mocked(api.stats).mockResolvedValue(statsFixture);
});

afterAll(async () => {
  await activate("en");
});

describe("Followed companies toolbar: every count follows the person's region", () => {
  it("groups every figure in a US English region", async () => {
    await activate("en", { region: "en-US" });
    renderToolbar();

    const bar = await toolbar();
    await waitFor(() =>
      expect(bar).toHaveTextContent(
        stats({ followed: "2,284", total: "3,054", openRoles: "30,850", live: "1,234", ready: "1,050" }),
      ),
    );
    // No figure is left as four bare digits ("2284 of 3,054 followed").
    expect(bar.textContent).not.toMatch(/\d{4}/);
  });

  it("groups by the region, not by English: a German region writes 2.284", async () => {
    await activate("en", { region: "de-DE" });
    renderToolbar();

    const bar = await toolbar();
    await waitFor(() =>
      expect(bar).toHaveTextContent(
        stats({ followed: "2.284", total: "3.054", openRoles: "30.850", live: "1.234", ready: "1.050" }),
      ),
    );
    expect(bar.textContent).not.toMatch(/\d{4}/);
    expect(bar.textContent).not.toMatch(/\d,\d{3}/);
  });
});
