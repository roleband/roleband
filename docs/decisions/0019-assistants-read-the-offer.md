# 0019: The person's offer is a category assistants read

## Context

The offer and the private-company valuations are kept in the local database
([0003](0003-offer-in-local-database.md)). Under
[0017](0017-agent-access-open-by-default.md) the offer is one of the five data
categories, shared with the person's assistant once agent access is on, and the
`offer.get` operation serves it. So where the offer goes depends on whether the
person connected an assistant and shares the category.

## Decision

- An assistant with agent access on reads the offer and the valuations through
  `offer.get`, as the Stock tab's offer route reads them. They stay in
  `app_settings`, no usage event counts them, and no RoleBand server receives
  them.
- The person can keep the offer from assistants with its category choice,
  stored in the `agent_access` row (`categories.offer`). Not shared, `offer.get`
  is refused as `category_disabled`, and the refusal carries none of the offer.
- Text that says where the offer goes says that it stays in the local database
  and reaches only the assistant the person connected, unless they keep it back.

## Consequences

- What an assistant does with an offer it read is outside RoleBand's control, as
  for every category (0017).
- `tests/test_agent_offer_export_reads.py` holds `offer.get` to the offer route
  and holds an offer that is not shared to a refusal with none of its figures.
- 0003's storage decision governs where the offer is kept.

## Alternatives considered

- **Keep the offer from agents for good.** Breaks the offer and negotiation help
  the people who turn agent access on want, and guards a choice that is theirs.
- **Off until the person opts in.** Rejected for every category in 0017.
