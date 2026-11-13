import { render } from "@testing-library/react";
import { format } from "echarts/core";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setCompanyNames } from "../../../format";
import { msg } from "../../../test/msg";
import { buildDisclosureRateOption, disclosureRateRows } from "./disclosure";
import {
  HiringCompaniesChart,
  OverviewSignalChart,
  SkillsConstellationChart,
} from "./StatisticsCharts";
import { encodeHTML, tooltipHtml, withParts } from "./tooltip";

/* ECharts writes a tooltip formatter's string into the tooltip's innerHTML.
 * Company names and skill names are text RoleBand did not write, so each
 * one must reach the page as text. The chart wrapper is the boundary to the
 * charting runtime: it is replaced by a probe that keeps the option each chart
 * hands it, and every formatter is read from there. */

const options = vi.hoisted(() => new Map<string, Record<string, any>>());
vi.mock("../../../ui/EChart", () => ({
  EChart: ({ className, option }: { className: string; option: Record<string, any> }) => {
    options.set(className, option);
    return null;
  },
}));

const EVIL = "<img src=x onerror=alert(1)>";

/** The tooltip as the browser would build it from the formatter's string. */
function tooltip(html: unknown): HTMLElement {
  const box = document.createElement("div");
  box.innerHTML = String(html);
  return box;
}

/** The hostile value is on screen as its own characters, and the only
 *  elements are the ones the tooltip lays itself out with. */
function expectInert(html: unknown): HTMLElement {
  const box = tooltip(html);
  expect(box.querySelector("img")).toBeNull();
  expect(box.querySelector("[onerror]")).toBeNull();
  expect([...box.querySelectorAll("*")].map((el) => el.tagName.toLowerCase()).filter((tag) => !["strong", "br", "span"].includes(tag))).toEqual([]);
  expect(box.textContent).toContain(EVIL);
  return box;
}

const formatter = (className: string) => {
  const option = options.get(className);
  if (!option) throw new Error(`no chart rendered as ${className}`);
  return option.tooltip.formatter as (params: unknown) => string;
};

beforeEach(() => {
  options.clear();
  setCompanyNames({ evil: EVIL, google: "Google" });
});
afterEach(() => setCompanyNames({}));

describe("chart tooltips", () => {
  it("show a hostile skill name as text on the Overview signal chart", () => {
    render(<OverviewSignalChart skills={[{ term: EVIL, category: EVIL, job_count: 12 }]} />);
    const box = expectInert(formatter("chart-overview")({ dataIndex: 0 }));
    expect(box.querySelector("strong")?.textContent).toBe(EVIL);
  });

  it("show a hostile company name as text on the Hiring company chart, with today's motion tinted", () => {
    render(<HiringCompaniesChart bars={[{ company: "evil", label: EVIL, open: 20, fresh: 3, closed: 2 }]} />);
    const box = expectInert(formatter("chart-demand")({ dataIndex: 0 }));
    expect(box.querySelector("strong")?.textContent).toBe(EVIL);
    expect(box.querySelector(".chart-tip-new")?.textContent).toBe(msg("insights-statistics-charts-new-count", { fresh: 3 }));
    expect(box.querySelector(".chart-tip-closed")?.textContent).toBe(msg("insights-statistics-charts-closed-count", { closed: 2 }));
    expect(box.querySelector("[style]")).toBeNull();
  });

  it("show a hostile skill name as text on the Skills constellation", () => {
    render(<SkillsConstellationChart skills={[{
      term: EVIL, category: "language", job_count: 12, share: 0.4, market_share: 0.1, lift: 4, distinctiveness: 5.2,
    }]} />);
    const box = expectInert(formatter("chart-skills")({ dataIndex: 0 }));
    expect(box.querySelector("strong")?.textContent).toBe(EVIL);
  });

  it("show a hostile level name as text on the pay transparency chart", () => {
    const rows = disclosureRateRows({
      overall: { open: 50, checked: 50, disclosed: 40, rate: 0.8 },
      by_level: [{ level_band: EVIL, open: 50, checked: 50, disclosed: 40, rate: 0.8 }],
    });
    const option = buildDisclosureRateOption(rows) as Record<string, any>;
    const box = expectInert(option.tooltip.formatter({ dataIndex: 0 }));
    expect(box.querySelector("strong")?.textContent).toBe(EVIL);
  });
});

describe("tooltipHtml", () => {
  const hostile = [EVIL, "AT&T", `"quoted" 'and' <b>bold</b>`, "<style>body{display:none}</style>", "plain"];

  it("escapes exactly as echarts' own format.encodeHTML does", () => {
    for (const text of hostile) expect(encodeHTML(text)).toBe(format.encodeHTML(text));
  });

  it("shows a value once, as written: escaped, never escaped twice", () => {
    const box = tooltip(tooltipHtml("AT&T", ["R&D · 3 open roles"]));
    expect(box.querySelector("strong")?.textContent).toBe("AT&T");
    expect(box.textContent).toBe("AT&TR&D · 3 open roles");
  });

  it("lays out a bold title and one line each, leaving out an empty line", () => {
    const box = tooltip(tooltipHtml("Stripe", ["first", "", "second"]));
    expect(box.querySelectorAll("br")).toHaveLength(2);
    expect([...box.childNodes].map((n) => n.textContent)).toEqual(["Stripe", "", "first", "", "second"]);
  });

  it("puts each tinted part where the message places it", () => {
    // A translation may open with "today", as the Chinese one does.
    const parts = withParts(
      ({ a, b }: { a: string; b: string }) => `today ${a} then ${b}`,
      { a: { text: "+3 new", tone: "new" }, b: { text: "<i>2</i>", tone: "closed" } },
    );
    expect(parts).toEqual(["today ", { text: "+3 new", tone: "new" }, " then ", { text: "<i>2</i>", tone: "closed" }]);
    const box = tooltip(tooltipHtml("Stripe", [parts]));
    expect(box.querySelector("i")).toBeNull();
    expect(box.querySelector(".chart-tip-closed")?.textContent).toBe("<i>2</i>");
    expect(box.textContent).toBe("Stripetoday +3 new then <i>2</i>");
  });
});
