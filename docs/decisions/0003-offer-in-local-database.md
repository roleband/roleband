# 0003: The person's offer is kept in the local database

## Context

The Stock tab takes the person's own job offer and the valuations they give
private companies. These are among the most private figures the app holds: the
usage consent promises that compensation and anything typed are never sent. The
offer is also not only a Stock tab idea: a role's application reaching an offer
will want the same questions and the same figures.

## Decision

The offer and the valuations are kept in the local database, in `app_settings`
(`user_profile/offer.py`), through `/api/profile/offer` and
`/api/profile/offer/valuations/{company}`. The dashboard keeps nothing of them in
browser storage. One offer is kept; valuations are kept per company slug. The
routes are never usage actions.

## Consequences

- The offer survives a cleared browser, a second browser and the app's own
  window, and backups and restores carry it with the rest of the record.
- The API validates every figure on the way in and again on the way out, so a
  row written by another version of the shape reads as nothing rather than as
  wrong figures. `tests/test_api_profile_offer.py` enforces it, and that no
  offer route is counted.
- A company typed in by hand has no slug, so its private valuation cannot be
  kept; its offer asks a price per share instead.
- When the Pipeline takes offers, it decides whether an application's offer is
  this row or one of its own; a table per application would come with a
  migration then.

## Alternatives considered

- **Browser storage.** No server change, but the figures would be lost with
  site data, differ between browsers, and miss backups.
- **A table of its own now.** Room for one offer per application, but a
  migration and a schema landing for a single row the Pipeline has not yet
  shaped.
