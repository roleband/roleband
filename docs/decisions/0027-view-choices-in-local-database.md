# 0027: How the person arranges the screens is kept in the local database

## Context

The person arranges what the screens show: the Workspace's blocks for each
stage, the Board's hidden columns, the List's columns, crossings dismissed on a
role, whether a posting's "More like this" is folded, the Insights view, and
the filters each screen was last left with. That is work they expect to keep.
Kept in browser storage, it was lost when site data was cleared, and the app's
own window and a browser each showed their own.

## Decision

Each of these is a view choice, kept in `app_settings` with one row per choice
(`view_choice.<name>`, `settings_store.VIEW_CHOICES`), through
`GET /api/settings/view-choices` and `PUT /api/settings/view-choices/{name}`.
The store names every choice and checks each one's form: a write that does not
fit is refused, and a stored row that no longer fits is never served. The
dashboard reads them once per page load, before the first render, beside the
company names (`hooks/viewChoicesRead.ts`), and every screen reads its choice
from one store (`hooks/viewChoices.ts`). A change shows at once and is saved in
the background; while one save of a choice is on its way, only the latest
change waits behind it. A choice a browser still holds moves to the database on
the first read that finds none there, then leaves the browser. Saving a view
choice is not a usage action.

The theme stays in the browser: it is drawn before the first paint, and a
person may want it to differ from one screen to another.

## Consequences

- The screens look the same after site data is cleared and in any browser, and
  backups and restores carry how they were arranged.
- One row per choice means each save is a single upsert: two windows saving
  different choices never undo each other.
- What a value means stays with the screen that reads it; the store holds only
  its form and size. `tests/test_view_choices.py` holds the names and forms,
  `viewChoices.test.ts` the reading, saving and the move out of the browser.
- A new choice is a name in `VIEW_CHOICES` and in the dashboard's move table
  if a browser held it before.
- A slow or failed read shows each screen's defaults; a read that arrives late
  arranges what is drawn after it. A change made in the instant before a full
  reload can be lost, since its save had not gone out.

## Alternatives considered

- **Browser storage.** No server change, but the arrangement is lost with site
  data and differs between browsers.
- **A route per screen.** Typed bodies, but every new choice would need a
  route, its schema, its agent and usage bookkeeping, and its own read at
  startup.
- **One row for every choice.** Fewer rows, but each save would read, change
  and write the whole set, and two quick saves could lose one.
