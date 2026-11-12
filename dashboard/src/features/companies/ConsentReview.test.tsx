import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { CompanyDiscoveryCompany, CompanyDiscoveryState } from "../../api";
import { api } from "../../api";
import { ApiError } from "../../api/transport";
import { AppProviders } from "../../context/AppProviders";
import { msg } from "../../test/msg";
import { statsFixture, statusFixture } from "../../test/fixtures";
import { ToastProvider } from "../../ui/Toast";
import { CompaniesDataProvider, useCompanies } from "./CompaniesData";
import { FollowConfirmDialog } from "./CuratedList";
import { CompaniesSection } from "./CompaniesSection";
import { AttentionStrip } from "./RegisterChrome";

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

/* Followed companies that wait for an answer: their sites came to need the
 * person's agreement after they were followed. However many there are, the
 * strip asks one question, the answer is one write, and nothing is agreed to
 * for a company the person chose to unfollow. */

const company = (slug: string, display: string, over: Partial<CompanyDiscoveryCompany> = {}): CompanyDiscoveryCompany => ({
  slug,
  display,
  careers_url: `https://example.com/${slug}/careers`,
  sectors: ["technology"],
  aliases: [],
  connector_state: "live",
  parked_reason: null,
  selectable: true,
  tracked: true,
  enabled: true,
  visible: true,
  builtin: false,
  curated: true,
  directory: false,
  directed: true,
  scan_on_schedule: false,
  wall: null,
  consented: false,
  status: "active",
  ...over,
});

// Forty waiting, listed out of name order, so the question's order is its own.
const names = Array.from({ length: 40 }, (_, index) => `Company ${String(index).padStart(2, "0")}`);
const waiting = [...names].reverse().map((display) => company(display.toLowerCase().replace(" ", "-"), display));
const agreed = company("agreed", "Agreed Co", { consented: true });
const unfollowed = company("unfollowed", "Unfollowed Co", { tracked: false, enabled: false });
const state: CompanyDiscoveryState = {
  reads_waiting: [],
  sectors: [{ slug: "technology", company_count: 42, ready_count: 0, selected_count: 41 }],
  companies: [...waiting, agreed, unfollowed],
};
const slugOf = (display: string) => display.toLowerCase().replace(" ", "-");

/** The failure the register shows above its rows, from the same context. */
function Failures() {
  const { failures } = useCompanies();
  return <>{failures.map((failure) => <p key={failure.key} data-testid="failure">{failure.text}</p>)}</>;
}

function renderStrip() {
  render(
    <MemoryRouter initialEntries={["/settings/companies"]}>
      <AppProviders>
        <ToastProvider>
          <CompaniesDataProvider>
            <AttentionStrip />
            <Failures />
            <FollowConfirmDialog />
          </CompaniesDataProvider>
        </ToastProvider>
      </AppProviders>
    </MemoryRouter>,
  );
}

const TITLE = msg("companies-follow-copy-keep-following-these", { first: "Company 00", second: "Company 01", rest: 38 });
const CHOOSE = msg("companies-follow-copy-which-to-unfollow");

const openQuestion = async () => {
  await userEvent.click(await screen.findByRole("button", { name: msg("companies-register-chrome-review") }));
  return screen.findByRole("dialog", { name: TITLE });
};

const tick = (display: string) => userEvent.click(screen.getByRole("checkbox", { name: display }));

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.companyDiscovery).mockResolvedValue(state);
  vi.mocked(api.companyOpenCounts).mockResolvedValue({ counts: {}, not_counted: {}, unplaced: {}, unsorted: {}, last_read: {} });
  vi.mocked(api.searchCompanyDirectory).mockResolvedValue({ size: 0, match_count: 0, matches: [] });
  vi.mocked(api.companyDirectoryStatus).mockResolvedValue({
    size: 0, following: false, since: null, checked: 0, to_check: 0, with_roles: 0, waiting_for_power: false,
  });
  vi.mocked(api.syncTargets).mockResolvedValue({ companies: [], freshness_max_hours: 26 });
  vi.mocked(api.status).mockResolvedValue(statusFixture);
  vi.mocked(api.stats).mockResolvedValue(statsFixture);
  vi.mocked(api.setCompanySelection).mockImplementation(async (change) => ({
    ...state,
    companies: state.companies.map((row) =>
      change.unfollow.includes(row.slug) ? { ...row, enabled: false } : change.follow.includes(row.slug) ? { ...row, consented: true } : row),
  }));
});

describe("followed companies that wait for an answer", () => {
  it("the strip asks once for all forty, with one button and no company's name on it", async () => {
    renderStrip();
    const strip = await screen.findByRole("region", { name: msg("companies-register-chrome-companies-needing-attention") });
    expect(within(strip).getByText(msg("companies-register-chrome-followed-companies-wait-for-your", { count: 40 }))).toBeTruthy();
    expect(within(strip).getAllByRole("button")).toHaveLength(1);
    expect(within(strip).queryByText(/Company \d\d/)).toBeNull();
  });

  it("opens one question, in name order, with the safe answer focused", async () => {
    renderStrip();
    const dialog = await openQuestion();
    expect(within(dialog).getByRole("heading", { name: TITLE })).toBeTruthy();
    expect(document.activeElement).toBe(within(dialog).getByRole("button", { name: msg("companies-follow-copy-not-now") }));
    expect(within(dialog).getByRole("button", { name: msg("companies-follow-copy-keep-following-count", { count: 40 }) })).toBeTruthy();
  });

  it("keeps all forty in one write that records each agreement in the words shown", async () => {
    renderStrip();
    const dialog = await openQuestion();
    // Off: the agreement records the switch as each company's schedule choice.
    await userEvent.click(within(dialog).getByRole("checkbox", { name: msg("companies-follow-copy-keep-scanning", { count: 40 }) }));
    await userEvent.click(within(dialog).getByRole("button", { name: msg("companies-follow-copy-keep-following-count", { count: 40 }) }));

    await waitFor(() => expect(api.setCompanySelection).toHaveBeenCalledTimes(1));
    const [change, consents] = vi.mocked(api.setCompanySelection).mock.calls[0];
    expect(change).toEqual({ follow: waiting.map((row) => row.slug).sort(), unfollow: [] });
    expect(consents).toHaveLength(40);
    const text = consents![0].text;
    expect(text.startsWith(`${TITLE}\n\n`)).toBe(true);
    expect(text).toContain(msg("companies-follow-copy-some-are-scanned-at-your-direction"));
    expect(text).not.toContain(msg("companies-follow-copy-let-me-choose"));
    expect(consents!.every((consent) => consent.text === text && consent.scan_on_schedule === false)).toBe(true);

    const toast = await screen.findByText(msg("companies-data-review-kept", { count: 40 }));
    // No way back: an agreement is not taken back.
    expect(within(toast.closest(".ui-toast") as HTMLElement).queryByRole("button", { name: msg("companies-data-undo") })).toBeNull();
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("Let me choose shows only the list; the ticked ones are unfollowed in the same write, with no agreement", async () => {
    renderStrip();
    const dialog = await openQuestion();
    await userEvent.click(within(dialog).getByRole("button", { name: msg("companies-follow-copy-let-me-choose") }));

    const step = await screen.findByRole("dialog", { name: CHOOSE });
    // The step is the task alone: the agreement was read on the step before.
    expect(within(step).queryByText(msg("companies-follow-copy-by-following-them"))).toBeNull();
    expect(within(step).queryByRole("checkbox", { name: msg("companies-follow-copy-keep-scanning", { count: 40 }) })).toBeNull();
    expect(document.activeElement).toBe(within(step).getByRole("button", { name: msg("companies-setup-back") }));
    const list = within(step).getByRole("group", { name: msg("companies-follow-copy-companies-to-unfollow") });
    expect(within(list).getAllByRole("checkbox").map((box) => box.closest("label")?.textContent)).toEqual(names);

    for (const display of ["Company 03", "Company 17", "Company 39"]) await tick(display);
    expect(within(step).getByText(msg("companies-follow-copy-count-to-unfollow", { count: 3 }))).toBeTruthy();
    await userEvent.click(within(step).getByRole("button", { name: msg("companies-follow-copy-keep-following-count", { count: 37 }) }));

    await waitFor(() => expect(api.setCompanySelection).toHaveBeenCalledTimes(1));
    const [change, consents] = vi.mocked(api.setCompanySelection).mock.calls[0];
    const dropped = ["Company 03", "Company 17", "Company 39"].map(slugOf);
    expect(change.unfollow).toEqual([...dropped].sort());
    expect(change.follow).toHaveLength(37);
    expect(change.follow).not.toEqual(expect.arrayContaining([dropped[0]]));
    expect(consents!.map((consent) => consent.slug).sort()).toEqual(change.follow);
    // Recorded in the words of the question, not the list.
    expect(consents![0].text.startsWith(`${TITLE}\n\n`)).toBe(true);
    expect(await screen.findByText(
      `${msg("companies-data-review-kept", { count: 37 })} ${msg("companies-data-review-dropped", { count: 3 })}`,
    )).toBeTruthy();
  });

  it("Back keeps the ticks, and the question's own answer still keeps every company", async () => {
    renderStrip();
    const dialog = await openQuestion();
    await userEvent.click(within(dialog).getByRole("button", { name: msg("companies-follow-copy-let-me-choose") }));
    await tick("Company 05");
    await userEvent.click(screen.getByRole("button", { name: msg("companies-setup-back") }));

    const back = await screen.findByRole("dialog", { name: TITLE });
    expect(document.activeElement).toBe(within(back).getByRole("button", { name: msg("companies-follow-copy-not-now") }));
    await userEvent.click(within(back).getByRole("button", { name: msg("companies-follow-copy-let-me-choose") }));
    expect((screen.getByRole("checkbox", { name: "Company 05" }) as HTMLInputElement).checked).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: msg("companies-setup-back") }));

    await userEvent.click(within(await screen.findByRole("dialog", { name: TITLE }))
      .getByRole("button", { name: msg("companies-follow-copy-keep-following-count", { count: 40 }) }));
    await waitFor(() => expect(api.setCompanySelection).toHaveBeenCalledTimes(1));
    expect(vi.mocked(api.setCompanySelection).mock.calls[0][0].unfollow).toEqual([]);
  });

  it("every one ticked unfollows all forty and agrees to nothing", async () => {
    renderStrip();
    const dialog = await openQuestion();
    await userEvent.click(within(dialog).getByRole("button", { name: msg("companies-follow-copy-let-me-choose") }));
    await userEvent.click(screen.getByRole("button", { name: msg("companies-follow-copy-select-all", { state: "some" }) }));
    expect(screen.getByRole("button", { name: msg("companies-follow-copy-select-all", { state: "all" }) })).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: msg("companies-follow-copy-unfollow", { count: 40 }) }));

    await waitFor(() => expect(api.setCompanySelection).toHaveBeenCalledTimes(1));
    const [change, consents] = vi.mocked(api.setCompanySelection).mock.calls[0];
    expect(change).toEqual({ follow: [], unfollow: waiting.map((row) => row.slug).sort() });
    expect(consents).toEqual([]);
    expect(await screen.findByText(msg("companies-data-review-dropped", { count: 40 }))).toBeTruthy();
  });

  it("Select all after a search ticks only the companies found", async () => {
    renderStrip();
    const dialog = await openQuestion();
    await userEvent.click(within(dialog).getByRole("button", { name: msg("companies-follow-copy-let-me-choose") }));
    await userEvent.type(screen.getByRole("searchbox", { name: msg("companies-follow-copy-find-a-company") }), "company 1");
    const list = screen.getByRole("group", { name: msg("companies-follow-copy-companies-to-unfollow") });
    expect(within(list).getAllByRole("checkbox")).toHaveLength(10);
    await userEvent.click(screen.getByRole("button", { name: msg("companies-follow-copy-select-all", { state: "some" }) }));
    expect(screen.getByText(msg("companies-follow-copy-count-to-unfollow", { count: 10 }))).toBeTruthy();
    expect(screen.getByRole("button", { name: msg("companies-follow-copy-keep-following-count", { count: 30 }) })).toBeTruthy();
  });

  it("Not now and Escape change nothing", async () => {
    renderStrip();
    const dialog = await openQuestion();
    await userEvent.click(within(dialog).getByRole("button", { name: msg("companies-follow-copy-not-now") }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await openQuestion();
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(api.setCompanySelection).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: msg("companies-register-chrome-review") })).toBeTruthy();
  });

  it("a failed save says so and leaves every company waiting", async () => {
    vi.mocked(api.setCompanySelection).mockRejectedValue(new ApiError("boom", 500));
    renderStrip();
    const dialog = await openQuestion();
    await userEvent.click(within(dialog).getByRole("button", { name: msg("companies-follow-copy-keep-following-count", { count: 40 }) }));
    const failure = await screen.findByTestId("failure");
    expect(failure.textContent).toContain(msg("companies-data-review-failed"));
    expect(screen.getByText(msg("companies-register-chrome-followed-companies-wait-for-your", { count: 40 }))).toBeTruthy();
  });
});

describe("a waiting company's row", () => {
  it("its state asks that company alone, and the answer agrees for it alone", async () => {
    render(
      <MemoryRouter initialEntries={["/settings/companies"]}>
        <AppProviders>
          <ToastProvider>
            <CompaniesDataProvider>
              <CompaniesSection />
            </CompaniesDataProvider>
          </ToastProvider>
        </AppProviders>
      </MemoryRouter>,
    );
    const row = (await screen.findByRole("checkbox", { name: "Company 07" })).closest(".ledger-row") as HTMLElement;
    // A company already agreed to has no question to ask.
    const agreedRow = screen.getByRole("checkbox", { name: "Agreed Co" }).closest(".ledger-row") as HTMLElement;
    expect(within(agreedRow).queryByRole("button", { name: msg("companies-company-register-rows-needs-consent") })).toBeNull();

    await userEvent.click(within(row).getByRole("button", { name: msg("companies-company-register-rows-needs-consent") }));
    const title = msg("companies-follow-copy-keep-following-one", { display: "Company 07" });
    const dialog = await screen.findByRole("dialog", { name: title });
    expect(within(dialog).queryByRole("button", { name: msg("companies-follow-copy-let-me-choose") })).toBeNull();
    await userEvent.click(within(dialog).getByRole("button", { name: msg("companies-follow-copy-keep-following") }));

    await waitFor(() => expect(api.setCompanySelection).toHaveBeenCalledTimes(1));
    const [change, consents] = vi.mocked(api.setCompanySelection).mock.calls[0];
    expect(change).toEqual({ follow: ["company-07"], unfollow: [] });
    expect(consents!.map((consent) => [consent.slug, consent.text.split("\n\n")[0]])).toEqual([["company-07", title]]);
    expect(await screen.findByText(msg("companies-data-followed", { coverage: "covered", company: "Company 07" }))).toBeTruthy();
  });
});
