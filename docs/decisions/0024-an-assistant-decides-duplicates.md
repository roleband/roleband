# 0024: An assistant decides duplicates, and the person's verdict stands

## Context

The duplicate detector pairs postings that may be one role posted twice, or two
openings for the same kind of role. Every pair it is not sure of waits in the
Review screen for the person, and the pairs it matched on its own wait there
unchecked. Working through them is long and repetitive, and it is the kind of
reading a connected assistant does well from the evidence the engine already
computes: the fields that differ, the days between the postings and the
passages only one of them has.

A verdict changes what the radar shows: a pair marked as one role stacks the
two postings, and the person's changes feed reads from the result. So the
person has to be able to tell which verdicts an assistant gave, read why, and
change any of them.

## Decision

- Two operations: `duplicates.queue` lists the pairs worth a verdict (the
  person's own roles first, then suspected pairs, then automatic matches,
  weakest first), each with its evidence; `duplicates.decide` takes up to 50
  verdicts, each with a one-line reason. It belongs to the `tuning_radar`
  action group.
- A verdict is said in the person's words: `same_opening`, `two_openings`,
  `different_roles` or `unsure`. `unsure` leaves the pair pending for the
  person with the assistant's note; the queue does not list it again.
- `job_lineage_link` and `job_twin_link` record `decided_by` (`person` or
  `agent`) and `decision_note`. A row with no `decided_by` reads as the
  person's, so every verdict made before this keeps its weight.
- An assistant never replaces a verdict the person gave, on the pair itself or
  on a pair the verdict would also change. That pair answers
  `decided_by_person` and the rest of the batch goes ahead. An assistant may
  change its own earlier verdict.
- The Review screen marks the assistant's verdicts with its reason, and shows
  its note on a pair it left for the person. Changing any of them stays in the
  app.

## Consequences

- The batch is one Activity entry naming each pair and its state before and
  after, and it replays under its idempotency key like every write.
- Undoing a verdict restores `decided_by` and `decision_note` with the rest of
  the pair, so an undone assistant verdict reads as it did.
- The projection is rebuilt once per batch, not once per pair.
- The local-model advice in the Review screen and linking two postings by hand
  have no operation: the assistant reads the evidence itself, and a pair the
  detector never proposed is the person's to find.

## Alternatives considered

- **Mirror the screen's controls as operations** (read one pair, analyze it,
  decide it, undo it). More calls for the same outcome, and undo by an
  assistant would let it reverse the person's own correction.
- **Let an assistant only suggest, never decide.** The person would still go
  through every pair, which is the work this saves.
- **Treat an assistant's verdict like the person's.** The person could not
  tell which verdicts to check, and an assistant could overwrite a decision the
  person made on purpose.
