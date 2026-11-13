import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { HiringCompaniesChart, type HiringBar } from "./StatisticsCharts";

/* A company's bar, or its name on the axis, opens that company's roles. The
 * chart wrapper is the boundary to the charting runtime: a probe keeps the
 * option and the event handlers the chart hands it, and the test fires the
 * click the runtime would. */

type Probe = { option: Record<string, any>; onEvents?: Record<string, (p: unknown) => void> };
const probe = vi.hoisted(() => ({ current: null as Probe | null }));
vi.mock("../../../ui/EChart", () => ({
  EChart: (props: Probe) => {
    probe.current = props;
    return null;
  },
}));

const bars: HiringBar[] = [
  { company: "anthropic", label: "Anthropic", open: 48, fresh: 2, closed: 1 },
  { company: "google", label: "Google", open: 41, fresh: 1, closed: 0 },
  { company: "openai", label: "OpenAI", open: 33, fresh: 1, closed: 1 },
];

const click = (params: unknown) => probe.current?.onEvents?.click(params);

beforeEach(() => {
  probe.current = null;
});

describe("HiringCompaniesChart", () => {
  it("hands the company of the clicked bar to onPick, leaders drawn top-down", () => {
    const onPick = vi.fn();
    render(<HiringCompaniesChart bars={bars} onPick={onPick} />);
    // The axis draws bottom-up, so the rows are reversed: index 0 is the last bar.
    const labels = probe.current!.option.yAxis.data as string[];
    expect(labels).toEqual(["OpenAI", "Google", "Anthropic"]);

    click({ componentType: "series", dataIndex: 2 });
    expect(onPick).toHaveBeenLastCalledWith("anthropic");
    click({ componentType: "series", dataIndex: 0 });
    expect(onPick).toHaveBeenLastCalledWith("openai");
  });

  it("hands the company of a clicked axis name to onPick", () => {
    const onPick = vi.fn();
    render(<HiringCompaniesChart bars={bars} onPick={onPick} />);
    expect(probe.current!.option.yAxis.triggerEvent).toBe(true);

    click({ componentType: "yAxis", value: "Google" });
    expect(onPick).toHaveBeenCalledExactlyOnceWith("google");
  });

  it("ignores a click on nothing it drew", () => {
    const onPick = vi.fn();
    render(<HiringCompaniesChart bars={bars} onPick={onPick} />);
    click({ componentType: "series", dataIndex: 7 });
    click({ componentType: "yAxis", value: "Netflix" });
    expect(onPick).not.toHaveBeenCalled();
  });

  it("keeps its option and handlers while its bars stay the same, and replaces them when the bars change", () => {
    const onPick = vi.fn();
    const { rerender } = render(<HiringCompaniesChart bars={bars} onPick={onPick} />);
    const first = probe.current!;
    rerender(<HiringCompaniesChart bars={bars} onPick={onPick} />);
    // A new option redraws every label, so the one under the pointer would be a new element.
    expect(probe.current!.option).toBe(first.option);
    expect(probe.current!.onEvents).toBe(first.onEvents);

    const fewer = bars.slice(0, 2);
    rerender(<HiringCompaniesChart bars={fewer} onPick={onPick} />);
    expect(probe.current!.option).not.toBe(first.option);
    expect(probe.current!.option.yAxis.data).toEqual(["Google", "Anthropic"]);
    click({ componentType: "series", dataIndex: 0 });
    expect(onPick).toHaveBeenLastCalledWith("google");
  });

  it("listens for nothing without onPick", () => {
    render(<HiringCompaniesChart bars={bars} />);
    expect(probe.current!.onEvents).toBeUndefined();
    expect(probe.current!.option.yAxis.triggerEvent).toBe(false);
  });
});
