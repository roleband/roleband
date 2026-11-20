import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { msg } from "../../test/msg";
import { JobDescription } from "./JobDescription";

describe("JobDescription", () => {
  it("renders source sections, qualifications as lists, and pay as its own region", () => {
    render(
      <JobDescription
        sections={[
          { key: "summary", title: "Summary", content: "Lead the platform." },
          {
            key: "minimum_qualifications",
            title: "Minimum Qualifications",
            content: "10+ years in product\nExperience with AI systems",
          },
          {
            key: "pay_and_benefits",
            title: "Pay & Benefits",
            content: "Base pay range: $250,800 to $376,300 per year.",
          },
        ]}
      />,
    );

    expect(screen.getByRole("heading", { name: "Summary" })).toBeVisible();
    const qualifications = screen.getByRole("heading", { name: "Minimum Qualifications" })
      .closest("section")!;
    expect(within(qualifications).getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByText(/\$250,800 to \$376,300/)).toBeVisible();
    expect(screen.getByRole("heading", { name: "Pay & Benefits" }).closest("section"))
      .toHaveClass("jd-section-pay_and_benefits");
  });

  it("falls back to legacy plain text when sections are absent", () => {
    render(<JobDescription fallback="Legacy complete description." />);
    expect(screen.getByText("Legacy complete description.")).toBeVisible();
    expect(screen.getByText("Legacy complete description.").closest(".jd")).not.toBeNull();
  });

  it("with no text at all, says so as a quiet fact, not as text to read", () => {
    const { container } = render(<JobDescription sections={[]} fallback={null} />);
    const said = screen.getByText(msg("role-job-description-no-description-captured"));
    expect(said.tagName).toBe("P");
    expect(said).toHaveClass("jd-empty");
    expect(container.querySelector(".jd, .jd-sections")).toBeNull();
  });
});

describe("JobDescription while its text is read", () => {
  const posting = "https://jobs.lever.co/spotify/cc5ccf57";
  const reading = (phase: "reading" | "slow" | "failed", retry = vi.fn()) =>
    render(
      <JobDescription
        sections={[]}
        fallback={null}
        read={{ phase, retry }}
        company="Spotify"
        postingUrl={posting}
      />,
    );

  it("says what is happening under a running line, and nothing about a missing description", () => {
    reading("reading");
    const region = screen.getByRole("status");
    expect(region).toHaveTextContent(msg("role-job-description-reading", { company: "Spotify" }));
    const bar = within(region).getByRole("progressbar", { name: msg("role-job-description-reading-progress") });
    expect(bar).not.toHaveAttribute("aria-valuenow");
    // The posting is not offered yet: most reads land before anyone needs it.
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.queryByText(msg("role-job-description-no-description-captured"))).toBeNull();
  });

  it("once the site is slow, keeps waiting and offers the posting there", () => {
    reading("slow");
    const region = screen.getByRole("status");
    expect(region).toHaveTextContent(msg("role-job-description-reading-slow", { company: "Spotify" }));
    expect(within(region).getByRole("progressbar")).toBeVisible();
    const link = within(region).getByRole("link", { name: msg("role-job-description-open-posting", { company: "Spotify" }) });
    expect(link).toHaveAttribute("href", posting);
    expect(link).toHaveAttribute("target", "_blank");
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("when the read failed, stops the line, offers Try again and the posting", async () => {
    const retry = vi.fn();
    reading("failed", retry);
    const region = screen.getByRole("status");
    expect(region).toHaveTextContent(msg("role-job-description-read-failed", { company: "Spotify" }));
    expect(within(region).queryByRole("progressbar")).toBeNull();
    expect(within(region).getByRole("link")).toHaveAttribute("href", posting);

    await userEvent.click(within(region).getByRole("button", { name: msg("common-try-again") }));
    expect(retry).toHaveBeenCalledTimes(1);
  });

  it("shows the text, not the read, once the text is there, and lets it come in", () => {
    const { container } = render(
      <JobDescription
        sections={[{ key: "summary", title: "Summary", content: "Lead the platform." }]}
        read={{ phase: "reading", retry: vi.fn() }}
        arrived
        company="Spotify"
      />,
    );
    expect(screen.getByText("Lead the platform.")).toBeVisible();
    expect(screen.queryByRole("status")).toBeNull();
    expect(container.querySelector(".jd-sections")).toHaveClass("jd-arrived");
  });
});
