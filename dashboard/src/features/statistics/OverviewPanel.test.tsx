import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, it, vi } from "vitest";
import { api } from "../../api";
import { date } from "../../copy/format";
import { overviewFixture } from "../../test/fixtures";
import { msg } from "../../test/msg";
import { OverviewPanel } from "./OverviewPanel";

vi.mock("../../api", async () => {
  const actual = await vi.importActual<typeof import("../../api")>("../../api");
  return { ...actual, api: { ...actual.api, statisticsOverview: vi.fn() } };
});

vi.mock("./charts/StatisticsCharts", () => ({ OverviewSignalChart: () => null }));

it("leads with the window's motion and never draws the top skills twice", async () => {
  vi.mocked(api.statisticsOverview).mockResolvedValue({
    ...overviewFixture,
    kpis: { ...overviewFixture.kpis, new_count: 494, closed_count: 217, already_listed_count: 1867, open_total: 3192 },
    top_skills: [{ term: "roadmap", category: "process", job_count: 1435 }],
  });
  render(
    <MemoryRouter>
      <OverviewPanel days={30} />
    </MemoryRouter>,
  );
  expect(await screen.findByRole("heading", { level: 2, name: "494 opened · 217 closed" })).toBeInTheDocument();
  expect(screen.getByText("Overview", { selector: ".eyebrow" })).toBeInTheDocument();
  // The roles already listed at a company's first scan say when the radar
  // first looked, not what the market did: no tile and no sentence.
  expect(screen.queryByText("1,867")).toBeNull();
  expect(screen.queryByText(/first scanned/)).toBeNull();
  // The chart is the one place the top skills are drawn; the brief names the
  // first of them in a sentence.
  expect(screen.queryByRole("heading", { name: "Most in-demand skills" })).toBeNull();
  const drawn = screen.getAllByText(/Roadmapping/).filter((el) => !el.closest(".insight-hero"));
  expect(drawn).toHaveLength(1);
  expect(screen.getByText(/Top skill: Roadmapping \(1,435 roles\)\./)).toBeInTheDocument();
});

it("calls the window's openings Opened, never New, and says all time is the history since its start", async () => {
  // New is the Board's 2-day rule; Overview counts the roles that appeared
  // in the window. With no window, the figures cover the history there is.
  vi.mocked(api.statisticsOverview).mockResolvedValue({ ...overviewFixture, days: 0, since: "2026-11-03T06:02:00Z" });
  render(
    <MemoryRouter>
      <OverviewPanel days={0} />
    </MemoryRouter>,
  );
  expect(await screen.findByText(msg("insights-common-opened"))).toBeInTheDocument();
  expect(screen.queryByText(msg("insights-common-new"))).toBeNull();
  const since = "2026-11-03T06:02:00Z";
  const days = Math.floor((Date.now() - Date.parse(since)) / 86_400_000);
  expect(screen.getAllByText(msg("insights-common-since-date", { date: date(since, "day"), days }))).toHaveLength(2);
  expect(screen.queryByText(msg("insights-common-last-days-or-all-time", { period: "all", days: 0 }))).toBeNull();
});

it("lists no roles and groups none: the window's motion and the top skills", async () => {
  vi.mocked(api.statisticsOverview).mockResolvedValue({
    ...overviewFixture,
    top_skills: [{ term: "python", category: "language", job_count: 12 }],
  });
  render(
    <MemoryRouter>
      <OverviewPanel days={30} />
    </MemoryRouter>,
  );
  expect(await screen.findByRole("heading", { level: 2 })).toBeInTheDocument();
  // A role's age answers nothing here (docs/decisions/0004-insights-answers-a-question.md):
  // no role link, and no card or sentence that groups roles by skill profile.
  expect(screen.queryByRole("link")).toBeNull();
  expect(screen.queryByText(/longest|cluster|group/i)).toBeNull();
});
