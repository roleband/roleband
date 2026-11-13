# 0017: Agent access is open by default, with a switch per category and action

## Context

Two switches gate assistant apps today, both off until the person turns them
on: `enabled` for reads and `allow_writes` for writes, in the `agent_access`
row of `app_settings` (`AgentAccessConfig` in `tracker/agents/config.py`). Most
people who turn them on want the help, and many already give their CV to a
cloud model. A few want to keep some of their data, or some kinds of action,
away from an agent, or within models that run on their own computer.

Only the two switches exist today. The categories and action groups below are
built with the agent operations that read and write them, and
`docs/architecture.md` describes them in that change.

## Decision

Turning on the connection is the one consent. From then on everything is
open, and the person switches off what they do not want.

- **Data categories**, each shared with any model when `enabled` is on: public
  postings, market statistics, the person's pursuits and notes, their offer,
  and their candidate profile. Per category the person chooses **any model**,
  **local models only**, or **not shared**.
- **Action groups**, each on when `allow_writes` is on: tracking progress,
  keeping findings, tuning the radar, and controlling collection. Per group
  the person chooses **on**, **ask first**, or **off**.
- These choices are stored in the `agent_access` row beside the two switches,
  are changed only in the app, and need no per-client credential. A row that
  has no choice for a category or a group reads as open.
- The two switches stay the masters: with `enabled` off no category is
  served, and with `allow_writes` off no action group acts, whatever each is
  set to.
- **Local models only** is enforced where RoleBand calls the model itself. An
  assistant outside RoleBand treats such a category as not shared, because
  RoleBand cannot see where that assistant sends what it reads.
- A category switched off is absent from every view of every operation, not
  masked. An action set to ask first is held until the person approves it in
  the app. Every action an agent takes is listed in the app and can be undone.

## Consequences

- The enablement screen lists every category and group, switched on; nothing
  else asks the person again.
- An operation declares the categories it reads and the action group it
  belongs to, so the engine can refuse it from the stored choices, and a test
  can fail when an operation declares neither.
- A malformed `agent_access` row reads as everything off, as today, so a bad
  write never opens access.
- What an outside assistant does with data it was given is outside RoleBand's
  control; the enablement screen says so once.
- Wording that promises a category never leaves the computer changes with the
  operation that first serves that category.

## Alternatives considered

- **Private categories off until the person opts in to each.** Protects the
  few who want it at the cost of every person who turned the connection on to
  get help, and turns one consent into several.
- **An approval prompt before every write.** Interrupts every ordinary action
  and trains people to approve without reading; a listed, undoable entry gives
  the same control after the fact, and ask first remains for those who want it.
- **Choices per assistant from the start.** Needs a credential per assistant
  that the macOS engine does not have yet; the per-category choices do not
  wait for it.
