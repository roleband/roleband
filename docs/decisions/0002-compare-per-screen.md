# 0002: Each list screen keeps its own comparison

## Context

Radar and the Pipeline both let the reader pick roles to compare. A pick is a
view choice, like a filter or a sort: it belongs to the list it was made in.
With one selection for the whole app, roles picked in the Pipeline stayed
picked on Radar, where some of them are not even listed, and the count in the
top bar spoke for a list the reader was not looking at.

## Decision

Radar and the Pipeline each keep a comparison of their own. The store holds
one selection per screen (`compare_selection.scope`, `radar` or `pipeline`),
and `GET`/`PUT /api/compare-selection` take `?scope=`, defaulting to `radar`.
A role can be in both. The cap of three holds per screen.

The dashboard serves the selection of the screen on show (`JobWorkspace`),
found by `listScreenOf`: the Pipeline is every page under `/pipeline`, and a
cover (a role, Compare) belongs to the page under it. Every other page, and
Compare reached by its address alone, is Radar's. The top-bar count, the
palette and the margin beacon read that one selection.

Facts about a role stay shared: a star, Not for me and a role marked viewed
read the same on every screen.

## Consequences

- A pick never leaks between screens, and each count says what its own list
  holds. `context/compare-persistence.test.tsx`, `tests/test_api_compare_selection.py`
  and the Pipeline and Radar spec in `tests/ux/applications.spec.ts` enforce it.
- A screen added later chooses: it joins a scope, or the vocabulary grows
  (`COMPARE_SCOPES`, the check constraint, `CompareScope`), with a migration.
- A page outside both lists (Settings, Insights) shows Radar's count.
- A downgrade refuses while the Pipeline holds a comparison, since the earlier
  schema keeps one selection.

## Alternatives considered

- **Keep the Pipeline's picks in the browser.** No migration, but a reload or
  a second browser would lose them while Radar's survive, and the store would
  no longer cascade a deleted role out of both.
- **Clear the selection on leaving a screen.** One list still, but it throws
  away work the reader meant to keep, and Compare opened from a role would
  have nothing to show.
