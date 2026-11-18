/* Layout facts a person sees and a centre-to-centre check does not: whether
 * something is cut off, and whether two things sit on top of each other.
 *
 * Both work from the boxes the browser laid out, so they hold whatever the
 * words, the language or the font: a column sized by hand to one label passes
 * a centre check and fails these once a longer label lands in it. */

import { expect, type Locator } from "@playwright/test";

export interface Edges {
  left: number;
  right: number;
  top: number;
  bottom: number;
}

/** How many pixels of the element the viewport, or a box that clips it, hides
 *  on each side. All zeros means the whole element can be seen.
 *
 *  A box clips only the descendants whose containing blocks run through it:
 *  an absolutely placed child escapes a clipping parent that is not
 *  positioned, a fixed one escapes everything but a transformed or filtered
 *  ancestor, and an element in the top layer (an open popover, a modal
 *  dialog) escapes every ancestor. */
export async function hiddenEdges(locator: Locator): Promise<Edges> {
  return locator.evaluate((el) => {
    const style = (node: Element) => getComputedStyle(node);
    const boundsFixed = (s: CSSStyleDeclaration) =>
      s.transform !== "none" ||
      s.filter !== "none" ||
      (s.backdropFilter ?? "none") !== "none" ||
      s.perspective !== "none" ||
      /paint|layout|strict|content/.test(s.contain) ||
      /transform|filter|perspective/.test(s.willChange);
    const containingBlock = (node: Element): Element | null => {
      const position = style(node).position;
      let up = node.parentElement;
      if (position === "fixed") {
        while (up && !boundsFixed(style(up))) up = up.parentElement;
        return up;
      }
      if (position === "absolute") {
        while (up && style(up).position === "static" && !boundsFixed(style(up))) up = up.parentElement;
        return up;
      }
      return up;
    };
    const inTopLayer = (node: Element) => {
      try {
        return node.matches(":popover-open, :modal");
      } catch {
        return false;
      }
    };

    const rect = el.getBoundingClientRect();
    const clip = { left: 0, top: 0, right: window.innerWidth, bottom: window.innerHeight };
    let node: Element = el;
    while (!inTopLayer(node)) {
      const block = containingBlock(node);
      // The root's and the body's overflow belong to the viewport, counted above.
      if (!block || block === document.body || block === document.documentElement) break;
      const s = style(block);
      const paint = /paint|strict|content/.test(s.contain);
      const box = block.getBoundingClientRect();
      const left = box.left + block.clientLeft;
      const top = box.top + block.clientTop;
      if (paint || s.overflowX !== "visible") {
        clip.left = Math.max(clip.left, left);
        clip.right = Math.min(clip.right, left + block.clientWidth);
      }
      if (paint || s.overflowY !== "visible") {
        clip.top = Math.max(clip.top, top);
        clip.bottom = Math.min(clip.bottom, top + block.clientHeight);
      }
      node = block;
    }
    const side = (n: number) => Math.max(0, Math.round(n));
    return {
      left: side(clip.left - rect.left),
      right: side(rect.right - clip.right),
      top: side(clip.top - rect.top),
      bottom: side(rect.bottom - clip.bottom),
    };
  });
}

/** Fails, naming the sides, unless the whole element can be seen. */
export async function expectFullyVisible(locator: Locator, what: string) {
  await expect(locator).toBeVisible();
  expect(await hiddenEdges(locator), `${what}: pixels hidden on each side`).toEqual({
    left: 0,
    right: 0,
    top: 0,
    bottom: 0,
  });
}

interface Laid {
  what: string;
  left: number;
  right: number;
  top: number;
  bottom: number;
}

/** Every visible element `selector` matches inside `scope`, named by its text
 *  or its accessible label, with the box the browser gave it. */
export async function laidOut(scope: Locator, selector: string): Promise<Laid[]> {
  return scope.evaluate((root, sel) => {
    return [...root.querySelectorAll(sel)]
      .filter((el) => {
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== "hidden";
      })
      .map((el) => {
        const r = el.getBoundingClientRect();
        const name = el.getAttribute("aria-label") ?? el.textContent?.trim() ?? "";
        return {
          what: `${el.tagName.toLowerCase()}.${[...el.classList].join(".")} "${name.slice(0, 40)}"`,
          left: r.left,
          right: r.right,
          top: r.top,
          bottom: r.bottom,
        };
      });
  }, selector);
}

/** Every pair of the elements whose boxes cross, by more than half a pixel
 *  each way. An empty list means nothing sits on anything else. */
export function overlapping(boxes: Laid[]): string[] {
  const out: string[] = [];
  for (let i = 0; i < boxes.length; i++) {
    for (let j = i + 1; j < boxes.length; j++) {
      const a = boxes[i];
      const b = boxes[j];
      const x = Math.min(a.right, b.right) - Math.max(a.left, b.left);
      const y = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
      if (x > 0.5 && y > 0.5) out.push(`${a.what} × ${b.what} (${Math.round(x)}px)`);
    }
  }
  return out;
}
