---
name: roleband
description: Read and update the person's job search in RoleBand (opportunities, pursuits, recipes, radar) through the `roleband` command. Use when the person asks about roles, companies, pay or applications they track in RoleBand.
---
<!-- roleband skill, version 2. `roleband connect` installed this file; once you edit it, connect leaves it as it is. -->

# RoleBand

`roleband` reaches the RoleBand engine running on this computer. Pass `--json` on every call and start the command with `roleband` itself: a variable set before it (`ROLEBAND_AGENT=1 roleband ...`) makes the host ask the person first. Every call prints exactly one JSON envelope: read `ok` first, then `data`, or `error.code` and `error.message` when `ok` is false.

1. Run `roleband capabilities --json` to see the operations this engine offers and which of them the person has turned on.
2. Before calling an operation, run `roleband describe OPERATION --json` with an id from that list. It gives the input and output schemas, the effects and the setting that controls it.
3. Call an operation by its id as words: `opportunities.search` is `roleband opportunities search`. A field the operation's address names is an argument (`roleband opportunities get 4821`); a plain value or list field is a flag (`level_band` is `--level-band`; repeat a list flag for more values). A nested field, such as the `document` of `recipes validate`, has no flag: give it in one JSON object with `--input @FILE`, or `--input -` reading `echo '{...}' | roleband ...`. Arguments and flags add the fields that object leaves out; a field given both ways fails with exit 2. `--help` after the command lists the flags.
4. A filter value that names nothing fails with exit 2, and `error.next_actions` names the lookup that lists the accepted values, such as `roleband vocabulary list --kind location`. When `meta.next_cursor` is set, pass it as `--cursor` for the next page. When `meta.truncated` is true on `opportunities get`, `data.excerpt.continue_with` lists the calls that read the rest, an operation and its arguments: make them as given (`description_from` is `--description-from`).

## Changing data

1. Read the item first: `roleband pursuits get ID --json`. Pass its `data.revision` as `--if-revision` (0 when the role has no pursuit yet).
2. Pass `--idempotency-key KEY`, a token of your own for this one change, such as `task-17-follow-up` (8 to 128 letters, digits and `_.:-`).
3. A field you leave out stays as it is. A flag sets a value; to clear one, send an explicit null: `echo '{"next_action_due": null}' | roleband pursuits patch 4821 --input - --if-revision 12 --idempotency-key task-17-follow-up --json`.
4. With no answer, or exit 3 or 8, run the same command again once, with the same key: a change that landed answers again with `meta.replayed` true and is never made twice. A new key could make it twice.

The exit status says what to do next:

| Exit | Meaning | Next step |
|---|---|---|
| 0 | Done | Use `data` |
| 2 | The input is wrong, or the operation does not exist | Fix the input; check `roleband capabilities`. `context_required` means no engine is set up for this command: tell the person |
| 3 | No engine answered | Retry a change under its key once; otherwise ask the person to open RoleBand |
| 4 | The person's settings refuse it | Tell the person which setting `error.details` names; do not work around it |
| 5 | Not found | Look the item up again |
| 6 | It changed since you read it | Read it again, then decide |
| 7 | The person has to decide | Show them the proposal |
| 8 | Out of time, or too many calls | Retry once, a change under its key; then tell the person |

Never repeat a change under a new key after a failure, and never reach the engine's database or web routes another way.
