import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { IntelligenceStatus } from "../../api";
import { msg } from "../../test/msg";
import { intelligenceStatusFixture } from "../../test/fixtures";
import { MatchingModel } from "./MatchingModel";

// The RAM line the automatic choice draws is the server's
// (`provision.TIER_RAM_THRESHOLD`), sent as `ram_threshold_bytes`. A value
// other than the shipped 16 GiB shows whether the screen reads it or keeps
// its own copy.
const GIB = 1024 ** 3;

function statusWith(matching: Partial<IntelligenceStatus["matching"]>): IntelligenceStatus {
  return {
    ...intelligenceStatusFixture,
    matching: { ...intelligenceStatusFixture.matching, ...matching } as IntelligenceStatus["matching"],
  };
}

async function openSwitchToSmall(status: IntelligenceStatus) {
  render(<MatchingModel status={status} setStatus={vi.fn()} />);
  await userEvent.click(
    screen.getByRole("button", {
      name: msg("ai-matching-model-switch-to-the", { nAME_LOWER: msg("ai-matching-model-small-model-2") }),
    }),
  );
  return screen.findByRole("dialog", { name: msg("ai-matching-model-local-ai-model-switch") });
}

describe("MatchingModel", () => {
  it("states the RAM threshold the server sends beside the machine's own", async () => {
    const dialog = await openSwitchToSmall(statusWith({ ram_threshold_bytes: 24 * GIB, detected_ram_bytes: 48 * GIB }));
    const builtFor = within(dialog).getByText(msg("ai-matching-model-small-model-is-built-for")).closest("div");
    expect(builtFor).toHaveTextContent(/^.*24\s*GB$/);
    const yours = within(dialog).getByText(msg("ai-matching-model-your-computer-has")).closest("div");
    expect(yours).toHaveTextContent(/48\s*GB$/);
  });

  it("states the threshold in the sentence when this computer's RAM was not detected", async () => {
    const dialog = await openSwitchToSmall(statusWith({ ram_threshold_bytes: 24 * GIB, detected_ram_bytes: null }));
    expect(dialog).toHaveTextContent(msg("ai-matching-model-gb", { ramThresholdGb: 24 }));
    expect(dialog).not.toHaveTextContent(msg("ai-matching-model-gb", { ramThresholdGb: 16 }));
  });

  it("counts ranked roles in the reader's plural, with the number grouped", () => {
    const { rerender } = render(<MatchingModel status={statusWith({ corpus_embedded: 1, corpus_total: 1 })} setStatus={vi.fn()} />);
    expect(screen.getByText(msg("ai-matching-model-roles-ranked", { choice: "no", value: 0, corpus_total: 0, corpus_embedded: 1 }))).toBeInTheDocument();
    expect(screen.getByText("1 role ranked")).toBeInTheDocument();
    rerender(<MatchingModel status={statusWith({ corpus_embedded: 1234, corpus_total: 1234 })} setStatus={vi.fn()} />);
    expect(screen.getByText("1,234 roles ranked")).toBeInTheDocument();
  });
});
