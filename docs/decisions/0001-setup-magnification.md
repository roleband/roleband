# 0001: First-run setup is magnified with CSS zoom

## Context

First-run setup is designed and tested at 1440 x 900. On a large window it sits
small in the middle of the screen, with wide empty margins, at the moment a person
first meets the app. Making it larger must keep the design exactly as it is: the
same weights, the same proportions, the same line breaks, the same alignment
between cards. Any approach that re-lays the screens out for a larger window is a
redesign of every step, and its result has to be reviewed again at every size.

## Decision

Setup is drawn larger by one factor, CSS `zoom` on the root element, only while
setup is on screen ([docs/ui.md](../ui.md#first-run-setup-magnification)):

- The factor follows the window, from 1 at 1440 x 760 up to 1.3, growing by six
  tenths of the window's spare room rather than all of it: the long steps keep
  more of their rows above the fold, and the short ones still grow. It is not
  rounded, so the browser's own zoom can only make setup larger.
- An engine that does not draw text in proportion under the zoom keeps the
  factor at 1. Whether it does is measured in the browser at the factor, never
  assumed from the engine's name.
- Everything the zoom does not scale correctly is corrected where it is written:
  window units divide by the zoom, the planet converts its pointer and its
  backing store, and pop-ups placed from a position stay out of setup.
- A browser without `zoom` gets setup at its plain size.

## Consequences

- Setup at 1.3 is the design, larger, by construction: a test compares every
  element of every setup screen against the design, in the engines that
  magnify.
- A new window unit, or a setup screen that reaches a pop-up placed from a
  position, fails a unit test until it is corrected or listed with its reason
  (`features/scope/setupZoom.test.ts`).
- Chrome on Linux with font hinting is not magnified, because it rounds letters
  to whole pixels and would rewrap lines. The suite's own Chromium is that case,
  so the magnification itself is tested in WebKit and in Chromium without
  hinting.
- Media queries and scripts see the real window. A setup rule cannot use a
  viewport breakpoint above 1440 px, and code that places a box from the
  window's size must convert by the zoom before a setup screen uses it.
- Controls the browser draws itself (a native select's open menu, `title`
  tooltips, scrollbars) may stay at their plain size.

## Alternatives considered

- **Larger tokens or a larger root font size.** Every size in the app would have
  to scale through one variable, and the ones that do not (borders, icon boxes,
  canvas, fixed widths) would drift apart from those that do. It changes the
  design rather than enlarging it.
- **A scale transform.** It enlarges the picture without the layout: the page
  keeps its unscaled size for scrolling and the window's edges, hit testing goes
  through the transform, and text is scaled as an image.
- **Three fixed steps chosen by media query.** Simpler to review, but the
  person's own browser zoom shrinks the window in CSS pixels, so turning it up
  could drop setup a step and make it smaller.
- **A separate large-window layout.** A redesign of every step, with its own
  review at every size, for the same goal.
