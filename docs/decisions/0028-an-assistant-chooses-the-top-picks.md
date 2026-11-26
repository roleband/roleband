# 0028: An assistant chooses the top picks, and the person's hard rules stand

## Context

Top picks is for a person who wants to hear only of the roles worth leaving
their job for. The Radar's filters and its fit ranking order every open role,
but neither can say whether a role beats the job the person holds: that takes
reading the posting against what the person has, wants and reacts to. A
frontier model does that reading well, and the person already runs one as
their assistant, connected through the `roleband` command
([0015](0015-agents-use-the-cli.md)).

Some of what the person asks for is a field the engine already holds: stated
pay, a placed level, the places, the work mode, the company. The rest only
reading can judge. The assistant reads on a schedule, with no person present,
so what it may change on its own has to be fixed in advance.

## Decision

- **The engine decides what code can decide; the assistant judges the rest.**
  The queue of postings to judge is a query, never stored
  (`tracker/picks/queue.py`): the Board's open, visible roles, one posting per
  duplicate stack, less those whose current text already has a verdict that
  stands, less those a checkable hard rule rules out, best fit first. Fit
  orders the work and never cuts it. Roles open before Top picks was turned on
  are read too, a day's limit at a time.
- **A hard rule is checkable or judged.** The engine applies a checkable rule
  before any model reads the posting, and only on a field the posting has (a
  stated pay band, a placed level, a place, a work mode, the company), never
  on estimated pay: a posting without the field goes to the judge. Any other rule is judged by reading. The forms and how each is read
  are in [architecture.md](../architecture.md#top-picks).
- **A verdict has a form the engine holds it to.** A pick has two to four
  reasons and is never weaker than what the person holds; a near miss has the
  one reason it failed; a pass has a code. A reason is one sentence of plain
  text, its opening fact apart from the rest, naming the item of the brief it
  rests on. A verdict out of form is refused alone; the rest of its batch is
  saved.
- **The person's rules are the person's.** A write made in a routine run (one
  that names its run) changes only what the routine learns from reactions: the
  pulls, the trade-offs, the examples and the rules it proposes. Every other
  part (the hard rules, the baseline, the targets, the direction, the budget
  among them), the summary and making a draft the active brief answer
  `needs_the_person`. The routine proposes a rule; only the person makes it
  one.
- **The person's reaction is the last word.** Not for me on a pick removes it
  from Top picks and from the Radar. The reason the person gives, a code or
  their own words, is what the assistant reads back (`picks.list` with
  `removed`). Clearing the mark puts the pick back in both.

## Consequences

- No posting the Board hides is ever judged, so a pick is never better than
  the scan behind it. A model reads only what the rules leave.
- Silence is explained: Passed over lists the near misses, the passes by why,
  and how many roles each hard rule ruled out before any reading
  (`GET /api/picks/passed`).
- The engine cannot tell whether a person is present. The routine's limits hold
  the routine to its contract and are no security boundary: an assistant in a
  conversation with the person writes as the person.
- Health is read from the stored runs, so the app can say when the routine is
  late or stopped without asking the assistant.
- `backend/tests/test_picks_engine.py` holds the rules, the queue and the
  routine's refusals; `backend/tests/test_agent_picks_db.py` holds the
  verdicts' forms, Not for me and Passed over through the operations and
  routes.

## Alternatives considered

- **A fit threshold with no model.** Keep the roles above a fit score. Fit
  measures how close a posting's text sits to what the person said and saved;
  it cannot compare a role with the job they hold or say why a role is worth a
  move, and a role whose text says little would fall below the line. Fit
  orders the queue instead.
- **A model that only suggests.** The assistant proposes and the person
  confirms each pick. The person would read every suggestion, which is the
  work Top picks saves, and nothing would arrive while they are away. A pick
  arrives with its reasons instead, and Not for me takes it back.
