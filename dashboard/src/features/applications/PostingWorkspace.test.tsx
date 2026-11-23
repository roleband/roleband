import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { applicationDetailFixture, jobDetailFixture } from "../../test/fixtures";
import { msg } from "../../test/msg";
import { fakeViewChoiceServer } from "../../test/viewChoicesServer";
import PostingWorkspace from "./PostingWorkspace";
import type { WorkspaceProps } from "./Workspace";

/* A posting's Workspace tab says what changed on the posting since the person
 * applied, until they put the line away. What they put away is one of their
 * view choices, kept in the database, and the read of those choices can
 * answer after the tab first draws: a line put away before stays away, and
 * putting one away keeps every other. */

vi.mock("./Workspace", () => ({ Workspace: () => <p>The role's blocks</p> }));

const CHOICE = "pipeline.crossings-dismissed";
const CLOSED_AT = "2026-11-10T09:00:00Z";
const THIS_LINE = `101:closed:${CLOSED_AT}`;
const ANOTHER_ROLES_LINE = "102:closed:2026-11-12T09:00:00Z";

const closedLine = () => screen.queryByText(msg("applications-crossing-closed", { days: 9 }));

/** The view-choice server, its read held until `answer` is called. */
function slowServer(held: Record<string, unknown>) {
  const server = fakeViewChoiceServer(held);
  let answer!: () => void;
  server.read.mockImplementationOnce(() => new Promise((resolve) => {
    answer = () => resolve({ choices: held as never });
  }));
  return {
    server,
    answer: () => act(async () => {
      await vi.waitFor(() => expect(server.read).toHaveBeenCalled());
      answer();
    }),
  };
}

function renderTab() {
  const workspace = { detail: applicationDetailFixture() } as unknown as WorkspaceProps;
  const job = jobDetailFixture({ id: 101, lifecycle: [{ event_type: "closed", at: CLOSED_AT, detail: {} }] });
  return render(<PostingWorkspace job={job} onShowPosting={vi.fn()} {...workspace} />);
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("a posting's change since applying", () => {
  it("stays away when it was put away before, also when the read answers after the tab draws", async () => {
    const { answer } = slowServer({ [CHOICE]: [THIS_LINE] });
    renderTab();
    expect(screen.getByText("The role's blocks")).toBeInTheDocument();
    await answer();
    expect(closedLine(), "a line put away in another session stays away").toBeNull();
  });

  it("is put away alongside every line put away before", async () => {
    const { server, answer } = slowServer({ [CHOICE]: [ANOTHER_ROLES_LINE] });
    renderTab();
    await answer();
    expect(closedLine()).not.toBeNull();

    await userEvent.click(screen.getByRole("button", { name: msg("applications-crossing-dismiss") }));
    expect(closedLine()).toBeNull();
    await vi.waitFor(() => expect(server.saved()[CHOICE]).toEqual([ANOTHER_ROLES_LINE, THIS_LINE]));
  });
});
