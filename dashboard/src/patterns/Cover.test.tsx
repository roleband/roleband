import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Button } from "../ui";
import { ToastProvider, useToast } from "../ui/Toast";
import { Cover } from "./Cover";

/* The way back raised INSIDE a cover is reachable from inside it. Opened over a
 * list the cover is a modal dialog, so its Tab ring is the whole of what a
 * keyboard can reach — and the toast host is app chrome, outside the dialog.
 * Wired through the real three pieces (Cover's shell, Toast's host, Overlay's
 * ring), because each alone passes its own test while the seam between them is
 * where an Undo gets lost. Paint is proven in the browser
 * (tests/ux/compare.spec.ts); jsdom cannot tell what is on top. */
function Remove() {
  const { toast } = useToast();
  return (
    <Button onClick={() => toast({ text: "Removed a role from compare", action: { label: "Undo", onClick: () => {} } })}>
      Remove
    </Button>
  );
}

function renderCover(asOverlay: boolean) {
  render(
    <ToastProvider>
      <button type="button">Row underneath</button>
      <Cover label="Comparison" asOverlay={asOverlay} onBack={() => {}} bar={<Button>Back</Button>}>
        <Remove />
      </Cover>
    </ToastProvider>,
  );
}

describe("Cover", () => {
  it("opened over a list, lets Tab reach the Undo it raised and come back round", () => {
    renderCover(true);
    const remove = screen.getByRole("button", { name: "Remove" });
    fireEvent.click(remove);
    const undo = screen.getByRole("button", { name: "Undo" });

    remove.focus();
    fireEvent.keyDown(remove, { key: "Tab" });
    expect(undo).toHaveFocus();

    const dismiss = screen.getByRole("button", { name: "Dismiss" });
    dismiss.focus();
    fireEvent.keyDown(dismiss, { key: "Tab" });
    expect(screen.getByRole("button", { name: "Back" })).toHaveFocus();
  });
});

/* A role opened from a Pipeline view opens beside the rail: the rail stays
 * live, the rest of the page goes inert, and Back lands on the page's link to
 * the role. The page around it is drawn as App draws it, with the markers. */
describe("Cover beside the rail", () => {
  function Page({ open, besideRail }: { open: boolean; besideRail: boolean }) {
    return (
      <>
        <nav aria-label="Rail" data-behind-cover="" data-beside-cover="">
          <a href="/pipeline/board">Board</a>
        </nav>
        <div data-behind-cover="">
          <a href={window.location.pathname}>The role's card</a>
          <a href="/company/other/job/9">Another card</a>
        </div>
        {open && (
          <Cover label="Role" asOverlay besideRail={besideRail} onBack={onBack} bar={<Button>Back</Button>}>
            <p>The role</p>
          </Cover>
        )}
      </>
    );
  }
  let onBack: () => void;
  const rail = () => screen.getByRole("navigation", { name: "Rail", hidden: true });
  const page = () => screen.getByText("The role's card", { selector: "a" }).parentElement!;

  beforeEach(() => {
    onBack = vi.fn();
    window.history.replaceState(null, "", "/company/openai/job/202");
  });
  afterEach(() => vi.useRealTimers());

  it("keeps the rail live and is no modal dialog, while the page behind it goes inert", () => {
    render(<Page open besideRail />);
    expect(rail()).not.toHaveAttribute("inert");
    expect(page()).toHaveAttribute("inert");
    expect(screen.getByRole("dialog", { name: "Role" })).not.toHaveAttribute("aria-modal");
  });

  it("starts where the rail ends, and takes the whole width when the rail lies along the bottom", () => {
    const box = (width: number, height: number) => ({ x: 0, y: 0, top: 0, left: 0, right: width, bottom: height, width, height, toJSON: () => ({}) });
    const measure = vi.spyOn(HTMLElement.prototype, "getBoundingClientRect");
    measure.mockImplementation(function (this: HTMLElement) {
      return this.hasAttribute("data-beside-cover") ? box(72, window.innerHeight) : box(0, 0);
    });
    const { unmount } = render(<Page open besideRail />);
    expect(screen.getByRole("dialog", { name: "Role" }).style.getPropertyValue("--cover-left")).toBe("72px");
    unmount();

    measure.mockImplementation(function (this: HTMLElement) {
      return this.hasAttribute("data-beside-cover") ? box(window.innerWidth, 56) : box(0, 0);
    });
    render(<Page open besideRail />);
    expect(screen.getByRole("dialog", { name: "Role" }).style.getPropertyValue("--cover-left")).toBe("0px");
    measure.mockRestore();
  });

  it("goes back on Escape", () => {
    render(<Page open besideRail />);
    fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it("hands focus, once gone, to the page's link to the role it showed, which wears a mark for a moment", () => {
    vi.useFakeTimers();
    const { rerender } = render(<Page open besideRail />);
    rerender(<Page open={false} besideRail />);
    act(() => vi.advanceTimersByTime(0));
    const card = screen.getByText("The role's card", { selector: "a" });
    expect(card).toHaveFocus();
    expect(card).toHaveAttribute("data-returned");
    expect(screen.getByText("Another card", { selector: "a" })).not.toHaveAttribute("data-returned");
    act(() => vi.advanceTimersByTime(2400));
    expect(card).not.toHaveAttribute("data-returned");
    expect(page()).not.toHaveAttribute("inert");
  });

  it("opened over the Radar's list, stays modal and takes the rail with the page", () => {
    render(<Page open besideRail={false} />);
    expect(rail()).toHaveAttribute("inert");
    expect(page()).toHaveAttribute("inert");
    expect(screen.getByRole("dialog", { name: "Role" })).toHaveAttribute("aria-modal", "true");
  });
});
