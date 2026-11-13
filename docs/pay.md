# Pay

How RoleBand turns a posting plus its own dataset into base, bonus, equity and
total figures, what each figure means, and where each rule and seed lives.
Paths are under `backend/tracker/` unless written in full. Who writes each pay
column, and what clears it, is in [field-authority.md](field-authority.md). A
plugin can supply per-level pay instead of RoleBand's dataset; how a plugin
publishes rows is in [plugins.md](plugins.md).

## Three layers

| Layer | Stored in | Built by | Meaning |
|---|---|---|---|
| Stated pay | `jobs.disclosed_*` | connectors, the text pass, the posting page | The band the posting itself states. A fact about this posting. |
| Estimate | `job_comp_estimate` (one row per source), copied to `jobs.comp_*` | `enrich/comp.py` | What this company pays at this level and family. Never a fact about this posting. |
| Package | not stored; built per request | `analytics/comp_package.build_job_package`, called by `api/routers/jobs.py` | Base, bonus, equity and total for the job detail, each marked `stated` or `estimated`. |

A component is `stated` only when the posting stated it. Everything else is
`estimated`, and the package says which estimator produced it.

## Reading stated pay

All of this lives in `pay_disclosure.py`, `pay_period.py` and `pay_numbers.py`,
and only reports what the posting literally says.

- **Basis** (`base`, `total`, `unclear`): `derive_pay_basis` reads the window
  `basis_context` returns around the band: its paragraph plus a pad each
  side, capped in length. Every writer then passes the basis through
  `settle_band`: an `unclear` band becomes base or total when the posting
  defines its bands per kind of role (sales reads total), or base when its
  paragraph calls the band a salary. Last, a band whose pay country is the US
  or Canada (`BASE_BY_CONVENTION_COUNTRIES`,
  [0005](decisions/0005-unmarked-range-is-base-pay.md)) is base when the role does not sell
  (`taxonomy/roles.sells` is false): a posting there conventionally prints its
  base salary as the one figure under a bare label. It stays `unclear` when the posting describes an employee
  election, or its paragraph says the range includes more or calls it total,
  cash or on-target pay. An explicit statement that this position's
  annual salary range is displayed below may cross the benefits paragraph to
  one labelled pay range; multiple ranges, conditional definitions and inclusive
  compensation wording leave that reference unresolved.
- **Period** (`year`, `month`, `hour`, `unclear`): size decides first, words
  second, and only words next to the amount count (`decide_period`). In US
  dollars a yearly amount sits in 10,000..5,000,000, monthly in 1,000..30,000,
  hourly in 7..1,000; other currencies are sized through
  `pay_numbers.USD_PER_UNIT`, never converted for display. A word that
  contradicts the size gives `unclear`: shown with no unit, never split, never
  counted. Every reader of a stored period goes through `effective_period`.
- **Bounds**: a band is two amounts in one currency, and its code or symbol
  may sit on either amount or both ("USD $160,200.00 - USD $425,000.00").
  A k written once on the high amount scales a bare low under a thousand
  ("$245-$280K"); a band may name its bounds minimum and maximum ("Salary
  Min: $120,000  Salary Max: $160,000").
  Two currencies are two figures, never one band. An amount with a broken
  comma group ("$290,00", "$215,0000") is a typo and bounds nothing, so the
  next stated band is read instead.
- **Several bands, one per place**: `extract_grounded_band` takes the band
  whose label names the posting's first city or metro (`enrich/classify.first_place`)
  when exactly one does, else the first stated. A connector knows no place, so a reader
  that scans a shared source's prose for every tenant (`detail/eightfold.one_band`)
  states a band only when the posting prints one range, and leaves a posting
  with a range per place to the text pass.
- **Bonus percentage**: `derive_bonus_pct` reads "+ 25% bonus target" and
  similar around the band, only when the basis is `base`, and drops anything
  above 60%. Writers read it in `settle_band`, after the basis is settled, so a
  band only its salary wording makes base keeps the target its paragraph
  states. A connector's own read of its pay block stands over the stored
  text's.
- **Pay section**: `connectors/detail/base.promote_section` carves the pay
  sentence into its own section and grows the cut to sentence bounds, so the
  body never holds half a statement.
- Changing how a band is read means bumping `PAY_PARSER_VERSION`; the text
  pass then re-reads the bands it wrote, a capped number per run. Where the
  posting did not change since its last read, a band that re-read changes is
  rewritten without a `changed` event: the reader moved, not the posting, so no
  saved role is told its pay moved. A posting whose text or first place also
  changed records the event as usual.

**Who may write a band.** Three sources state one, and `correct_pay_periods`
corrects one; `db/pay_band.py` holds the rule all of them apply.

- **Precedence.** A band has one owner, `jobs.disclosed_source`. A writer
  replaces a band its own source owns, or one a weaker source owns. Strongest
  first: a structured field on the listing, then the posting's text, then its
  page, which is read only while the text states no pay and so fills that gap.
  The full rule is in [field-authority.md](field-authority.md#4-pay).
- **Clearing.** A writer clears only a band it owns, and only when its source
  can say there is no pay. A connector that scans the posting's text where its
  source prints pay (`pay_from_text` in `connectors/detail/`) clears its own
  band when a complete read with text finds none there. A connector that reads
  a structured salary field (Ashby, OpenAI) never clears: a posting with no pay
  field and one whose employer withdrew a band both arrive as no field at all.
- **The place key.** Every writer records the place it chose the band for, so
  a posting that moves city is owed a fresh read though its text never moved.
- **The stamp.** Every writer records when it wrote and which reader produced
  the figure, and never another reader's version. A correction moves the
  stamp and keeps the source: it corrects what that source stated.
- **History.** Each of the three sources records `disclosed_base` when it
  moves the stated figures, so the same move is visible wherever it was
  published. A correction records nothing: it fixes our reading, not the
  posting. Where a move is shown is in [field-authority.md](field-authority.md#4-pay).

## The estimate

`enrich/comp.CompResolver` asks its providers in order. The first answer is the
headline; every answer is kept in `comp_sources` for the job detail. No band
below Senior gets an estimate, because no reference data starts lower. Nor does
a level we cannot place (`level_basis` `none` or `unmapped`,
`schema.UNPLACED_BASES`): its band is a guess kept for sorting, so no source
prices it, ours or a plugin's. The pay the posting states still shows.

Each provider answers a `CompEstimate`: a total (`median`, `low`, `high`), a
base range (`base_median`, `base_low`, `base_high`), or both. A missing part is
unknown, never zero.

### RoleBand's own estimate

Built in `plugins/reestimate.SourceInputs.resolver`, in this order:

| Order | Provider | Reads | Range |
|---|---|---|---|
| 1 | `comp_providers/table.ReferenceTableProvider` | Stored per-level rows from RoleBand's own sources, keyed by company, the job's family and band; a family with no row reads `REFERENCE_FAMILY` | median ±15% |
| 2 | `comp_providers/static.StaticCompProvider` | The seed on the rung the band reads (`levels/pay.seed_range`, `seed_median_usd` in `levels/atlas/rungs.csv`) | median ±20% |
| 3 | `enrich/builtin_pay.BuiltinPayProvider` | Our dataset's per-level base | base ±15%, no total |

The built-in provider is on by default; `ROLEBAND_BUILTIN_PAY=false` turns it
off (`config.Settings.builtin_pay_enabled`). Its base comes from
`enrich/level_pay.level_bases`, one figure per company, family and band, from
one kind of evidence, never mixed:

1. **filed**: government wage filings (`levels/atlas/title_pay.csv`). The
   filed title goes through the same `classify_family` and `read_level` a
   posting does, at use time.
2. **posted**: ranges the company posts at a known rung or band
   (`pay_grades.csv`, `pay_bands.csv`, `posted_pay.csv`).
3. **estimated**: collected aggregate points (`estimated_pay.csv`), placed on a
   rung by the atlas alone (`enrich/estimated_pay.py`).

A filed or posted base wins; a collected aggregate fills the keys left. No
fallback to another family, year or parent company: a key with no evidence is
absent. The published `level_base.csv` contains company, family, band, base and
stock amounts only; the company API adds policy-based bonus and a total only
where all components are known. It carries no source labels, original-rung
references, collection dates or evidence counts.

The company baseline calls these values **Estimated**: they describe a level,
not the salary stated for a particular posting. A posted midpoint is calculated,
while its underlying range is employer-stated. Job detail keeps the distinction
between a posting's stated components and estimated ones. The vocabulary for
collected base, bonus and equity is Estimated throughout the application.

`enrich/builtin_pay.build_rows` adds a bonus row only where the company policy
answers one (a target, or 0 at a company that pays none) and no equity row,
so this provider answers a base and never a total. Its rows contain values and
matching keys without traceability metadata, and are cached on disk by a
fingerprint of `BUILD_SOURCES`.

A stored rung answers the components it states (`comp_providers/table.py`):
a total and a base, or a base alone, which is a base estimate with the total
unknown. Components are never added up into a total. Within one source the
widest answer leads (`enrich/comp.CompResolver`): a base-only answer stands
only when nothing else in that source answers the total, so a plugin that
publishes base pay alone moves the base estimate, and ours keeps the seed's
total beside a stored base.

### A plugin's estimate

While a plugin is selected for `pay.levels`, a second resolver reads that
plugin's rows and nothing else. Every job keeps both estimates in
`job_comp_estimate`; `jobs.comp_*` is a copy of the selected source's, which
every list, sort and filter reads. Neither source fills a gap in the other: a
company the plugin has not read has no plugin estimate, and the job detail
says it is not covered.

### Re-estimating

An estimate is a function of the job's stored fields and the reference set.
`plugins/reestimate.py` hashes that set (the estimate's code and atlas files in
`ESTIMATE_SOURCES`, the provider record, and the exact rows read). When the
hash moves, every job is re-estimated in batches, and the switch lands in one
transaction with one `reference_change` record instead of a per-job event. If
you make the estimate read a new file, add it to `ESTIMATE_SOURCES`
(`tests/test_reestimate.py` checks each path exists, and follows the estimate's
imports into `tracker.levels` and `tracker.comp_providers` so a module it reads
cannot be left out).

The hash never covers a job's own fields (company, band and its basis, family,
place, title).
Code that moves them outside a scan calls `reestimate.refresh_jobs(ids)`: the
levels backfill, the role reclassify (pass and script) and a held row's fresh
read do. It re-estimates those jobs under the set that applies: settled, their
rows and the list's copy; mid-switch, the jobs the move has already passed (the
move reaches the rest); if the set itself moved, nothing, since the re-estimate
that follows recomputes every job. A new writer of those fields must call it too.

### Which rung a band reads

A band is coarser than a ladder (Microsoft's 65, 66 and 67 are all
`principal`). `levels/ladder.rung_for_band` picks the rung a band reads its pay
from: inside the band, the lowest rung with seed pay, else the lowest; a band
the company has no rung in reads the nearest rung below. `levels/pay.pay_label`
names that rung's lookup label. `comp_package.choose_rung_row` prefers the
stored row that names that rung, by its label or any alias against any
spelling the atlas holds for the rung (its lookup label, code or aliases), so
two sources that spell one rung differently read the same row; else the
median candidate by base, never row order.
The estimate (`pay_level_index`) and the package (`select_baselines`) both go
through it, so the median beside the package is read from the same row.

**Every figure is for one country, and prices postings in that country only.**
A posting's pay country is the one country every place it names lies in
(`taxonomy/locations.pay_country`): a posting naming places in two countries,
or none, has no pay country and shows no estimate and no measured split. Our
own data (the dataset, the seed pay and our stored rows) is US pay
(`comp_providers/base.OUR_PAY_COUNTRY`), so it answers US postings only. A
plugin's rung is for the `country` it states; one that states none prices no
posting. Readers match a row to the posting by country (`pay_level_index`,
`package_rows`, `comp_package.country_rows`); the company page and the
estimate panels on Insights show US rows. Posted pay on Insights is read per
country instead ([Posted pay on Insights](#posted-pay-on-insights)).

Of the US rows, only those that can stand for US pay are read
(`analytics/comp_market.us_rows`), by the estimate, the package, the company
page and the Insights estimate panels alike. A row that states its country is US pay exactly
when it states the US. A row that states none (ours, read for the US) is held
to the floor: a median base under $45,000 is set aside, and so is every such
row of a company and family whose priced rows are at least half under it.
Interns are exempt. Another country's rows are not held to the US floor.

## The package, component by component

`build_job_package` looks up the measured split for the job: the stored row at
company, family and band whose base, bonus and stock are all known
(`is_split`; a measured 0 is a value). The job's own family gives
`split_source = measured`; otherwise it borrows another family at the same
band in `taxonomy/comp_families.BORROW_ORDER` order (`cross_family`); with no
row it falls back to `heuristic`. A measured or borrowed split carries the row's
`provider` and `as_of` as `split_provider` and `split_as_of`, and Job detail
names them under the split ("Split from Levels, as of Oct 1").

### When the posting states a yearly base band

| Component | Estimator, first that applies | Provenance |
|---|---|---|
| Base | The stated band | `stated` |
| Bonus | 1. the posting's stated percentage × base; 2. the row's bonus/base ratio × base; 3. the company policy's target midpoint (`levels/pay.bonus_ratio_for`); 4. the heuristic's flat share (`analytics/comp_split.BONUS_PCT`) | `stated` for 1, else `estimated` |
| Equity | 1. the row's annualised grant (`stock_usd`) as a point, widened to 0.60..1.40 (`_EQUITY_SPREAD_LOW/HIGH`), `equity_basis = measured_grant`; 2. otherwise a share of the stated base from the heuristic, `equity_basis = ratio` ([The heuristic split](#the-heuristic-split)) | `estimated` |
| Total | The sum of the segments shown | `estimated` |

Bonus is a ratio of base because companies set it that way: a level-set target
percentage. Equity is a dollar grant sized by level from its own budget, so it
is never scaled off the two ends of a base band; doing that would turn a band's
geographic spread into an equity spread. The package shows annualised equity
(per year, vesting over time), not year-1 cash.

A segment that comes to zero (a company that pays no bonus, or grants no stock)
is left out rather than drawn as an empty sliver. The total is always the sum
of the segments the user sees.

### When the posting states no band

With an estimated total, the total is split by the same ratios (row, then
policy bonus, then heuristic) and every segment, including base, is
`estimated`, with `equity_basis = ratio`. A company whose people pick their own
cash and equity mix is not split (`employee_election`): the estimate stands
whole. With only an estimated base (the
built-in provider), the package shows one estimated base segment and no total:
bonus and equity are unknown, not zero.

### The heuristic split

With no measured split, the package reads shares that are the same for every
company (`analytics/comp_split.heuristic_ratios`): equity is a share of the
year's total pay that rises with the level, from none for an internship to the
largest share at Director+, and every level names its own share, so no
early-career role reads more stock than a senior one. The bonus is the company's stated
rule or else a flat share of the total, and base is the rest. Whatever the
bonus, equity stays the level's share of the total: a company that pays no
bonus does not get a larger equity share for it. A company's own facts enter
only as stated rules: its bonus rule, and an equity rule of `none`, which
draws no equity segment. No company has an equity multiplier of its own; a
company whose figures need one needs measured rows instead. Every figure built
this way is `estimated`, and nothing checks the shares against stated pay.

### When a band is not split

`no_split_reason` says why the stated figure is shown whole. A yearly base the
posting states is still the bar's one stated segment, with no bonus, equity or
total beside it ([0006](decisions/0006-stated-base-without-a-level.md)): the
reasons below are about the parts RoleBand models, not about the employer's own
figure. The three that would draw a figure as something it is not, an unclear
basis, a period that is not a year and a stated total, draw no segment.

| Reason | When |
|---|---|
| `hourly`, `monthly`, `period_unclear` | The period is not a year. RoleBand never annualises. |
| `basis_unclear` | The posting did not say what the band covers, and no rule settles it (outside the US and Canada, a selling role, or a range called total or cash pay). Splitting it would assume base. |
| `total_compensation` | The band is total pay; it is the headline, `stated`. |
| `employee_election` | The company states that each person picks the cash and equity mix: `equity_rule = employee_election` or `equity_vehicle = cash_election` in the atlas (Netflix is one). No figure of its is split, whether a stated total, a stated base or an estimated total. |
| `plugin_without_split` | A plugin answers pay and its rows give no split for this level. Our heuristic and policy are our data and never split a plugin's figure. |
| `plugin_not_covered` | A plugin answers pay and has not read this company. |
| `not_us_pay` | RoleBand answers pay and the posting's pay is not US pay: another country, or places in several. Our split is measured on US pay only. |
| `level_unplaced` | The posting names no level, or one we cannot place. Its band is a guess, so no row is read for it: no bonus, equity or total is built on it, and nothing is reconciled against it. A stated yearly base is still shown. |

While a plugin answers pay, the package also omits the offer `policy` line,
which is RoleBand's data.

## The Stock tab

Insights' Stock tab sums the same packages Job detail shows: both build a
role's package through `api/comp_packages.role_package`, from the shown
source's estimate, the band the posting states, the company's rungs for the
posting's country and whether the level is placed. A role therefore reads the
same on both screens (`test_a_role_reads_the_same_package_on_job_detail_and_the_stock_tab`).

`analytics/stock_trajectory.build_comp_trajectory` takes each split package's
parts at the middle of their ranges. A company's row is the median total of its
roles, split by each part's dollar-weighted share, so its parts add up to its
total. Each part says where it comes from:

| Source | Base | Bonus | Equity |
|---|---|---|---|
| `posted` | the posted base range | the posting's stated percentage | |
| `company_rule` | | the company's stated bonus rule, none included | the company's equity rule of `none`: "No equity", never 0% |
| `measured` | | a pay row for the company and level | a pay row for the company and level |
| `estimated` | the estimated total, split | the split heuristic | a share of base |
| `mixed` | the company's roles differ | | |

A company whose people pick the cash and equity mix gets a row of its own with
its total and no split, and no price move changes it. One of its roles with no
total, stated or estimated, is counted apart with the rest. Every other role with a
pay figure but no split is counted apart by reason: the package's
`no_split_reason`, `not_us_pay` for any posting whose pay is not US pay (the tab
is in US dollars), `base_only` for a role priced by a base alone (posted or
estimated) with no total, and
`level_unplaced` for an estimate the package built nothing on. A role with no
pay figure is not counted.

The tab's offer calculator works on the person's own figures.
`GET /api/statistics/offer-terms` (`stock_trajectory.build_offer_terms`) gives
it what a company states and nothing else: listed or not and its ticker
(resolved as the table resolves them), its stock type, its vesting schedule
with who states it (a schedule longer than four years is not offered), its bonus
rule and whether its sign-on bridges vesting. A listed company carries the last
quote the prices job stored, in dollars, only while a price key is saved; the
route never asks the feed. In the calculator only equity moves with the slider:
a grant in dollars scales by the move, shares by today's price, options by the
price above their strike and never below zero. A private company's grant
follows the ratio of the valuation the person tests to the one it was priced
at. A schedule summing to 99% (thirds) vests the whole grant; any other sum is
read as typed and shown.

### The offer

The person's offer and their private-company valuations are kept in the local
database, in `app_settings` (`user_profile/offer.py`): one row for the offer, one
for the valuations keyed by company slug, each with the time it was saved.
`GET /api/profile/offer` reads both; `PUT` and `DELETE /api/profile/offer` keep
or forget the offer, and `PUT` and `DELETE /api/profile/offer/valuations/{company}`
one company's valuation. Forgetting the offer keeps the valuations. The API
refuses a figure the shape cannot hold (negative, not finite, a schedule over
100% or longer than four years) and stores nothing; a stored row the current
shape cannot read comes back as nothing, never as other figures. At most
`MAX_VALUATIONS` companies are kept. None of these routes is a usage action
(`api/usage_counter.py` lists them as not counted), so nothing about an offer,
not even that one was saved, leaves the computer. Why the database and not the
browser: `docs/decisions/0003-offer-in-local-database.md`.

## A role list's Base column

The Board and the pipeline's List show one figure per row, of one kind: base
salary. A total is never shown there, because postings state a base and the
built-in estimate answers no total; job detail shows the package.

| The row knows | The cell shows | Its hover, also read to screen readers |
|---|---|---|
| A posted base range (`jobs.disclosed_*`, basis `base`, a period the row can write) | The low end with `+` (`$150K+`), or one figure when both ends read the same; per hour or month with its unit, in the posting's currency, never converted | The posted range |
| Otherwise an estimated base (`jobs.comp_base_median`) | That figure (`$180K`), in its currency | Estimated from the level |
| Neither | Nothing; screen readers hear that it is not known | Why, when a plugin answers pay and has not read the company |

`api/serializers/jobs.posted_base` decides which posted range a row carries
(`pay_disclosure.ROW_PAY_PERIODS`, checked by `pay_period.effective_period`:
a stored period the amount's size rules out shows the estimate instead, and a
band with no stored period reads by its size), and the dashboard's
`payShown.baseShown` writes the cell. The `base_pay` sort and the `base_min`
and `base_max` filters read `db/queries/jobs.base_pay`, the same rule in SQL,
as yearly US dollars: a posted range per hour or month or in another currency,
and an estimate in another currency, are shown but compare with nothing, and a
shown range never falls back to the estimate the row does not show
(`test_api_jobs_sort.py` checks the two agree on every case). Money a search
query names applies as these bounds. The agent tools keep their own estimate filter and sort
(`comp_min`, `comp_median`: the total, else the estimated base).

## Posted pay on Insights

Insights' Compensation tab opens on what employers post, not on the estimate
(`analytics/comp_stats.build_posted_pay`, the `posted` block of
`GET /api/statistics/compensation`).

- **The unit is a distinct range.** A range (company, low, high) at one level
  counts once, however many roles carry it: an employer posts one range per
  level and place and hangs many roles off it.
- **The figure.** A level's typical range runs from the median low to the
  median high of its ranges; its middle half spans the 25th to 75th
  percentile of the ranges' midpoints. A level shows a figure only with at
  least `POSTED_MIN_EMPLOYERS` employers and `POSTED_MIN_RANGES` ranges;
  below that it shows its counts and what a figure needs.
- **One country, one currency.** A role counts for its pay country (above).
  A country's figure is in the currency most of its ranges at a placed level
  use, and its ranges in any other currency are counted apart. Nothing is converted or
  annualised. The tab opens on the US and the person's own levels, and lists
  each of the person's countries even with no range, so the screen can say
  so.
- **What is read.** Yearly base pay only. Each role left out is counted
  under its reason in `excluded`: a range that is total compensation or
  unclear (`not_base`), per hour or month or of a size its period rules out
  (`not_yearly`, `pay_period.effective_period`), a placeholder that is no pay
  at any size, such as $1 to $2 (`implausible`), no pay country (`no_country`),
  or a level read from the range itself (`placed_by_pay`, `LevelBasis.PAY_GRADE`:
  counting it would describe pay by pay). A low salary is still a salary: no
  floor above the size classes applies. `excluded` counts across all
  countries; each country's own `excluded` counts its roles only, so the note
  under a country's heading never counts another's. Every role left out that
  names several countries or none, whatever its reason, is counted again in
  `without_country`, which each country's note says, as no country holds it. A role whose level we
  cannot place is counted apart in `not_placed`, never inside a level.
- **The estimate stays apart.** The estimate panels (by level, company and
  discipline, and the base-only estimates) read only roles whose pay country
  is the US and whose estimate is in US dollars, and are labelled as
  estimates of US pay. Base pay and an estimated total never share an
  axis.

## Checks beside the headline

Both checks say an input (the level or the family) is probably wrong, never
that the employer pays unusually. Neither rewrites `split_source`.

| Field | Question | Fires |
|---|---|---|
| `reconciliation` | Does the stated band's top match the measured base for this level? Only for a USD yearly base band against an exact-family row. | ratio above 1.50 (`stated_above_measured`) or below 0.75 (`stated_below_measured`) |
| `market_gap` | Does the package total match the estimate's median? USD only. | `abs(ratio - 1) > 0.50` (`diverges`) |

The thresholds sit outside the ordinary spread on purpose: a range that spans
locations and adjacent levels has a top well above a median, and the package
total and a median total disagree by a wide margin as normal statistics.

## Company offer policy

`levels/pay.PAY_POLICIES` loads one `levels/model.PayPolicy` per company from
`levels/atlas/company_facts.csv` (one fact per row, with who states it:
`employer` or `estimated`).

| Fact | Values |
|---|---|
| `bonus_rule` | `pct_of_base`, `none`, `unverified` |
| `equity_rule` | `dollar_grant_by_level`, `tc_target_minus_base`, `employee_election`, `none`, `unverified` |
| `vesting` | annual fractions as stated, e.g. `25/25/25/25` |
| `grant_term` | `one_year` or `vested_at_grant`; company profile only, a job package never reads it |
| `sign_on_bridges_vesting`, `base_cap_usd`, `annual_refresh`, `equity_vehicle` | as stated |

Per-rung facts sit on the rungs in `levels/atlas/rungs.csv`: `seed_median_usd`
and the bonus target range `bonus_low`, `bonus_high`. `bonus_ratio_for` returns
`0.0` for a `none` company, the target midpoint for a `pct_of_base` rung, and
`None` (use the next estimator) when unverified. A company that pays no bonus
and a company nobody checked are different answers, and the UI shows unknown,
never zero, for the second. `levels/pay.describe` puts the policy on the
package so the panel can state the vest schedule and bonus rule.

Every built-in company must have a policy entry and a seeded rung at Senior,
Staff and Principal: blueprint checks `offer_policy` and `pay_reference` in
`blueprint.py` name what is missing.

## Where things live

| Question | Lives in |
|---|---|
| Which rung is which band | `levels/atlas/` files, loaded by `levels/companies.py`; `levels/ladder.band_for`, `levels/words.resolve_band` |
| The rung the employer printed on the posting | `taxonomy/stated_level.py` into `jobs.raw_level`; banded through `levels/atlas/printed.csv` |
| Which family a role borrows from | `taxonomy/comp_families.py` (`REFERENCE_FAMILY`, `BORROW_ORDER`, `borrow_rank`) |
| The heuristic split, where nothing is measured | `analytics/comp_split.py` (`_EQUITY_PCT_BY_BAND`, `BONUS_PCT`, `heuristic_ratios`) |
| What the offer calculator fills in for a company | `analytics/stock_trajectory.build_offer_terms`, `GET /api/statistics/offer-terms`; the arithmetic in `dashboard/src/features/statistics/offerModel.ts` |
| Where the person's offer and valuations are kept | `user_profile/offer.py`, `/api/profile/offer` |
| Stated pay against the user's pay floor | `analytics/pay_floor.floor_check` |
| Comparing our base with a plugin's per-level rows | `python -m scripts.bench_level_pay compare` |

## Rules

- Never split a band whose basis is `unclear`, never annualise an hourly or
  monthly rate, never split a stated total.
- Never price a level we cannot place. Its band is kept for sorting only: it
  gets no estimate, and nothing is built on it. The base the posting states is
  not priced by us, so it is still shown
  ([0006](decisions/0006-stated-base-without-a-level.md)).
- Equity's range comes from equity's own tolerance, never from the width of
  the base band. For the same reason `tc_target_minus_base` is not used as a
  second equity estimator: evaluated at both ends of a posted band it rebuilds
  equity's spread from the base band.
- Never add a pay multiplier for a family (for example `ml_ai_research`). A
  family with no row of its own borrows and is labelled `cross_family`; a
  borrowed split is never called measured.
- At a company whose `bonus_rule` is `none`, a measured bonus is a one-time
  sign-on, not annual pay.
- A posted band can rule a rung out, never locate one: posted bands are wider
  than the gap between adjacent rungs. So never fit a rung mapping to pay, and
  never feed `reconciliation` back as an automatic re-level; that would turn a
  guess into a fact and make the check meaningless.
- The package and the median beside it read the same row (`choose_rung_row`).
- The pay floor is compared, never converted: only a yearly band in the
  floor's currency is checked; a total or unstated band can only be below.
- Per-company level and pay literals live in `levels/atlas/` and nowhere else;
  `tests/test_levels_model.py` fails if a known per-company table name is
  defined anywhere under `tracker/`.
