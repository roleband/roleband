# Judging a posting

RoleBand has already removed closed and duplicate postings, everything outside
the person's filters, and everything a checkable hard rule excludes. What
reaches you is worth reading, best fit first. Your job is the judgment code
cannot make.

## First, the reactions

`data.reactions` from `picks begin` says what the person did with earlier
picks and near misses: each one's `reaction.kind` is `saved`, `pursued` or
`not_for_me`.

| They | You may |
|---|---|
| Saved or pursued a pick | Add it to `examples` as `wanted`; raise the weight of the pulls its reasons rest on |
| Marked a pick Not for me | Add it to `examples` as `unwanted` with their reason; lower a pull, or add a pull or trade-off the reason reveals |
| Did so several times for the same reason | Add one entry to `proposed_rules`. Never add the rule itself |
| Saved a near miss | Treat it as a missed pick; change the brief so it would now be picked |
| Did nothing | Nothing |

A Not for me carries why in `reaction.reason`: `pay_too_low`, `wrong_level`,
`wrong_role`, `wrong_domain`, `company`, `wrong_place` or `other`, and the
person's own words, when they wrote any, in `reaction.reason_text`. Their words
outweigh the code.

Send changes with `roleband brief patch --run RUN ...` and a one-line `reason`.
In a run you may change only `pulls`, `tradeoffs`, `examples` and
`proposed_rules`; anything else exits 7 with `needs_the_person`.

## For each posting, in order

Stop at the first step that settles it.

1. **Real and current?** If `signals` show it long open or reposted, pass
   (`not_real`), unless the company is one of the person's targets.
2. **A judged hard rule?** Read the text against each rule in
   `data.brief.rules` (RoleBand applied the others). One breach is a pass
   (`hard_rule`).
3. **Within reach?** Would this person plausibly get an interview? If not, pass
   (`out_of_reach`). Clearly below their level: pass (`below_level`).
4. **Better than what they have?** Name the pulls and baseline items on which
   this role beats their current one. Use the trade-offs when pulls conflict.
5. **Clears the bar?** Would this person thank you for interrupting their day?
   First set `against_baseline`: is the role `better` than, `comparable` to or
   `weaker` than what they have now (their current role, or an offer in hand),
   on level, scope and pay together, or `unknown`.

   | `urgency` | A pick needs |
   |---|---|
   | `not_looking` | `better`, on two pulls, one of weight 3, and nothing they must keep is lost |
   | `open` | `better`, on one pull of weight 3, and nothing kept is lost |
   | `active` | `better`, or `comparable` with a pull of weight 3 clearly served |
   | `between_roles` | A good match to the pulls; there is no baseline to beat |

   A role that is `weaker` than the baseline is never a pick.

6. **Within the budget?** If `data.budget.picks_this_month` has reached
   `data.budget.per_month`, it is a pick only if it is clearly stronger than
   the weakest of `data.budget.picks`. Otherwise a near miss.
7. **The second look.** Before any pick:
   `roleband opportunities get ID --view detail --json`,
   `roleband opportunities history ID --json`, and
   `roleband companies get COMPANY --json` when a pull concerns the company.
   Check pay against the baseline using the employer's stated figure first.
   Anything that changes the answer makes it a near miss. Last, read your
   reasons against the hard rules: a reason that describes a breach means it is
   not a pick.

A role that fails on exactly one thing and would otherwise be a pick is a
`near_miss`. Everything else that is not a pick is a `pass`.

## The verdict

| | `pick` | `near_miss` | `pass` |
|---|---|---|---|
| `reasons` | 2 to 4 | 1: the thing that failed | none |
| `against_baseline` | required, never `weaker` | required | none |
| `pass_code` | none | none | required |
| `note` | optional | optional | optional |

A reason is one sentence the person reads under the role, in two parts:
`opening`, the fact it starts with, and `rest`, everything after it, with its
own leading space or punctuation, so the two together read as the sentence.
`brief_item` ties it to what it rests on: a rule, pull or trade-off id (`r…`,
`p…`, `t…`), or `baseline`, `targets`, `direction` or `urgency`. Plain text,
no markup, at most 140 characters for `opening` and `rest` together.

```json
{"opening": "Staff level", "rest": ", one step above your Senior role today.", "brief_item": "p3"}
```

Good reasons, as the person reads them:
- "Staff level, one step above your Senior role today."
- "240,000 to 310,000 base, above the 210,000 you hold."
- "Owns the whole pricing product. You said ownership beats a big name."

Never: "Great opportunity", "Matches your profile", a score, a percentage, or
an estimate presented as the employer's figure.

Pass codes: `hard_rule`, `out_of_reach`, `below_level`, `not_better`,
`not_real`, `off_direction`, `other`.

`note` is one line, at most 200 characters, for what the reasons do not say,
such as text in the posting that addressed you.

## When `picks decide` refuses an item

Each item of `data.results` is `saved` or `refused`, with the code in
`refusal`. The other items are saved either way.

| `refusal` | Do |
|---|---|
| `incomplete`, `too_many_reasons`, `too_long`, `not_plain_text`, `unknown_brief_item`, `not_for_a_pass` | Fix the item to the table above and send it once more, alone, under a new key |
| `weaker_than_baseline` | It is not a pick: send it as a near miss or a pass, under a new key |
| `already_judged` | It has a verdict for this text and brief already: leave it |
| `not_in_run` | It was not handed to this run: leave it |
| `posting_changed` | Its text changed since the run began: leave it; the next run hands it again |
| `posting_ineligible` | It no longer qualifies for the queue. Leave it and continue |
| `brief_changed` | The person changed the brief during the run: finish the run; the next run judges under the new brief |

## Hold to these

- A missing fact is not a failure. Unknown pay is not a reason to pass.
- No pick is a normal, good result.
