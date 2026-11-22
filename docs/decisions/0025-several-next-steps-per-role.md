# 0025: A role holds several next steps

## Context

A pursuit held one next step: one text (`pursuits.next_action`) and one day
(`next_action_due`). A person working a role often owes more than one thing at
once (send the portfolio, ask a contact about the team, follow up with the
recruiter), each with its own day, and one field made them write a list into a
sentence or forget all but one. The board card, the List, the filters, Up next,
its month, the overdue reminders, the agents' change feed and the CLI all read
that one field.

## Decision

- A pursuit's next steps are rows of `pursuit_steps`: words, a day or none,
  when it was added, and when it was ticked done. They are listed soonest first,
  steps with no day last in the order added; there is no manual order.
- A ticked step leaves the open list and is kept, with its time, so History
  names it and Undo opens it again. The role's page lists the done steps,
  latest first, folded under the open ones: a done step opens again from its
  tick, and Delete takes it off for good. Remove deletes an open step outright,
  for one added by mistake. Deleting is the person's alone, in the app, as
  deleting an interview is.
- `pursuits.next_action` and `next_action_due` stay for one release as a mirror
  of the soonest open step, written only by the server in the same transaction
  as the step write. A write that still sends them changes the soonest open step,
  adds one when there is none, and ticks it done when its words are cleared.
- Every step write is one `pursuit_events` row whose detail names the step and
  what was done to it (added, edited, done, reopened, removed), and it moves the
  pursuit's revision like any other write.
- Reminders and the change feed's due events are per open step: an overdue step
  is one notification with its own words, and a step's due event has the step's
  own identity.
- Agents read `steps` in `pursuits.get`, `applications.board` and
  `applications.calendar`, and write with `steps.add`, `steps.edit`,
  `steps.done` and `steps.undo`, each against the pursuit's revision.
- The board card and the List show the soonest open step only, with no count of
  the rest. Up next and its month give every dated step its own row.

## Consequences

- The filters keep their rules through the mirror: overdue, due this week and
  needs a next step read the soonest open step, which is overdue exactly when any
  step is.
- Removing the mirror columns is a later migration, and it removes columns, so
  it waits for the owner's go. Until then every reader of the old fields keeps
  working.
- Done steps are listed by the role's page alone; no agent read lists them, and
  History names each one's writes.

## Alternatives considered

- **Keep one step and let the person write a list into it.** No day per item,
  no tick per item, and one reminder for all of them.
- **Steps as a JSON list on the pursuit.** No identity for a reminder, a due
  event or an undo to point at, and every write rewrites the whole list.
- **Delete a step when it is ticked.** History could not name what was done,
  and Undo would have to rebuild the step from the toast.
- **Drop the old columns in the same release.** Every reader would have to move
  at once, the installed app's included, with no release in which both work.
