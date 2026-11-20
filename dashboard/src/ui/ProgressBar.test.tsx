import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ProgressBar } from "./ProgressBar";

describe("ProgressBar", () => {
  it("states a counted value, bounded to its range", () => {
    render(<ProgressBar value={12} max={10} label="Companies scanned" />);
    const bar = screen.getByRole("progressbar", { name: "Companies scanned" });
    expect(bar).toHaveAttribute("aria-valuenow", "10");
    expect(bar).toHaveAttribute("aria-valuemax", "10");
    expect(bar).not.toHaveClass("ui-progress-indeterminate");
  });

  it("with no value claims none: a wait nothing can measure", () => {
    render(<ProgressBar label="Getting the description" />);
    const bar = screen.getByRole("progressbar", { name: "Getting the description" });
    expect(bar).not.toHaveAttribute("aria-valuenow");
    expect(bar).not.toHaveAttribute("aria-valuemax");
    expect(bar).toHaveClass("ui-progress-indeterminate");
  });
});
