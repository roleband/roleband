---
name: roleband
description: Read and update the person's job search in RoleBand (opportunities, pursuits, recipes, radar) through the `roleband` command. Use when the person asks about roles, companies, pay or applications they track in RoleBand.
---
<!-- roleband skill, version 1. `roleband connect` installed this file; once you edit it, connect leaves it as it is. -->

# RoleBand

`roleband` reaches the RoleBand engine running on this computer. Set `ROLEBAND_AGENT=1`, or pass `--json`, and every call prints exactly one JSON envelope: read `ok` first, then `data`, or `error.code` and `error.message` when `ok` is false.

1. Run `roleband capabilities` to see the operations this engine offers and which of them the person has turned on.
2. Before calling an operation, run `roleband describe OPERATION` with an id from that list. It gives the input and output schemas, the effects and the setting that controls it.
3. Call an operation by its id as words: `opportunities.search` is `roleband opportunities search`. Each input field is a flag (`level_band` is `--level-band`; repeat a list flag for more values), or pass the whole input with `--input @FILE`. `--help` after the command lists them.
4. A filter value that names nothing fails with exit 2, and `error.next_actions` names the lookup that lists the accepted values, such as `roleband vocabulary list --kind location`. When `meta.next_cursor` is set, pass it as `--cursor` for the next page.

The exit status says what to do next:

| Exit | Meaning | Next step |
|---|---|---|
| 0 | Done | Use `data` |
| 2 | The input is wrong, or the operation does not exist | Fix the input; check `roleband capabilities`. `context_required` means no engine is set up for this command: tell the person |
| 3 | No engine answered | Ask the person to open RoleBand |
| 4 | The person's settings refuse it | Tell the person which setting `error.details` names; do not work around it |
| 5 | Not found | Look the item up again |
| 6 | It changed since you read it | Read it again, then decide |
| 7 | The person has to decide | Show them the proposal |

Never repeat a change blindly after a failure, and never reach the engine's database or web routes another way.
