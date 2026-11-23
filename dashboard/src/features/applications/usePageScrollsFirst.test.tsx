import { render } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { usePageScrollsFirst } from "./usePageScrollsFirst";

/* A page that can scroll `room` more pixels, holding a frame that scrolls on
   its own. jsdom lays nothing out, so the page's sizes are set by hand. */
function Page() {
  const [node, setNode] = useState<HTMLDivElement | null>(null);
  usePageScrollsFirst(node);
  return (
    <main data-testid="page">
      <div data-testid="frame" ref={setNode}>
        <span data-testid="card">card</span>
      </div>
    </main>
  );
}

function at(room: number, scrolled = 0) {
  const view = render(<Page />);
  const page = view.getByTestId("page");
  Object.defineProperty(page, "clientHeight", { configurable: true, value: 600 });
  Object.defineProperty(page, "scrollHeight", { configurable: true, value: 600 + room });
  page.scrollTop = scrolled;
  return { page, card: view.getByTestId("card") };
}

/** A wheel over the card; whether the browser may still scroll the frame. */
function wheel(target: Element, init: WheelEventInit): boolean {
  const event = new WheelEvent("wheel", { bubbles: true, cancelable: true, ...init });
  target.dispatchEvent(event);
  return !event.defaultPrevented;
}

describe("a scroll down over the board's frame moves the page first", () => {
  it("takes the wheel for the page while the page has room, and no further than that room", () => {
    const { page, card } = at(180);
    expect(wheel(card, { deltaY: 100 }), "the frame scrolled while the title was still on screen").toBe(false);
    expect(page.scrollTop).toBe(100);
    expect(wheel(card, { deltaY: 100 })).toBe(false);
    expect(page.scrollTop, "the page went past where its toolbar docks").toBe(180);
  });

  it("leaves the wheel to the frame once the page is as far down as it goes", () => {
    const { page, card } = at(180, 180);
    expect(wheel(card, { deltaY: 100 })).toBe(true);
    expect(page.scrollTop).toBe(180);
  });

  it("counts a wheel that reports lines, not pixels", () => {
    const { page, card } = at(180);
    wheel(card, { deltaY: 3, deltaMode: WheelEvent.DOM_DELTA_LINE });
    expect(page.scrollTop).toBe(48);
  });

  it("leaves a scroll up, a sideways scroll and a pinch to the browser", () => {
    const { page, card } = at(180, 90);
    expect(wheel(card, { deltaY: -100 }), "up").toBe(true);
    expect(wheel(card, { deltaX: 120, deltaY: 20 }), "sideways").toBe(true);
    expect(wheel(card, { deltaY: 100, ctrlKey: true }), "pinch").toBe(true);
    expect(page.scrollTop).toBe(90);
  });
});
