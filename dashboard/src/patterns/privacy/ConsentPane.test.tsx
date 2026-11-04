import { createRef } from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { api } from "../../api";
import { ApiError } from "../../api/transport";
import { usageStateFixture } from "../../test/fixtures";
import { ConsentPane } from "./ConsentPane";
import { consentText, consentWords, groupsToAsk } from "./consentCopy";
import { msg } from "../../test/msg";

/* The usage-sharing question (docs/architecture.md): the record carries
   exactly the words on screen, "Happy to help" shares every kind asked in one
   click, nothing is ever pre-ticked, choosing shares exactly what was ticked,
   and a refusal says so and shares nothing. */

vi.mock("../../api", () => ({
  api: { saveUsageConsent: vi.fn() },
}));

const ALL = ["usage", "crashes", "questions"] as const;

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.saveUsageConsent).mockResolvedValue(usageStateFixture("shared"));
});

function sent() {
  expect(api.saveUsageConsent).toHaveBeenCalledTimes(1);
  return vi.mocked(api.saveUsageConsent).mock.calls[0][0];
}

const region = () => screen.getByRole("region", { name: "Help us improve" });
const answerNames = () => within(region()).getAllByRole("button").map((button) => button.textContent);

it("records exactly the words the screen shows", async () => {
  render(<ConsentPane state={usageStateFixture("undecided")} groups={[...ALL]} onAnswered={vi.fn()} />);
  await userEvent.click(screen.getByRole("button", { name: "Happy to help" }));
  await waitFor(() => expect(api.saveUsageConsent).toHaveBeenCalled());
  const { text, locale } = sent();
  expect(text).toBe(consentText(consentWords([...ALL])));
  for (const paragraph of text.split("\n\n")) {
    for (const part of paragraph.split(": ")) expect(region()).toHaveTextContent(part.trim());
  }
  expect(locale).toBe("en");
});

it("the welcome's look records the same words, keeps the answers equal, and puts a box in each icon's place", async () => {
  const { container } = render(<ConsentPane look="scene" state={usageStateFixture("undecided")} groups={[...ALL]} onAnswered={vi.fn()} />);
  // One mark for each kind, and one for the promise; no box until someone chooses.
  expect(container.querySelectorAll(".privacy-consent-icon")).toHaveLength(4);
  expect(screen.queryByRole("checkbox")).toBeNull();
  const no = screen.getByRole("button", { name: "No thanks" });
  expect(no.className).toBe(screen.getByRole("button", { name: "Happy to help" }).className);

  await userEvent.click(screen.getByRole("button", { name: "Let me choose" }));
  expect(screen.getAllByRole("checkbox")).toHaveLength(3);
  expect(container.querySelectorAll(".privacy-consent-groups .privacy-consent-icon")).toHaveLength(0);
  await userEvent.click(screen.getByRole("checkbox", { name: /Crash reports/ }));
  await userEvent.click(screen.getByRole("button", { name: "Happy to help" }));
  await waitFor(() => expect(api.saveUsageConsent).toHaveBeenCalled());
  const { text, answers } = sent();
  expect(text).toBe(consentText(consentWords([...ALL])));
  expect(answers).toEqual({ usage: false, crashes: true, questions: false });
});

it("speaks as us, gives a reason to help, and says what is never sent", () => {
  render(<ConsentPane state={usageStateFixture("undecided")} groups={[...ALL]} onAnswered={vi.fn()} />);
  expect(screen.getByRole("heading", { name: "Help us improve" })).toBeVisible();
  expect(region()).toHaveAccessibleDescription(/free and open source/);
  // The product's name is not spent where "us" will do.
  expect(region()).not.toHaveTextContent("RoleBand");
  for (const name of ["Anonymous usage data", "Crash reports", "Feedback surveys"]) {
    expect(within(region()).getByText(name)).toBeVisible();
  }
  expect(region()).toHaveTextContent("Never sent: Company names, role titles, compensation, your CV or anything you type.");
  expect(region()).not.toHaveTextContent(/Where it goes|PostHog|Session recordings/);
});

it("lays the reason out a sentence a line, and records it as the one paragraph it reads as", () => {
  render(<ConsentPane look="scene" state={usageStateFixture("undecided")} groups={[...ALL]} onAnswered={vi.fn()} />);
  const lines = [msg("privacy-consent-intro"), msg("privacy-consent-intro-data")];
  for (const line of lines) expect(screen.getByText(line)).toHaveClass("privacy-consent-intro-line");
  const paragraphs = consentText(consentWords([...ALL])).split("\n\n");
  expect(paragraphs[1]).toBe(lines.join(" "));
  expect(paragraphs).toContain(`${msg("privacy-never-label")}: ${msg("privacy-never")}`);
  // Read aloud, the two lines are one description, a space between them.
  expect(region()).toHaveAccessibleDescription(lines.join(" "));
});

it("asks with nothing ticked: no box until someone chooses", () => {
  render(<ConsentPane state={usageStateFixture("undecided")} groups={[...ALL]} onAnswered={vi.fn()} />);
  expect(screen.queryByRole("checkbox")).toBeNull();
  expect(answerNames()).toEqual(["Let me choose", "No thanks", "Happy to help"]);
});

it("Happy to help shares every kind asked, in one click", async () => {
  render(<ConsentPane state={usageStateFixture("undecided")} groups={[...ALL]} onAnswered={vi.fn()} />);
  const no = screen.getByRole("button", { name: "No thanks" });
  const yes = screen.getByRole("button", { name: "Happy to help" });
  expect(no.className).toBe(yes.className);
  await userEvent.click(yes);
  await waitFor(() => expect(api.saveUsageConsent).toHaveBeenCalled());
  const { answers, fingerprints } = sent();
  expect(answers).toEqual({ usage: true, crashes: true, questions: true });
  expect(fingerprints).toEqual({
    usage: "usage-fingerprint", crashes: "crashes-fingerprint", questions: "questions-fingerprint",
  });
});

it("choosing opens clear boxes, focuses the first, and shares exactly what was ticked", async () => {
  render(<ConsentPane state={usageStateFixture("undecided")} groups={[...ALL]} onAnswered={vi.fn()} />);
  await userEvent.click(screen.getByRole("button", { name: "Let me choose" }));
  const boxes = screen.getAllByRole("checkbox");
  expect(boxes).toHaveLength(3);
  for (const box of boxes) expect(box).not.toBeChecked();
  expect(boxes[0]).toHaveFocus();
  expect(screen.queryByRole("button", { name: "Let me choose" })).toBeNull();
  // Nothing ticked is nothing to share: the warm answer waits.
  expect(screen.getByRole("button", { name: "Happy to help" })).toBeDisabled();
  // The whole row is the hit target.
  await userEvent.click(screen.getByText("What broke and where, so we can fix it fast."));
  await userEvent.click(screen.getByRole("button", { name: "Happy to help" }));
  await waitFor(() => expect(api.saveUsageConsent).toHaveBeenCalled());
  expect(sent().answers).toEqual({ usage: false, crashes: true, questions: false });
});

it("No thanks declines everything, even with boxes ticked", async () => {
  const onAnswered = vi.fn();
  render(<ConsentPane state={usageStateFixture("undecided")} groups={[...ALL]} onAnswered={onAnswered} />);
  await userEvent.click(screen.getByRole("button", { name: "Let me choose" }));
  await userEvent.click(screen.getByRole("checkbox", { name: /Anonymous usage data/ }));
  await userEvent.click(screen.getByRole("button", { name: "No thanks" }));
  await waitFor(() => expect(onAnswered).toHaveBeenCalled());
  expect(sent().answers).toEqual({ usage: false, crashes: false, questions: false });
});

it("asks about one kind with nothing to choose, and declines only it", async () => {
  const onAnswered = vi.fn();
  render(<ConsentPane state={usageStateFixture("undecided")} groups={["questions"]} onAnswered={onAnswered} />);
  expect(screen.queryByText("Anonymous usage data")).toBeNull();
  expect(answerNames()).toEqual(["No thanks", "Happy to help"]);
  await userEvent.click(screen.getByRole("button", { name: "No thanks" }));
  await waitFor(() => expect(onAnswered).toHaveBeenCalled());
  expect(sent().answers).toEqual({ questions: false });
  expect(sent().text).not.toContain("Anonymous usage data");
});

it("says why when the answer is refused, and stays on the question", async () => {
  vi.mocked(api.saveUsageConsent).mockRejectedValue(
    new ApiError("older scope", 409, "usage-catalogue-changed", { groups: ["usage"] }),
  );
  const onAnswered = vi.fn();
  render(<ConsentPane state={usageStateFixture("undecided")} groups={[...ALL]} onAnswered={onAnswered} />);
  await userEvent.click(screen.getByRole("button", { name: "Happy to help" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("What's shared changed while you were choosing. Try again.");
  expect(onAnswered).not.toHaveBeenCalled();
});

it("asks only about groups never answered or widened since", () => {
  const state = usageStateFixture("declined");
  state.groups[0].status = "undecided";
  state.groups[1].status = "stale";
  state.groups[2].status = "shared";
  expect(groupsToAsk(state)).toEqual(["usage", "crashes"]);
});

/* Asked again (`review`): the welcome walk's way back to a question already
   answered. It opens on the answer, marks that answer's own button "Your
   answer", and pressing it records nothing. */

/** An answered state: each kind shared or declined as given. */
function answered(shared: readonly (typeof ALL)[number][]) {
  const state = usageStateFixture("declined");
  for (const group of state.groups) group.status = shared.includes(group.group) ? "shared" : "declined";
  return state;
}

const yours = () => within(region()).queryAllByRole("button", { description: "Your answer" });

it("asked again after No thanks, marks No thanks as the answer, and pressing it records nothing", async () => {
  const state = answered([]);
  const onAnswered = vi.fn();
  render(<ConsentPane review state={state} groups={[...ALL]} onAnswered={onAnswered} />);
  expect(screen.queryByRole("checkbox")).toBeNull();
  expect(yours()).toEqual([screen.getByRole("button", { name: "No thanks" })]);
  // A mark, not a third answer: still two answers and the way to choose.
  expect(within(region()).getAllByRole("button").map((button) => button.getAttribute("aria-describedby") ? "marked" : button.textContent))
    .toEqual(["Let me choose", "marked", "Happy to help"]);
  await userEvent.click(screen.getByRole("button", { name: "No thanks" }));
  expect(onAnswered).toHaveBeenCalledWith(state);
  expect(api.saveUsageConsent).not.toHaveBeenCalled();
});

it("asked again after Happy to help, marks it, takes the keyboard to it, and No thanks records the words again", async () => {
  const safe = createRef<HTMLButtonElement>();
  render(<ConsentPane review safeRef={safe} state={answered([...ALL])} groups={[...ALL]} onAnswered={vi.fn()} />);
  const happy = screen.getByRole("button", { name: "Happy to help" });
  expect(yours()).toEqual([happy]);
  // Enter on the marked answer changes nothing, so it is the safe one here.
  expect(safe.current).toBe(happy);
  await userEvent.click(screen.getByRole("button", { name: "No thanks" }));
  await waitFor(() => expect(api.saveUsageConsent).toHaveBeenCalled());
  const { answers, text } = sent();
  expect(answers).toEqual({ usage: false, crashes: false, questions: false });
  expect(text).toBe(consentText(consentWords([...ALL])));
});

it("asked again after choosing some, opens on exactly the person's own ticks and records a change", async () => {
  render(<ConsentPane review state={answered(["crashes"])} groups={[...ALL]} onAnswered={vi.fn()} />);
  expect(yours()).toEqual([screen.getByRole("button", { name: "Happy to help" })]);
  // Open from the start, the boxes do not take the keyboard from the answer.
  for (const box of screen.getAllByRole("checkbox")) expect(box).not.toHaveFocus();
  expect(screen.getByRole("checkbox", { name: /Anonymous usage data/ })).not.toBeChecked();
  expect(screen.getByRole("checkbox", { name: /Crash reports/ })).toBeChecked();
  expect(screen.getByRole("checkbox", { name: /Feedback surveys/ })).not.toBeChecked();
  await userEvent.click(screen.getByRole("checkbox", { name: /Feedback surveys/ }));
  await userEvent.click(screen.getByRole("button", { name: "Happy to help" }));
  await waitFor(() => expect(api.saveUsageConsent).toHaveBeenCalled());
  expect(sent().answers).toEqual({ usage: false, crashes: true, questions: true });
});

it("asked again after choosing some, marks the answer only while the boxes show it", async () => {
  const onAnswered = vi.fn();
  const state = answered(["usage", "crashes"]);
  render(<ConsentPane review state={state} groups={[...ALL]} onAnswered={onAnswered} />);
  const crashes = screen.getByRole("checkbox", { name: /Crash reports/ });
  // Unticking a kind that is shared makes a new answer: a mark on it would
  // keep that kind shared under a screen that shows it off.
  await userEvent.click(crashes);
  expect(yours()).toEqual([]);
  await userEvent.click(crashes);
  expect(yours()).toHaveLength(1);
  await userEvent.click(screen.getByRole("button", { name: "Happy to help" }));
  expect(onAnswered).toHaveBeenCalledWith(state);
  expect(api.saveUsageConsent).not.toHaveBeenCalled();
});

it("asked again after choosing some, records the change once a tick moves", async () => {
  const onAnswered = vi.fn();
  render(<ConsentPane review state={answered(["usage", "crashes"])} groups={[...ALL]} onAnswered={onAnswered} />);
  await userEvent.click(screen.getByRole("checkbox", { name: /Crash reports/ }));
  await userEvent.click(screen.getByRole("button", { name: "Happy to help" }));
  await waitFor(() => expect(api.saveUsageConsent).toHaveBeenCalled());
  expect(sent().answers).toEqual({ usage: true, crashes: false, questions: false });
  expect(onAnswered).toHaveBeenCalledTimes(1);
});

it("asked again with a kind widened since, marks nothing and ticks nothing for it", () => {
  const state = answered([...ALL]);
  state.groups[1].status = "stale";
  render(<ConsentPane review state={state} groups={[...ALL]} onAnswered={vi.fn()} />);
  expect(yours()).toEqual([]);
  expect(screen.queryByRole("checkbox")).toBeNull();
});

it("asked the first time, marks nothing, even on a state that has an answer", () => {
  render(<ConsentPane state={answered(["usage"])} groups={[...ALL]} onAnswered={vi.fn()} />);
  expect(yours()).toEqual([]);
  expect(screen.queryByRole("checkbox")).toBeNull();
});
