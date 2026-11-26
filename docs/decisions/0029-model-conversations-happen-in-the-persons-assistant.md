# 0029: A model conversation happens in the person's assistant, not in the app

## Context

Top picks needs two kinds of model work. Setup is a conversation: the model
learns who the person is from their CV or their own words, what they want from
a move and which rules are hard, and checks each with them. After setup, a
model reads new roles on a schedule, with no one present.

The person who wants this already runs a frontier assistant, such as Claude
Code or Codex, under their own sign-in, and that assistant can run the
`roleband` command ([0015](0015-agents-use-the-cli.md)) and keep a scheduled
task of its own. The engine has the parts of a runner, a tool-calling
transport and tools built from the operations
(`tracker/intelligence/tool_calls/`, `tracker/agents/tool_definitions.py`),
but nothing calls them, and its own model backends stay off until the person
turns on AI egress.

## Decision

- **The app has no chat surface.** Every model conversation about the
  person's search happens in the assistant the person runs, which reads and
  writes through the `roleband` command. The app shows the results and the
  state: the Top picks screen and its notes, Passed over, and the rail's dot.
- **Nothing lives in a chat.** The reading of the person's background, the
  brief and its versions, the runs and the verdicts are kept by the engine, so
  any conversation, any assistant and any day continues from the same state.
  `picks.status` says where setup stands and what it has saved.
- **The scheduled check is the assistant's own task**, run under the person's
  sign-in. The engine starts no assistant and calls no model for Top picks;
  `picks.switch` records which assistant runs the check and when.
- **The person's switches stay in the app.** Pausing the checks, the daily
  limit and Remove are routes the app calls (`PUT /api/picks/mode`,
  `DELETE /api/picks/setup`). The assistant can pause, resume and change the
  limit through `picks.switch`; no operation of the assistant's deletes the
  stored CV, its reading or the brief.

## Consequences

- The engine holds no model key for Top picks and sends nothing to a model
  provider. What an assistant reads goes where that assistant sends it,
  within the categories the person shares
  ([0017](0017-agent-access-open-by-default.md)).
- Top picks needs a connected assistant that can run the command unattended.
  The app reads the assistant's own files to say whether it can
  (`routine_host_connection` in `GET /api/picks/state`), and the screen says so
  when the assistant asks before each command or is no longer connected.
- A person with no such assistant cannot use Top picks.
- How an assistant runs setup and the checks is the assistant's to follow; the
  engine holds every write to its form, whichever conversation sends it.

## Alternatives considered

- **A chat panel in the app.** The engine would hold a model key or relay a
  model, a second copy of the assistant the person already uses, with its own
  context, tools and limits, and the person would have two places to talk
  about one search. It also leaves the scheduled check unsolved: a panel runs
  only while it is open.
- **A built-in runner first.** The engine would loop a model over the
  operations, with a cloud key the person pays for by the call or a model on
  their computer. A cloud key is a second account and bill beside the
  assistant they already sign in to, and a model that cannot do the whole
  judgment is not offered. A runner would call the same operations, so it can
  come later without changing them.
