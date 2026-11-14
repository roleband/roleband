---
name: roleband
description: Read and update the person's job search in RoleBand (opportunities, pursuits, recipes, radar) through the `roleband` command. Use when the person asks about roles, companies, pay or applications they track in RoleBand.
---
<!-- roleband skill, version 1. `roleband connect` installed this file; once you edit it, connect leaves it as it is. -->

# RoleBand

`roleband` reaches the RoleBand engine running on this computer. Set `ROLEBAND_AGENT=1`, or pass `--json`, and every call prints exactly one JSON envelope: read `ok` first, then `data`, or `error.code` and `error.message` when `ok` is false.

1. Run `roleband capabilities` to see the operations this engine offers and which of them the person has turned on.
2. Before calling an operation, run `roleband describe OPERATION` (for example `roleband describe opportunities.search`). It gives the input and output schemas, the effects and the setting that controls it.
3. An operation id maps to a command: `opportunities.search` is `roleband opportunities search`.

The exit status says what to do next:

| Exit | Meaning | Next step |
|---|---|---|
| 0 | Done | Use `data` |
| 2 | The input is wrong, or the operation does not exist | Fix the input; check `roleband capabilities` |
| 3 | No engine answered | Ask the person to open RoleBand; `context_required` means no engine is set up for this command |
| 4 | The person's settings refuse it | Tell the person which setting `error.details` names; do not work around it |
| 5 | Not found | Look the item up again |
| 6 | It changed since you read it | Read it again, then decide |
| 7 | The person has to decide | Show them the proposal |

Never repeat a change blindly after a failure, and never reach the engine's database or web routes another way.
