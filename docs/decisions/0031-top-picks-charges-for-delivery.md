# 0031. Top picks charges for delivery

An assistant can stop after one page of a run. Charging the whole queue at
begin can exhaust the day even though most of that queue stayed in the engine.
Charging on judgment would let a caller read through its allowance by
withholding verdicts.

Record the first committed handoff in `pick_delivery`, with the run and job
as its identity and the engine's local date as its day. The queue holds order
and content hashes. It can be interrupted without holding any capacity open.
The picks transaction lock covers both the allowance check and the insert.
This also orders delivery against changes to the cap or mode.

Paging is a POST with natural idempotency. Its reply is made from current
eligibility and capacity, and a retry can reuse a recorded delivery. A cached
page could return a posting that no longer belongs in the batch. Begin keeps
its keyed receipt so a retry can identify the original run.

Older queues cannot establish which postings were served. Keep their prior
charge and verdict admission, and leave the history intact when upgrading.
The operational rules are in [Top picks](../architecture.md#top-picks).
