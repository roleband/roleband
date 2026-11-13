## insights: moved as it was found (wording=as-is)

## features/statistics/CompensationPanel.tsx
# kind=sentence
insights-compensation-panel-estimated-total-compensation-is-imputed = Estimated from company, level and discipline, not stated by employers. Treat it as a reference, not an offer.
# kind=label
insights-compensation-panel-published-bands = Posted ranges
# kind=status
insights-compensation-panel-bands-from-employers = { $bands } ranges · { $employers ->
    [one] { $employers } employer
   *[other] { $employers } employers
}
# kind=heading
insights-compensation-panel-median-comp-by-level = Median estimated total compensation by level
# kind=tooltip note="A bar's tooltip: p25–p75 is the 25th to 75th percentile of the group's estimates, then how many roles it rests on"
insights-compensation-panel-spread = p25–p75: { $low }–{ $high } · { $roles }
# kind=heading note="Roles RoleBand's data prices by their base alone, shown apart from total comp"
insights-compensation-panel-estimated-base-by-level = Estimated base salary by level
# kind=sentence note="Why these roles are apart: no total exists for them"
insights-compensation-panel-base-only-lead = { $count ->
    [one] { $count } more role has only a base salary estimate, so it isn't in the figures above.
   *[other] { $count } more roles have only a base salary estimate, so they aren't in the figures above.
}
# kind=heading
insights-compensation-panel-top-paying-companies = Top-paying companies
# kind=heading
insights-compensation-panel-median-pay-by-discipline = Median estimated total compensation by discipline
# kind=label wording=as-is
insights-compensation-panel-roles = { $count ->
    [one] { $count } role
   *[other] { $count } roles
}
# kind=label
insights-compensation-panel-groups-of-roles-or-more = { $min_roles }+ roles per bar
# kind=sentence
insights-compensation-panel-base-salary-quoted-from-the = Base salary as posted, not an estimate. Each line is one posted range, however many roles share it.
# kind=label wording=as-is
insights-compensation-panel-how-compensation-is-estimated = How compensation is estimated
# kind=label
insights-compensation-panel-about-published-salary-bands = About posted ranges

## features/statistics/Demand.tsx
# kind=heading wording=as-is
insights-demand-open-roles-by-company = Open roles by company
# kind=sentence
insights-demand-each-role-counts-once-however = Each role counts once, however many places it is listed at. New and closed both count the last 2 days.
# kind=sentence wording=as-is
insights-demand-no-open-roles-at-these = No open roles at these companies.
# kind=sentence note="Under the company chart: the companies folded out of it. $share is none when this side has no open roles to take a share of"
insights-demand-more-hold = { $share ->
    [none] { $companies } more have { $roles }.
   *[known] { $companies } more have { $roles } ({ $percent }% of these roles).
}
# kind=button wording=as-is
insights-demand-show-all = Show all { $company }
# kind=heading wording=as-is
insights-demand-open-roles-by-region = Open roles by region
# kind=sentence
insights-demand-a-role-open-in-several = A role open in several regions counts in each. One that names only a region, such as Remote Europe, counts once for that region and never in its countries. Remote ANZ counts in Australia and New Zealand.
# kind=sentence wording=as-is
insights-demand-no-open-roles-yet = No open roles yet.
# kind=label wording=as-is
insights-demand-all-of = All of { $region }
# kind=label wording=as-is
insights-demand-and-more-countries = { $more ->
    [one] and { $more } more country
   *[other] and { $more } more countries
}
# kind=sentence
insights-demand-name-no-place-we-can = { $role } name no specific place, such as Remote alone.
# kind=label wording=as-is
insights-demand-of = { $shown } of { $companies }
# kind=status note="Roles new and closed over one period, the New rule's 2 days"
insights-demand-hiring-now-new-closed = { $company } hiring now · { $new } new and { $closed } closed in the last 2 days
# kind=label wording=as-is
insights-demand-each-role-once = each role once
# kind=label wording=as-is
insights-demand-with-an-open-role = with an open role
# kind=label wording=as-is
insights-demand-how-companies-are-counted = How companies are counted
# kind=label wording=as-is
insights-demand-how-regions-are-counted = How regions are counted
# kind=label wording=as-is
insights-demand-all-companies-hiring = All companies hiring
# kind=label wording=as-is
insights-demand-find-a-company = Find a company

## features/statistics/DisclosurePanel.tsx
# kind=sentence
insights-disclosure-panel-of-open-roles-have-not = { $pending } of { $open } open roles haven't been checked for a posted range yet, so they're left out.
# kind=label wording=as-is
insights-disclosure-panel-pay-transparency = Pay transparency
# kind=heading
insights-disclosure-panel-who-states-pay = Who posts a range
# kind=sentence
insights-disclosure-panel-the-share-of-open-roles = The share of checked open roles that post a range. Any range counts: base salary, total compensation or not stated.
# kind=status
insights-disclosure-panel-of-checked-roles-state-pay = { $rate } of { $checked } checked roles post a range
# kind=sentence
insights-disclosure-panel-no-open-roles-have-been = No open roles have been checked for a posted range yet.
# kind=aria
insights-disclosure-panel-how-the-disclosure-rate-is = How pay transparency is measured
# kind=label
insights-disclosure-panel-disclosure-breakdown = Pay transparency breakdown
# kind=status
insights-disclosure-panel-share-of-open-roles-stating = { $group ->
    [company] Share of open roles that post a range, by company
   *[level] Share of open roles that post a range, by level
}

## features/statistics/OverviewPanel.tsx
# kind=label wording=as-is
insights-overview-panel-most-named-skills = Most named skills
# kind=heading
insights-overview-panel-what-is-pulling-the-market = Most-wanted skills
# kind=sentence
insights-overview-panel-the-skills-open-roles-name = Skills ranked by how many open roles name them.
# kind=label wording=as-is
insights-overview-panel-leads-roles = { $display } leads · { $job_count } roles
# kind=label wording=as-is
insights-overview-panel-opened-closed = { $new_count } opened · { $closed_count } closed
# kind=label
insights-overview-panel-about-the-demand-field = About this chart

## features/statistics/PayBands.tsx
# kind=sentence
insights-pay-bands-each-line-is-one-published = Each line is one posted range. The outlined span is the level's typical range.
# kind=label wording=as-is
insights-pay-bands-any-employer = Any employer
# kind=aria
insights-pay-bands-published-base-salary-bands-by = Posted base salary ranges by level
# kind=status
insights-pay-bands-bands-from-employers = { $bands ->
    [one] { $bands } range
   *[other] { $bands } ranges
} · { $employers ->
    [one] { $employers } employer
   *[other] { $employers } employers
}
# kind=label note="The bands the picked employer publishes at a level, or none"
insights-pay-bands-employer-bands = { $published ->
    [none] No range
   *[some] { $range } · { $bands } ranges
}

## features/statistics/SkillsView.tsx
# kind=sentence
insights-skills-view-a-narrowed-view-ranks-skills = Filtered: ranked by how often these roles name a skill compared with the market. Unfiltered: ranked by number of roles.
# kind=sentence
insights-skills-view-no-skills-extracted-for-this = No skills found for this selection yet.
# kind=heading wording=as-is
insights-skills-view-expected-of-the-role = Expected of the role
# kind=sentence
insights-skills-view-process-leadership-and-collaboration-asks = Process, leadership and collaboration skills that most roles ask for.
# kind=label wording=as-is
insights-skills-view-against-the-market = Against the market
# kind=heading wording=as-is
insights-skills-view-what-sets-these-roles-apart = What sets these roles apart
# kind=label wording=as-is
insights-skills-view-above-the-line-named-more = Above the line: named more than the market does
# kind=sentence
insights-skills-view-pick-a-company-a-discipline = Pick a company or a discipline to compare its roles with the market.
# kind=label wording=as-is
insights-skills-view-skill = Skill
# kind=label wording=as-is
insights-skills-view-category = Category
# kind=label wording=as-is
insights-skills-view-share-of-roles = Share of roles
# kind=label
insights-skills-view-lift = vs market
# kind=label wording=as-is note="$view is narrowed when a company, discipline or side is picked"
insights-skills-view-lead-skill = { $view ->
    [narrowed] { $skill } sets these roles apart
   *[market] { $skill } leads
}
# kind=label wording=as-is
insights-skills-view-of-roles-name-it = { $view ->
    [narrowed] { $share } of these roles name it, against { $market_share } of the market
   *[market] { $share } of roles name it
}
# kind=label wording=as-is
insights-skills-view-how-skills-are-ranked = How skills are ranked
# kind=label wording=as-is
insights-skills-view-roles = Roles
# kind=label wording=as-is
insights-skills-view-naming-a-skill = naming a skill
# kind=label wording=as-is
insights-skills-view-expected = Expected
# kind=label wording=as-is
insights-skills-view-any-company = Any company
# kind=aria note="The info button's screen-reader name, beside the Expected of the role column"
insights-skills-view-what-expected-of-the-role = What “Expected of the role” means
# kind=label
insights-skills-view-skills-order = { $view ->
    [narrowed] Skills, most distinctive first
   *[market] Skills, most named first
}
# kind=status
insights-skills-view-loading = Loading skills…
# kind=heading
insights-skills-view-load-failed = Couldn't load skills

## features/statistics/StatisticsView.tsx
# kind=label note="Names the time-range picker on Insights: shown beside it and read out as its name"
insights-statistics-view-window = Time range
# kind=label
insights-statistics-view-all-time = All time
# kind=label
insights-statistics-view-statistics-sections = Insights sections
# kind=label wording=as-is
insights-statistics-view-discipline = Discipline
# kind=label
insights-statistics-view-advanced-view = Advanced view
# kind=heading
insights-statistics-view-advanced-warning-title = Fair warning
# kind=sentence note="Shown once, the first time the person turns the advanced view on; a light joke, not a warning about risk"
insights-statistics-view-advanced-warning-body = Advanced view is for people who read footnotes for fun: how long roles stay open, how often pay is posted, levels and stock side by side, and the small samples behind them. You can switch back any time.
# kind=button
insights-statistics-view-show-me-everything = Show me everything
# kind=button
insights-statistics-view-keep-it-simple = Keep it simple
# kind=sentence note="Above a tab the basic view does not list, opened from a link"
insights-statistics-view-part-of-advanced-view = This tab is part of the advanced view.
# kind=button
insights-statistics-view-show-advanced-view = Show advanced view

## features/statistics/StockTrajectoryPanel.tsx
# kind=heading wording=as-is
insights-stock-trajectory-panel-stock-trajectory = Stock trajectory
# kind=sentence
insights-stock-trajectory-panel-no-open-roles-at-public = No open roles at public companies with a compensation estimate yet.
# kind=status note="$equity is where the equity part of the package comes from: measured, mixed (partly measured) or estimated"
insights-stock-trajectory-panel-typical-package = { $equity ->
    [measured] Typical public-company total compensation · equity measured
    [mixed] Typical public-company total compensation · equity partly measured
   *[estimated] Typical public-company total compensation · equity estimated
}
# kind=sentence
insights-stock-trajectory-panel-stock-moves-re-price-equity = Only equity moves with the stock. Base is the posted base salary range where a role has one, else an estimate. Bonus comes from the posting, pay data or the company's own rule, else an estimate. A reference, not an offer.
# kind=label wording=as-is
insights-stock-trajectory-panel-stock-price-change = Stock price change
# kind=button wording=as-is
insights-stock-trajectory-panel-reset-to-today = Reset to today
# kind=label
insights-stock-trajectory-panel-equity-shockwave = Equity impact
# kind=heading wording=as-is
insights-stock-trajectory-panel-who-moves-when-the-stock = Who moves when the stock moves
# kind=heading wording=as-is note="$move is the stock scenario's direction: up, down or flat"
insights-stock-trajectory-panel-public-companies = { $move ->
    [up] Public companies · +{ $pct }%
   *[other] Public companies · { $pct }%
}
# kind=sentence
insights-stock-trajectory-panel-sorted-by-equity-exposure-only = Sorted by equity share.
# kind=sentence wording=as-is
insights-stock-trajectory-panel-no-open-roles-at-public-yet = No open roles at public companies yet.
# kind=label wording=as-is
insights-stock-trajectory-panel-ticker = Ticker
# kind=label wording=as-is
insights-stock-trajectory-panel-equity = Equity
# kind=aria
insights-stock-trajectory-panel-about-the-source-labels = Where each figure comes from
# kind=label wording=as-is
insights-stock-trajectory-panel-equity-share = Equity share
# kind=label wording=as-is
insights-stock-trajectory-panel-today = Today
# kind=label wording=as-is
insights-stock-trajectory-panel-projected = Projected
# kind=label wording=as-is
insights-stock-trajectory-panel-change = Change
# kind=label
insights-stock-trajectory-panel-no-exposure = no equity
# kind=heading wording=as-is
insights-stock-trajectory-panel-private-companies = Private companies
# kind=sentence
insights-stock-trajectory-panel-pre-ipo-equity-is-illiquid = Private-company equity has no daily price, so this scenario doesn't change their total compensation.
# kind=label wording=as-is
insights-stock-trajectory-panel-median-tc = Median TC
# kind=tooltip note="The full words behind the Median TC column, for its hover and screen-reader name"
insights-stock-trajectory-panel-median-tc-full = Median total compensation
# kind=label wording=as-is
insights-stock-trajectory-panel-options = Options
# kind=label wording=as-is
insights-stock-trajectory-panel-no-equity = No equity
# kind=label
insights-stock-trajectory-panel-cash-election = Cash or equity
# kind=label note="Where a part of a company's typical total compensation comes from"
insights-stock-trajectory-panel-part-source = { $source ->
    [posted] Posted
    [company_rule] Company rule
    [measured] Measured
    [mixed] Mixed
   *[estimated] Estimated
}
# kind=status
insights-stock-trajectory-panel-part-source-explained = { $source ->
    [posted] From the posted ranges of this company's roles
    [company_rule] How this company says it pays this part
    [measured] From pay data for this company and level
    [mixed] Differs between this company's roles
   *[estimated] Estimated for this level
}
# kind=sentence note="When the company search matches no table: $query is what the person typed"
insights-stock-trajectory-panel-no-company-matches = No company matches “{ $query }”.
# kind=label
insights-stock-trajectory-panel-base = Base
# kind=label
insights-stock-trajectory-panel-bonus = Bonus
# kind=label
insights-stock-trajectory-panel-no-bonus = No bonus
# kind=label note="The company's vesting schedule: the share of a grant that vests each year, such as 25/25/25/25"
insights-stock-trajectory-panel-vests = Vests { $schedule }
# kind=heading
insights-stock-trajectory-panel-choice-companies = Cash or equity, your choice
# kind=sentence
insights-stock-trajectory-panel-choice-explained = At these companies each person chooses how much of their total compensation is cash and how much is equity, so no split is shown and a stock move changes nothing here.
# kind=status note="Roles with total compensation that has no split, so they are not in the tables: 3 roles"
insights-stock-trajectory-panel-left-out = Left out: { $count } { $count ->
    [one] { -role(num: "one") }
   *[other] { -role(num: "other") }
} with no split
# kind=aria
insights-stock-trajectory-panel-why-left-out = Why these roles are left out
# kind=label note="Why a role's total compensation has no split on this tab"
insights-stock-trajectory-panel-left-out-reason = { $reason ->
    [not_us_pay] Outside the US
    [level_unplaced] Level not placed
    [base_only] Base only, no total
    [basis_unclear] Range basis not stated
    [hourly] Hourly rate
    [monthly] Monthly rate
    [period_unclear] Period unclear
    [total_compensation] Posted as total compensation
    [plugin_without_split] Plugin reports no split
   *[plugin_not_covered] Not read by plugin
}
# kind=label wording=as-is
insights-stock-trajectory-panel-projected-tc = { $projected } projected TC
# kind=tooltip note="The full words behind the projected TC figure, for its hover and screen-reader name"
insights-stock-trajectory-panel-projected-tc-full = { $projected } projected total compensation
# kind=heading note="The Stock tab's figure while the price is unchanged: $share is equity's percent of total compensation, such as 45%"
insights-stock-trajectory-panel-equity-figure = { $share } of total compensation is equity
# kind=label wording=as-is
insights-stock-trajectory-panel-how-stock-trajectory-is-projected = How stock trajectory is projected
# kind=label wording=as-is
insights-stock-trajectory-panel-median-tc-tile = median TC
# kind=tooltip note="The full words behind the median TC tile, for its hover and screen-reader name"
insights-stock-trajectory-panel-median-tc-tile-full = median total compensation
# kind=label wording=as-is
insights-stock-trajectory-panel-at-price-change = { $move ->
    [up] at +{ $pct }%
   *[other] at { $pct }%
}
# kind=label wording=as-is
insights-stock-trajectory-panel-vs-today = vs today
# kind=label wording=as-is
insights-stock-trajectory-panel-of-tc-at-risk = of TC (at risk)
# kind=tooltip note="The full words behind the TC at risk tile, for its hover and screen-reader name"
insights-stock-trajectory-panel-of-tc-at-risk-full = of total compensation (at risk)
# kind=aria wording=as-is
insights-stock-trajectory-panel-stock-price-change-percent = Stock price change percent
# kind=aria
insights-stock-trajectory-panel-how-to-read-equity-sensitivity = How to read this chart
# kind=sentence wording=as-is
insights-stock-trajectory-panel-sensitivity-explained = { $move ->
    [flat] At today's price, each bar is what a 10% rise in the stock adds to typical total compensation. Move the slider for a scenario.
   *[other] Shows the dollar change to typical total compensation under this scenario.
}
# kind=label wording=as-is
insights-stock-trajectory-panel-scenario = { $move ->
    [flat] Per 10% stock move · adjust above for a scenario
    [up] +{ $pct }% scenario
   *[down] { $pct }% scenario
}
# kind=label wording=as-is
insights-stock-trajectory-panel-about-public-company-projections = About public-company projections
# kind=tooltip
insights-stock-trajectory-panel-paid-in-cash-unaffected-by = Paid in cash, unaffected by the stock price
# kind=label wording=as-is
insights-stock-trajectory-panel-why-private-companies-do-not = Why private companies do not move
# kind=status
insights-stock-trajectory-panel-loading = Loading the stock trajectory…
# kind=heading
insights-stock-trajectory-panel-load-failed = Couldn't load the stock trajectory
# kind=label note="An equity vehicle: restricted stock units"
insights-stock-trajectory-panel-rsus = RSUs

## features/statistics/OfferCalculator.tsx
# kind=heading note="The offer block before the first answer"
insights-offer-start-title = What an offer pays, year by year
# kind=sentence
insights-offer-start-intro = A few short questions, one at a time. What you enter stays on this computer.
# kind=status note="While the kept offer loads"
insights-offer-loading = Loading your offer
# kind=sentence
insights-offer-load-failed = Your offer didn't load.
# kind=sentence note="A save of the last answer failed; the answer is still on screen"
insights-offer-save-failed = Your last answer wasn't saved. Answer it again to keep it.
# kind=aria note="Where the person is in the questions this offer asks"
insights-offer-progress = Question { $n } of { $total }
# kind=heading
insights-offer-q-company = Which company made the offer?
# kind=sentence
insights-offer-q-company-hint = Its usual stock and bonus rules fill in for you.
# kind=label note="The company list's first entry, before a company is chosen"
insights-offer-pick-company = Choose a company
# kind=aria
insights-offer-all-companies = All companies
# kind=heading
insights-offer-q-base = What's the base salary?
# kind=sentence
insights-offer-q-base-hint = The yearly salary on your offer letter.
# kind=status note="Beside a yearly figure the person types"
insights-offer-per-year = a year
# kind=status note="Beside a price per share the person types"
insights-offer-per-share = a share
# kind=heading note="$vehicle is the company's stock type: cash is a company where each person picks the split between cash and stock"
insights-offer-q-stock = { $vehicle ->
    [options] How many options are in the offer?
    [cash] How much did you choose to take as stock?
   *[rsu] How much stock is in the offer?
}
# kind=sentence note="$company is the company's name; another is a company not on the list"
insights-offer-q-stock-hint = { $vehicle ->
    [options] { $company } grants stock options. Enter the number on your offer letter.
    [cash] { $company } lets you split your pay between cash and stock. Enter the stock part over four years: a move changes only that part.
    [another] Enter the total grant on your offer letter, in dollars or shares.
   *[rsu] { $company } grants RSUs. Enter the total grant on your offer letter.
}
# kind=button
insights-offer-no-stock = { $vehicle ->
    [options] No options
    [cash] All cash
   *[rsu] No stock
}
# kind=heading
insights-offer-q-strike = What's the strike price?
# kind=sentence
insights-offer-q-strike-hint = The price per share you pay to buy each option.
# kind=heading note="$quote is yes when a last close is stored for the company"
insights-offer-q-price = { $quote ->
    [yes] Use the last close for { $company }?
   *[no] What's the share price today?
}
# kind=sentence note="$price is a price per share, $date the market day it closed"
insights-offer-q-price-quote = { $price } a share at the close on { $date }.
# kind=button
insights-offer-use-price = Use { $price }
# kind=button
insights-offer-own-price = Enter a price
# kind=heading
insights-offer-q-valuation = What is { $company } worth?
# kind=button note="Answers the valuation question without a valuation: the equity reads at the value it was granted at"
insights-offer-dont-know = I don't know
# kind=heading note="$schedule lists the percent vesting each year, as 5, 15, 40, and 40"
insights-offer-q-vesting-stated = Does your grant vest { $schedule }?
# kind=sentence
insights-offer-q-vesting-stated-hint = That is the schedule { $company } usually states, as a percent of the grant each year.
# kind=heading
insights-offer-q-vesting = How does the grant vest?
# kind=sentence
insights-offer-q-vesting-hint = { $named ->
    [yes] { $company } doesn't say. Most grants vest evenly over four years.
   *[no] Most grants vest evenly over four years.
}
# kind=sentence
insights-offer-percent-of-grant = Percent of the grant in each year.
# kind=button
insights-offer-vesting-yes = Yes, same
# kind=button
insights-offer-vesting-differs = Mine differs
# kind=button note="Opens one field per year for a schedule not among the choices"
insights-offer-vesting-other = Other
# kind=status note="Marks the even schedule among the choices"
insights-offer-vesting-even = even
# kind=sentence
insights-offer-vesting-too-much = The years add up to { $pct }%. Keep it at 100% or under.
# kind=heading
insights-offer-q-bonus = Is there a yearly bonus target?
# kind=sentence
insights-offer-q-bonus-hint = A share of base, as your offer letter states it.
# kind=button note="$pct is a bonus target as a percent of base; 0 is no bonus"
insights-offer-bonus-choice = { $pct ->
    [0] No bonus
   *[other] { $pct }%
}
# kind=aria
insights-offer-bonus-other = Another bonus target, percent of base
# kind=heading
insights-offer-q-sign-on = Any sign-on bonus?
# kind=sentence
insights-offer-q-sign-on-hint = A one-time payment for joining, sometimes split over two years.
# kind=button
insights-offer-sign-on-yes = Yes
# kind=button
insights-offer-sign-on-no = No sign-on
# kind=sentence note="Under a question, when Next is pressed before it is answered; $what is the question"
insights-offer-need = { $what ->
    [company] Choose a company.
    [base] Enter the yearly base salary.
    [stock] Enter the amount, or choose the button beside it.
    [strike] Enter the strike price.
    [price] Enter today's share price.
    [valuation] Enter the value at grant, or choose I don't know.
    [vesting] Enter the percent vesting in at least one year.
    [bonus] Choose a bonus target.
   *[sign_on] Enter at least one sign-on amount.
}
# kind=button
insights-offer-next = Next
# kind=button note="Keeps a changed answer and goes back to the offer"
insights-offer-done = Done
# kind=button
insights-offer-back = Back
# kind=button
insights-offer-cancel = Cancel
# kind=button note="Folds the questions away; the answers so far are kept"
insights-offer-later = Finish later
# kind=heading note="$named is no for a company not on the list"
insights-offer-finished-title = { $named ->
    [yes] Your { $company } offer, year by year
   *[no] Your offer, year by year
}
# kind=status
insights-offer-unfinished = { $answered } of { $total } answered
# kind=button
insights-offer-continue = Continue
# kind=sentence note="The offer was started from a company's or a role's typical figures"
insights-offer-typical = These are typical figures. Swap in yours to see your own offer.
# kind=button
insights-offer-swap = Use my figures
# kind=status note="Where an answer comes from, on its chip"
insights-offer-tag = { $tag ->
    [typical] Typical
    [rule] Company rule
    [employer] Stated by the company
    [estimated] Estimated
    [assumed] Assumed
   *[quote] Last close
}
# kind=aria note="Names a chip that reopens its question; $answer is the chip's text"
insights-offer-chip-edit = Change { $answer }
# kind=status
insights-offer-chip-base = Base { $amount }
# kind=status
insights-offer-chip-stock = { $kind ->
    [none] No stock
    [cash] { $amount } as stock
    [options] { $count } options
    [shares] { $count } shares
   *[dollars] { $amount } in stock
}
# kind=status
insights-offer-chip-strike = Strike { $amount }
# kind=status
insights-offer-chip-price = { $kind ->
    [none] No share price yet
   *[some] { $amount } a share
}
# kind=status
insights-offer-chip-valuation = { $kind ->
    [none] At the value granted
    [per_share] { $from } to { $to } a share
   *[company] Valued { $from } to { $to }
}
# kind=status note="$schedule is the percent vesting each year, as 5 / 15 / 40 / 40"
insights-offer-chip-vesting = Vests { $schedule }
# kind=status
insights-offer-chip-bonus = { $pct ->
    [0] No bonus
   *[other] { $pct }% bonus
}
# kind=status
insights-offer-chip-sign-on = { $kind ->
    [none] No sign-on
   *[some] Sign-on { $first } + { $second }
}
# kind=aria
insights-offer-chart = Total compensation by year
# kind=status note="Under the four-year total; $amount is the difference a move makes"
insights-offer-vs-today = { $sign ->
    [up] { $amount } more than at today's price
    [down] { $amount } less than at today's price
   *[same] At today's price
}
# kind=button note="Opens the years as a table of exact figures"
insights-offer-show-table = Show the table
# kind=button note="Forgets the offer on this computer; private-company valuations stay"
insights-offer-clear = Clear offer
# kind=status note="Toast after Clear offer; the toast's Undo puts the offer back"
insights-offer-cleared = Offer cleared.
# kind=status note="When the person last saved an answer to the offer, or a valuation; $date is a calendar day"
insights-offer-entered = Entered by you, { $date }
# kind=status note="The form was filled from a company's median role on this tab ($title absent), or from one role's figures on its detail page"
insights-offer-started-from = { $kind ->
    [role] Filled in from { $title } at { $company }.
   *[company] Filled in from the median role at { $company }.
}
# kind=button note="Puts back the offer the person had before the form was filled in from a role"
insights-offer-undo = Undo
# kind=label note="The company picker's choice for a company not on the list"
insights-offer-another-company = Another company
# kind=status note="The answer chip for a company not on the list"
insights-offer-chip-another = { $listed ->
    [yes] Another company, listed
   *[no] Another company, private
}
# kind=aria note="Names the choice between a listed and a private company, for a company not on the list"
insights-offer-listed-label = Listed or private
# kind=label
insights-offer-listed = { $listed ->
    [yes] Listed
   *[no] Private
}
# kind=sentence note="The company's own bonus rule, under the bonus field"
insights-offer-bonus-rule = { $rule ->
    [none] This company pays no annual bonus.
   *[pct_of_base] This company sets bonus as a share of base by level. Enter the one on your offer.
}
# kind=aria
insights-offer-equity-type = Equity type
# kind=aria note="Names the choice between a grant stated in dollars and one stated in shares"
insights-offer-grant-unit = Grant stated in
# kind=label
insights-offer-grant-unit-option = { $unit ->
    [dollars] Dollars
   *[shares] Shares
}
# kind=sentence note="No price key is saved. $link is a link to Settings › Plugins, where the Stock prices card takes a key"
insights-offer-price-needs-key = Type today's price, or add a key in { $link } to fill it from the last close.
# kind=link
insights-offer-price-settings = Settings › Plugins › Stock prices
# kind=sentence note="A price key is saved, but no close is stored for this ticker yet"
insights-offer-price-no-close = No close stored for { $ticker } yet. Type today's price.
# kind=aria
insights-offer-vesting-year = Year { $year }, percent vesting
# kind=sentence note="The four years vest a share of the grant other than all of it"
insights-offer-vesting-sum = These four years vest { $pct }% of the grant.
# kind=label
insights-offer-sign-on = Sign-on, year { $year }
# kind=sentence
insights-offer-sign-on-bridges = This company pays sign-on cash in the first two years to bridge its vesting.
# kind=sentence
insights-offer-private = Private-company equity can't be sold until the company lists or runs a tender.
# kind=aria note="Names the choice between a valuation per share and one for the whole company"
insights-offer-valuation-unit = Valuation stated as
# kind=label
insights-offer-valuation-unit-option = { $unit ->
    [per_share] Price per share
   *[company] Company valuation
}
# kind=label
insights-offer-valuation-grant = { $unit ->
    [per_share] Share price at grant
   *[company] Valuation at grant
}
# kind=label
insights-offer-valuation-test = { $unit ->
    [per_share] Share price to test
   *[company] Valuation to test
}
# kind=label
insights-offer-share-count = Shares outstanding
# kind=sentence
insights-offer-valuation-hint = Enter the valuation on your offer and the one to test, such as the latest round or your own expectation.
# kind=sentence
insights-offer-valuation-none = Without a valuation, the equity is shown at the valuation it was priced at.
# kind=label
insights-offer-move = { $listed ->
    [yes] Stock price change
   *[no] Change in valuation
}
# kind=aria
insights-offer-move-aria = { $listed ->
    [yes] Stock price change for your offer, percent
   *[no] Change in valuation for your offer, percent
}
# kind=sentence note="What the equity cannot be valued without; until then it counts as zero"
insights-offer-missing = { $missing ->
    [price] Enter today's share price to value the shares.
    [strike] Enter the strike price to value the options.
    [valuation] Enter a valuation to value the shares.
   *[share_count] Enter the shares outstanding to turn the valuation into a price per share.
}
# kind=label
insights-offer-year = Year
# kind=label
insights-offer-year-n = Year { $year }
# kind=label
insights-offer-four-years = Four years
# kind=label
insights-offer-sign-on-column = Sign-on
# kind=label note="Column of total compensation at today's price"
insights-offer-tc-today = TC today
# kind=tooltip
insights-offer-tc-today-full = Total compensation at today's price
# kind=label note="Column of total compensation after the move; $pct is signed"
insights-offer-tc-moved = { $move ->
    [up] TC at +{ $pct }%
   *[down] TC at { $pct }%
}
# kind=tooltip note="$pct is the size of the move, without a sign"
insights-offer-tc-moved-full = { $move ->
    [up] Total compensation after a { $pct }% rise
   *[down] Total compensation after a { $pct }% fall
}
# kind=status note="A year whose total compensation is less than the year before"
insights-offer-drop = Less than year { $year }
# kind=button note="Starts the offer from this company's median role, as typical figures"
insights-offer-start = Start from this
# kind=aria note="Names a row's Start from this button with its company"
insights-offer-start-aria = Start an offer from { $company }
# kind=label note="Column of the button that starts the offer from a row"
insights-offer-column = Your offer
# kind=label note="Private companies table: total compensation with equity at the valuation the person entered and the move"
insights-offer-at-your-valuation = At your valuation
# kind=label note="The At your valuation column once the valuation moves; $pct is signed"
insights-offer-at-your-valuation-moved = { $move ->
    [up] At your valuation, +{ $pct }%
   *[down] At your valuation, { $pct }%
}
# kind=tooltip note="Hover name of a figure in the At your valuation column; $date is when the valuation was entered"
insights-offer-at-your-valuation-full = Equity at the valuation you entered on { $date }

## features/statistics/VelocityPanel.tsx
# kind=heading wording=as-is
insights-velocity-panel-companies = Companies · { $window }
# kind=label wording=as-is
insights-velocity-panel-open = Open
# kind=label wording=as-is
insights-velocity-panel-time-posted = Time posted
# kind=sentence
insights-velocity-panel-from-the-first-scan-that = Days from first listed to closed. Needs 5 closed roles with a known start.
# kind=heading wording=as-is
insights-velocity-panel-age-of-open-roles = Age of open roles
# kind=heading wording=as-is
insights-velocity-panel-how-long-postings-stay-up = How long postings stay up
# kind=sentence
insights-velocity-panel-this-builds-up-as-roles = { $closed_sample ->
    [one] Fills in once 5 closed roles have a known start. 1 has so far.
   *[other] Fills in once 5 closed roles have a known start. { $closed_sample } have so far.
}
# kind=label wording=as-is
insights-velocity-panel-median-age = { $median_days_open } median age
# kind=label wording=as-is
insights-velocity-panel-median-time-posted = { $median_observed_listing_duration_days } median time posted
# kind=label
insights-velocity-panel-more-already-listed-when-found = { $already_listed } found already listed
# kind=aria note="The info button's screen-reader name, beside the Time posted chart"
insights-velocity-panel-what-time-posted-measures = What “Time posted” measures
# kind=label
insights-velocity-panel-age-unknown = Age unknown: { $count }
# kind=label
insights-velocity-panel-time-posted-unknown = Time posted unknown: { $count }
# kind=aria note="The info button's screen-reader name, beside the Age unknown and Time posted unknown lines"
insights-velocity-panel-what-unknown-means = What “unknown” means
# kind=sentence
insights-velocity-panel-why-a-start-is-unknown = Found on a company's first scan, with no earlier date from the employer.
# kind=sentence
insights-velocity-panel-counted-from-first-listed = Counted from when each role was first listed.
# kind=aria note="The info button's screen-reader name, after the found already listed count in Pace's summary line"
insights-velocity-panel-what-already-listed-means = What “found already listed” means
# kind=sentence
insights-velocity-panel-why-already-listed = Already listed when first seen: dated more than 2 days earlier by the employer, or found on a company's first scan with no date in the last 2 days.

## features/statistics/ageCopy.ts
# kind=label wording=as-is
insights-age-copy-listed-today = Listed today
# kind=label wording=as-is
insights-age-copy-listed-for = Listed for { $days }

## features/statistics/charts/StatisticsCharts.tsx
# kind=label wording=as-is note="A skill's tooltip: its open roles, then its category"
insights-statistics-charts-skill-open-roles = { $job_count } open roles · { $category }
# kind=aria
insights-statistics-charts-market-demand-field = Most-wanted skills
# kind=label
insights-statistics-charts-company-open-roles = { $open ->
    [one] { $open } open role
   *[other] { $open } open roles
}
# kind=tooltip note="A company's new roles and closings over the last 2 days, on its chart tooltip. $new_roles is the new ones ('+3 new') and $closed_roles the closings ('−2 closed'), each in its own colour"
insights-statistics-charts-new-closed = { $new_roles } · { $closed_roles } in the last 2 days
# kind=tooltip note="Roles new at a company in the last 2 days, a part of the line 'new · closed in the last 2 days'"
insights-statistics-charts-new-count = +{ $fresh } new
# kind=tooltip note="Roles a company closed in the last 2 days, a part of the line 'new · closed in the last 2 days'"
insights-statistics-charts-closed-count = −{ $closed } closed
# kind=aria wording=as-is
insights-statistics-charts-open-roles-by-company = Open roles by company
# kind=label wording=as-is
insights-statistics-charts-open-new-closed = { $label }: { $open } open, { $fresh } new, { $closed } closed
# kind=label wording=as-is
insights-statistics-charts-closed = Closed ←
# kind=label wording=as-is note="A company's change in equity under the stock scenario: $amount is the size of the change, $direction its sign"
insights-statistics-charts-equity-change = { $direction ->
    [flat] $0 change
    [down] −{ $amount }
   *[up] +{ $amount }
}
# kind=label wording=as-is
insights-statistics-charts-no-change = No change
# kind=aria
insights-statistics-charts-equity-shockwave-by-company = Equity impact by company
# kind=label wording=as-is
insights-statistics-charts-share-against-market = { $share }% of these roles · { $market_share }% of the market
# kind=tooltip note="How many times the market's rate a skill is named at, under its share of these roles"
insights-statistics-charts-lift-the-market-s-rate = ×{ $lift } the market's rate
# kind=label wording=as-is
insights-statistics-charts-share-of-these-roles = share of these roles →
# kind=label wording=as-is
insights-statistics-charts-the-market-s-rate = × the market's rate →
# kind=aria wording=as-is
insights-statistics-charts-what-sets-these-roles-apart = What sets these roles apart
# kind=label wording=as-is
insights-statistics-charts-of-these-roles-the-market = { $skill }: { $share }% of these roles, ×{ $lift } the market

## features/statistics/charts/compBands.ts

## features/statistics/charts/disclosure.ts
# kind=label
insights-disclosure-unclassified = Level unknown
# kind=sentence same-as=insights-disclosure-panel-no-open-roles-have-been
insights-disclosure-no-open-roles-have-been = No open roles have been checked for a posted range yet.
# kind=sentence note="$rates lists each group's rate; $unrated counts the groups with nothing checked yet"
insights-disclosure-share-of-checked-open-roles = Share of checked open roles that post a range. { $rates }.{ $unrated ->
        [0] { "" }
        [one] { " " }{ $unrated } more group has no role checked yet, so no rate can be stated for them.
       *[other] { " " }{ $unrated } more groups have no role checked yet, so no rate can be stated for them.
    }
# kind=label wording=as-is
insights-disclosure-of-roles = { $label }: { $rate }, { $disclosed } of { $checked } roles
# kind=label
insights-disclosure-rate-states-pay = { $rate } post a range
# kind=tooltip note="Under a company's share of roles stating pay: the roles that state it, of the open roles checked"
insights-disclosure-of-checked-open-roles = { $disclosed } of { $checked } checked open roles

## features/statistics/charts/StatisticsCharts.tsx (by hand)

## features/statistics/CompensationPanel.tsx
# kind=status
insights-compensation-panel-loading = Loading compensation…
# kind=heading
insights-compensation-panel-load-failed = Couldn't load compensation

## features/statistics/Demand.tsx
# kind=label wording=as-is
insights-demand-open = { $role } open
# kind=status
insights-demand-loading = Loading hiring activity…
# kind=heading
insights-demand-load-failed = Couldn't load hiring activity
# kind=label note="Under a count of new roles: 3 new in the last 2 days"
insights-demand-last-2-days = last 2 days

## features/statistics/OverviewPanel.tsx
# kind=label wording=as-is
insights-overview-panel-companies = { $companies } companies
# kind=status
insights-overview-panel-loading = Loading the overview…
# kind=heading
insights-overview-panel-load-failed = Couldn't load the overview

## features/statistics/VelocityPanel.tsx
# kind=label wording=as-is
insights-velocity-panel-opened-count = { $opened } opened
# kind=label wording=as-is same-as=insights-demand-open
insights-velocity-panel-open-count = { $open_total } open
# kind=status
insights-velocity-panel-loading = Loading the hiring pace…
# kind=heading
insights-velocity-panel-load-failed = Couldn't load the hiring pace

## features/statistics/charts/compBands.ts
# kind=label wording=as-is
insights-comp-bands-to = { $low } to { $high }
# kind=sentence note="A level's summary when an employer is picked: $summary is the level's own sentence, $published whether the employer publishes a band at this level, $ranges lists them"
insights-comp-bands-employer-at-level = { $published ->
    [none] { $summary } { $employer } posts no range at this level.
   *[some] { $summary } { $employer }: { $ranges }.
}

## features/statistics/charts/disclosure.ts

## The two sides of Insights' company split (docs/copy.md)
# kind=label
insights-your-companies = Your companies
# kind=label
insights-other-companies = Other companies
# kind=label note="A period lens: 7d, 30d, 90d"
insights-period-days = { $days }d

## Words several Insights panels share
# kind=label wording=as-is
insights-common-companies = Companies
# kind=label wording=as-is
insights-common-company = Company
# kind=label wording=as-is
insights-common-open-roles = Open roles
# kind=label wording=as-is
insights-common-open-roles-unit = open roles
# kind=label wording=as-is
insights-common-new = New
# kind=label note="Roles first seen in a period that were new when found; from a company's first scan, only those its employer dated in the last 2 days"
insights-common-opened = Opened
# kind=label wording=as-is
insights-common-closed = Closed
# kind=label wording=as-is
insights-common-market = Market
# kind=label wording=as-is
insights-common-by-level = By level
# kind=label wording=as-is same-as=insights-velocity-panel-market-current
insights-common-by-company = By company
# kind=label wording=as-is
insights-common-all-companies = All companies
# kind=label note="The period a figure covers: all-time, or last 30d"
insights-common-last-days-or-all-time = { $period ->
    [all] all time
   *[days] last { $days }d
}
# kind=label note="The period a figure covers when it is all the history there is: since the first day these companies were read in full, and how many days that is"
insights-common-since-date = since { $date } ({ $days ->
        [one] { $days } day
       *[other] { $days } days
    })

## Skill categories (backend/tracker/skills/catalog.yaml), from copy/skills.ts
# kind=name note="Skill category; slug language"
insights-skill-language = Language
# kind=name note="Skill category; slug framework"
insights-skill-framework = Framework
# kind=name note="Skill category; slug cloud"
insights-skill-cloud = Cloud
# kind=name note="Skill category; slug data"
insights-skill-data = Data
# kind=name note="Skill category; slug ml_ai"
insights-skill-ml-ai = ML / AI
# kind=name note="Skill category; slug infra"
insights-skill-infra = Infra
# kind=name note="Skill category; slug security"
insights-skill-security = Security
# kind=name note="Skill category; slug process"
insights-skill-process = Process
# kind=name note="Skill category; slug leadership"
insights-skill-leadership = Leadership
# kind=name note="Skill category; slug collaboration"
insights-skill-collaboration = Collaboration
# kind=name note="Skill category; slug industry"
insights-skill-industry = Industry

## Statistics names said from codes the server sends: the cohort series
## and the fixed age bands
## (backend/tracker/analytics/velocity.py AGING_BANDS, by `lo`).
# kind=label wording=as-is
insights-aging-from-0-days = < 1 week
# kind=label wording=as-is
insights-aging-from-7-days = 1–2 weeks
# kind=label wording=as-is
insights-aging-from-14-days = 2–4 weeks
# kind=label wording=as-is
insights-aging-from-30-days = 1–2 months
# kind=label wording=as-is
insights-aging-from-60-days = 2–3 months
# kind=label wording=as-is
insights-aging-from-90-days = 3 months+

## The Overview's one-line brief, said from the facts the server sends. Each
## sentence is said only when its fact is there; the brief joins them with a space.
# kind=sentence wording=as-is
insights-brief-open = { $open } open roles across { $companies } companies.
# kind=sentence note="$period: since names the start of all the history there is ($date, '3 Nov'); all is all time before the history starts; days is a window"
insights-brief-opened = { $period ->
    [since] { $opened } opened, { $closed } closed since { $date }.
    [all] { $opened } opened, { $closed } closed, all time.
   *[days] { $opened } opened in { $days }d, { $closed } closed.
}
# kind=sentence wording=as-is
insights-brief-top-skill = Top skill: { $skill } ({ $count } roles).

## features/statistics/LevelsPanel.tsx
# kind=status
insights-levels-loading = Loading the level guide…
# kind=heading
insights-levels-load-failed = Couldn't load the level guide
# kind=heading
insights-levels-figure = How each company names its levels
# kind=heading
insights-levels-figure-translating = { $company } { $code } is { $level }
# kind=sentence
insights-levels-line = Pick any level to see what each company with a level guide calls it.
# kind=sentence
insights-levels-line-translating = The lit column is the same level at every other company.
# kind=label
insights-levels-kpi-guided = With a level guide
# kind=label
insights-levels-kpi-flat = Titles without levels
# kind=label
insights-levels-kpi-flat-sub = Level never stated
# kind=label
insights-levels-kpi-skipped = No { $level } level
# kind=label
insights-levels-kpi-skipped-sub = Nearest level stands in
# kind=label
insights-levels-search = Company or level
# kind=label note="A search placeholder: a company and a level code"
insights-levels-search-example = Google or ICT4
# kind=label
insights-levels-sector = Sector
# kind=label
insights-levels-your-level = { $level }, your level
# kind=label
insights-levels-your-aim = { $level }, your aim
# kind=label
insights-levels-translating-column = { $level }, translating
# kind=aria
insights-levels-translate-from = Translate from { $company } { $code }
# kind=status
insights-levels-translating = Translating { $company } { $code } ({ $level }) across every company
# kind=button
insights-levels-clear = Clear
# kind=sentence
insights-levels-ambiguous = { $count ->
    [one] { $code } is a level at { $count } company. Pick it to translate from.
   *[other] { $code } is a different level at { $count } companies. Pick one to translate from.
}
# kind=label
insights-levels-engineering = Engineering levels
# kind=tooltip
insights-levels-engineering-title = This company lists levels for engineers only
# kind=status
insights-levels-flat = Titles state no level here
# kind=tooltip
insights-levels-flat-title = This company's job titles don't state a level beyond these
# kind=aria
insights-levels-skipped = { $company } has no { $level } level
# kind=status
insights-levels-skipped-closest = No { $level } level. Closest: { $code }
# kind=sentence
insights-levels-no-guide = No level guide for { $company } yet.
# kind=sentence
insights-levels-same-as = Shares the levels of { $company }.
# kind=sentence
insights-levels-followed-without-guide = { $count ->
    [one] { $count } company you follow has no level guide yet.
   *[other] { $count } companies you follow have no level guide yet.
}
# kind=heading
insights-levels-empty = No company or level matches
# kind=button
insights-levels-reset = Reset all

## features/statistics/CompensationPanel.tsx: posted pay
# kind=label note="The Pay tab's headline: the median low to the median high of the posted base ranges at one level"
insights-posted-typically = Typically { $low } to { $high }
# kind=label note="The headline when a level has some ranges but fewer than the minimums"
insights-posted-too-few = Too few ranges yet
# kind=label note="The headline when no role in the country posts a range at the level"
insights-posted-none = No posted ranges yet
# kind=status note="Under the headline: what the figure rests on"
insights-posted-line = Posted base salary for { $level } roles in { $country }: { $ranges ->
    [one] { $ranges } range
   *[other] { $ranges } ranges
} from { $employers ->
    [one] { $employers } employer
   *[other] { $employers } employers
}, { $roles ->
    [one] { $roles } role
   *[other] { $roles } roles
}.
# kind=sentence
insights-posted-needs = A typical range needs at least { $min_employers } employers and { $min_ranges } ranges at one level.
# kind=sentence
insights-posted-none-at-level = No open role in { $country } posts a yearly base salary range at this level yet.
# kind=sentence
insights-posted-none-in-country = No open role in { $country } posts a yearly base salary range at a placed level yet.
# kind=sentence
insights-posted-none-anywhere = No open role posts a yearly base salary range yet.
# kind=aria
insights-posted-how-read = How the typical range is read
# kind=sentence
insights-posted-how-read-body = Each distinct range counts once, however many roles share it. The typical range runs from the median low to the median high, and the middle half spans the middle 50% of the ranges' midpoints. Yearly base salary only, in the country's own currency, never converted. Roles whose level was read from their range are left out.
# kind=label
insights-posted-middle-half = Middle half
# kind=label note="Under the middle half: what it is measured on"
insights-posted-midpoints = Range midpoints
# kind=label note="A headline tile: the share of checked open roles that post a range"
insights-posted-share = Share posting a range
# kind=status note="Under the share posting a range: the tile counts every country and level, whatever the pickers show"
insights-posted-checked = { $checked ->
    [one] { $checked } role checked, all countries and levels
   *[other] { $checked } roles checked, all countries and levels
}
# kind=label
insights-posted-country = Country
# kind=label
insights-posted-level = Level
# kind=label note="A country in the picker that holds one of the person's places"
insights-posted-your-place = { $name }, your place
# kind=heading
insights-posted-by-level = Posted base salary by level in { $country }
# kind=label note="A tag on a row the person picked as their level"
insights-posted-your-level = Your level
# kind=sentence
insights-posted-not-placed = Level not placed: { $roles ->
    [one] { $roles } role
   *[other] { $roles } roles
} on { $ranges ->
    [one] { $ranges } range
   *[other] { $ranges } ranges
}, counted apart from every level.
# kind=sentence
insights-posted-other-currency = { $count ->
    [one] { $count } more role posts its range in another currency, never converted.
   *[other] { $count } more roles post their range in another currency, never converted.
}
# kind=label note="Eyebrow over every panel built from the estimate, which reads US pay only"
insights-posted-estimate-us-only = Estimate, US only
# kind=heading
insights-posted-every-range = Every posted range in { $country }

## features/statistics/charts/compBands.ts: posted pay
# kind=sentence note="A level's row in words, for a screen reader; $figure says whether the level has a typical range"
insights-comp-bands-level-ranges = { $label }: { $bands ->
    [one] { $bands } range
   *[other] { $bands } ranges
} from { $employers ->
    [one] { $employers } employer
   *[other] { $employers } employers
}{ $figure ->
    [none] , too few for a typical range.
   *[some] , typically { $low } to { $high }.
}
# kind=sentence
insights-comp-bands-not-base = { $count ->
    [one] { $count } more role posts a range that is total compensation or does not say, so it is not shown.
   *[other] { $count } more roles post a range that is total compensation or does not say, so they are not shown.
}
# kind=sentence
insights-comp-bands-not-yearly = { $count ->
    [one] { $count } more role posts its base salary per hour or month, so it is not on this yearly scale.
   *[other] { $count } more roles post their base salary per hour or month, so they are not on this yearly scale.
}
# kind=sentence
insights-comp-bands-implausible = { $count ->
    [one] { $count } more role posts a placeholder range, such as $1 to $2, so it is not shown.
   *[other] { $count } more roles post a placeholder range, such as $1 to $2, so they are not shown.
}
# kind=sentence
insights-comp-bands-no-country = { $count ->
    [one] { $count } more role names places in several countries or none, so no country counts it.
   *[other] { $count } more roles name places in several countries or none, so no country counts them.
}
# kind=sentence
insights-comp-bands-placed-by-pay = { $count ->
    [one] { $count } more role had its level read from its range, so it is left out.
   *[other] { $count } more roles had their level read from their range, so they are left out.
}

## features/statistics/PayTable.tsx
# kind=heading note="The company table under the Pay tab's hero"
insights-pay-table-heading = Companies hiring { $level } roles in { $country }
# kind=heading note="The company table when a skill is picked"
insights-pay-table-heading-skill = Companies hiring { $level } roles in { $country } that ask for { $skill }
# kind=label note="Column: the base salary range a company posts at the picked level"
insights-pay-table-posted = Posted base range
# kind=label note="Column: the estimate, shown where a company posts no range"
insights-pay-table-estimate = Estimate
# kind=label note="A row's figure rests on several posted ranges"
insights-pay-table-ranges = { $count ->
    [one] { $count } range
   *[other] { $count } ranges
}
# kind=status note="A company that posts a range on some of its roles at this level, not all"
insights-pay-table-some-roles = on { $posting } of { $roles } roles
# kind=label note="A row with no posted range: the company has been read and posts none"
insights-pay-table-no-range = No posted range
# kind=label note="A row with no posted range: what the company posts is total compensation"
insights-pay-table-total = Posts total compensation
# kind=status note="A row with no posted range: the posting does not say whether the range is base salary"
insights-pay-table-unclear = Range not stated as base
# kind=label note="A row with no posted range: the roles name places in more than one country"
insights-pay-table-several-countries = Covers several countries
# kind=label note="A row with no posted range: the range is per hour or per month"
insights-pay-table-not-yearly = Range not yearly
# kind=status note="A row with no posted range: the level was read from the range itself"
insights-pay-table-placed-by-pay = Level read from the range
# kind=label note="A row with no posted range: no posting of the company has been read yet"
insights-pay-table-unread = Not read yet
# kind=label note="Chip on an estimated base salary, short form; the full words are the hover"
insights-pay-table-est-base = Est. base
# kind=label note="The full words behind the Est. base chip"
insights-pay-table-est-base-full = Estimated base salary
# kind=label note="Chip on an estimated total compensation, short form; the full words are the hover"
insights-pay-table-est-tc = Est. TC
# kind=label note="The full words behind the Est. TC chip"
insights-pay-table-est-tc-full = Estimated total compensation
# kind=tooltip note="Where an estimated base salary comes from"
insights-pay-table-est-base-from = Estimated for { $level } roles in { $disciplines }, from built-in data.
# kind=tooltip note="Where an estimated total compensation comes from: the rung the figure is read at"
insights-pay-table-est-tc-from = Estimated for { $rung }, from built-in data.
# kind=tooltip note="Where an estimated total compensation comes from when no single rung was read"
insights-pay-table-est-tc-from-level = Estimated for { $level } roles, from built-in data.
# kind=sentence note="Under the table outside the US, in place of the estimate column"
insights-pay-table-estimates-us = Estimates read US pay only, so this country has none.
# kind=sentence note="Under the table: the roles of these companies whose level we cannot place"
insights-pay-table-not-placed = { $roles ->
    [one] { $roles } role
   *[other] { $roles } roles
} at { $companies ->
    [one] { $companies } company
   *[other] { $companies } companies
} have no placed level.
# kind=status note="Under a shortened table: the companies hiring at this level that post no range"
insights-pay-table-more-silent = { $count ->
    [one] { $count } more company hires at this level without posting a range.
   *[other] { $count } more companies hire at this level without posting a range.
}
# kind=label note="The skill filter with nothing picked"
insights-pay-table-any-skill = Any skill
# kind=status note="A skill filter that no longer matches 3 roles in the table"
insights-pay-table-skill-empty = No role at this level in { $country } names { $skill }.
# kind=empty note="No company hires at the picked level in the picked country"
insights-pay-table-empty = No company has an open role at this level in { $country }.
# kind=label note="A company followed as part of a set, not one the person chose"
insights-pay-table-followed-as-set = Followed with a set
# kind=aria note="A company's posted ranges, read out as text beside the strip that draws them"
insights-pay-table-ranges-read = { $company }: { $ranges }
# kind=sentence note="The table's info mark: what a row's figure rests on"
insights-pay-table-how-read = A row shows the median low to the median high of the company's distinct posted ranges at this level, in this country. An estimate shows only where a company posts no range, and never sets the order. Equity names what the employer states.
# kind=aria
insights-pay-table-about = How a company's row is read

## features/statistics/PayDisciplines.tsx
# kind=heading note="The advanced-view comparison of disciplines within one level"
insights-pay-discipline-heading = Posted base salary by discipline for { $level } roles in { $country }
# kind=label note="A tag on the discipline the person picked in the filter"
insights-pay-discipline-yours = Your discipline
# kind=status note="A discipline with too few employers or ranges to show a figure"
insights-pay-discipline-too-few = { $families }: too few employers post a range for a figure to hold.
# kind=status note="A discipline where one employer posts most of the ranges"
insights-pay-discipline-one-employer = { $families }: one employer posts most of the ranges, so no figure holds.
# kind=sentence note="Under the comparison: a gap between disciplines also reflects which companies hire each one"
insights-pay-discipline-note = A gap between disciplines also reflects which companies hire each one, not pay alone.
# kind=status note="A discipline's range count and employers"
insights-pay-discipline-counts = { $ranges ->
    [one] { $ranges } range
   *[other] { $ranges } ranges
} from { $employers ->
    [one] { $employers } employer
   *[other] { $employers } employers
}
# kind=status note="While the company table's own read is in flight"
insights-pay-table-loading = Loading the companies at this level…
# kind=heading note="The company table's read failed"
insights-pay-table-load-failed = Couldn't load the companies at this level
