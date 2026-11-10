# 0004: Each Insights element answers a reader's question

## Context

Insights grew a chart for most derived tables, whether or not a reader could act
on what it showed. Two of them answered no question a job seeker asks:

- **Trends** drew each skill's daily share of skill mentions. A share moves by a
  point or two over weeks, and a change in the companies or skills counted moves
  it as much as demand does, so the lines could not tell a reader what to learn
  or where to apply.
- **Clusters** grouped open roles by the words in their descriptions (KMeans
  over embeddings) and named each group by its strongest skills. Groups with
  near-identical names held different roles, a refit could regroup them, and no
  reader decision followed from a group's size.

## Decision

An Insights element stays only if it answers a question a person asks about
their search, and it is judged by that question, not by whether today's numbers
are right:

- A valuable question with a wrong answer is rebuilt.
- A valuable question that needs more history than the radar holds is hidden
  until the history exists.
- An element is removed only when the reader loses nothing, or when its question
  returns, answered properly, somewhere named.

The basic view carries the simple answers; the advanced view carries what needs
an understanding of statistics to read (docs/ui.md, "Insights views").

Trends and Clusters are removed: their tabs, the Overview's largest groups and
its "largest cluster" sentence, `/api/skills/trends`, `/api/clusters` and
`/api/clusters/{id}`, and the clustering post-pass. The daily skill counts
(`skill_demand_daily`) are still written, so a later view that needs weeks of
history starts with them. The stored groups (`clusters`, `jobs.cluster_id`,
`jobs.cluster_distance`) are kept unwritten and unread: they are user data, and
removing them is a separate, explicit step.

## Consequences

- Insights lists eight tabs: four basic, four advanced. A saved link to
  `/statistics/trends` or `/statistics/clusters` opens Overview
  (`StatisticsView.test.tsx`).
- A scan no longer refits the clusters, so it no longer changes or deletes the
  stored groups; scikit-learn stays because the bundle probe imports it.
- `db/ownership.py` records `clusters` as `unpopulated` and `skill_demand_daily`
  as read by its writer alone; `tests/test_table_writers.py` holds both claims.
- The question "which companies hire for roles like mine" is not answered by any
  screen until a similar-companies view is built on skill overlap.

## Alternatives considered

- **Keep Trends and wait for history.** More days would not fix the measure: a
  share of mentions still moves with what is counted, and a skill's rise of a
  point is not a reason to act.
- **Fix the cluster names.** Unique names would not make a group's size mean
  anything to a reader, and a refit could still regroup the roles.
- **Turn the clustering pass off but keep its code.** A refit deletes the groups
  it no longer matches, and with too few embedded roles it deletes every group,
  so the code is a hazard to the kept rows; the table stays and the writer goes.
