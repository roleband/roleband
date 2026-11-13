# 0014: A posting steps up by width

## Context

A posting is the app's long read, and people read many of them in a row. At the
design's 1440 px it fills the window; a wider window leaves margins empty and
the text small. Growing the description's type alone changes the composition:
the prose outweighs the pay panel, the headings and the side column.

A posting is not a short fixed screen like first-run setup
([0001](0001-setup-magnification.md)). It opens over a list that stays mounted,
under a bar that every cover shares, and it opens menus, pop-ups, dialogs and
toasts, keeps a side column and its section headings in view, and moves the pay
panel's small copy as it scrolls.

## Decision

Job detail steps up at set widths of its own scroll box
([docs/ui.md](../ui.md#cover)):

- Each step widens the frame and its gaps and sets the posting's type one size
  up, together, by restating the type tokens on `.jd-container`.
- The main column stays about 40 ems of the reading size, and the description
  fills it.
- The steps are container queries on the posting's scroll box, so they follow
  the posting's room and add no window breakpoint. They read the width alone,
  never the height.
- The bar, and the menus, pop-ups and dialogs the posting opens, keep their size
  at every step.

## Consequences

- Nothing is zoomed: boxes read from the page and lengths set on an element are
  in the same pixels, so pop-ups, the company card, sticky parts and the pay
  dock need no conversion, and 1 px lines stay 1 px.
- A window of a given width draws the same posting at any height.
- Each step is a design that is reviewed at its own size;
  `tests/ux/job-detail-steps.spec.ts` holds the frame, the columns, the type,
  the bar and the menus at every step.
- Text inside the posting that sets a literal size rather than a type token
  does not step.
- Turning up the browser's own zoom narrows the box and can drop the posting a
  step, as on any page that steps by width.

## Alternatives considered

- **CSS `zoom` on the posting, by setup's factor.** The design, larger, by
  construction; but the factor follows the window's height, so a wide short
  window drew a narrower page than a tall one; the bar, every portalled
  surface and every positioned pop-up needed an exemption or a conversion; a
  zoom at a fractional factor drew uneven hairlines; and the posting could not
  magnify in browsers that round text to whole pixels.
- **A larger type size for the description only.** Fixes the letters and breaks
  the composition.
- **A wider frame with the same type.** Uses the room, but a line of prose grows
  past the length a reader tracks comfortably.
- **Window breakpoints.** The same steps, but a new window breakpoint, which the
  closed set in `design/breakpoints.test.ts` refuses, for a decision that is the
  posting's room, not the window's.
