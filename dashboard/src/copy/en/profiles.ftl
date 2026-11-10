## profiles: moved as it was found (wording=as-is)

## features/company-profiles/CompanyOffices.tsx
# kind=sentence wording=as-is
profiles-company-offices-no-office-matches-that-search = No office matches that search.
# kind=label wording=as-is
profiles-company-offices-hq = HQ
# kind=label wording=as-is
profiles-company-offices-open = { $open_count } open
# kind=label wording=as-is
profiles-company-offices-location-not-mapped = Location not mapped
# kind=label wording=as-is
profiles-company-offices-search-cities = Search cities
# kind=label wording=as-is
profiles-company-offices-search-cities-2 = Search cities…
# kind=label wording=as-is
profiles-company-offices-country = Country
# kind=label wording=as-is
profiles-company-offices-cities = { $count ->
    [one] city
   *[other] cities
}
# kind=label wording=as-is
profiles-company-offices-text = { $choice ->
    [yes] { $shownCities } of { $length } cities
   *[no] { $length2 } { $value }
}
# kind=label wording=as-is
profiles-company-offices-offices-in = Offices in { $label }
# kind=label wording=as-is
profiles-company-offices-show-fewer = { $choice ->
    [yes] Show { $hidden } more in { $label }
   *[no] Show fewer
}

## features/company-profiles/CompanyProfilePanel.tsx
# kind=label wording=as-is
profiles-company-profile-panel-says = { $source_label } says { $value }
# kind=label wording=as-is
profiles-company-profile-panel-conflicting-signal = Conflicting signal:
# kind=sentence
profiles-company-profile-panel-no-level-in-this-company = No level in this company's ladder is matched to a standard level yet.
# kind=heading note="Over the ghost rows holding the room of a company's comp table that has no rows yet"
profiles-company-profile-panel-no-comp-bands-yet = No comp bands yet
# kind=label
profiles-company-profile-panel-band = Level
# kind=label
profiles-company-profile-panel-level = Company level
# kind=label
profiles-company-profile-panel-total-comp = TC
# kind=label wording=as-is
profiles-company-profile-panel-composition = Composition
# kind=label
profiles-company-profile-panel-stock = Equity
# kind=heading wording=as-is
profiles-company-profile-panel-profile-unavailable = Profile unavailable
# kind=button
profiles-company-profile-panel-retry = Try again
# kind=button wording=as-is
profiles-company-profile-panel-open = { $open_roles } open
# kind=label
profiles-company-profile-panel-not-on-your-board = Not on your radar
# kind=label wording=as-is
profiles-company-profile-panel-0-open = 0 open
# kind=sentence
profiles-company-profile-panel-values-come-from-the-source = From the source named at the bottom, unless marked. When sources disagree, the most trusted wins.
# kind=heading wording=as-is
profiles-company-profile-panel-offices-open-roles = Offices & open roles
# kind=label wording=as-is
profiles-company-profile-panel-countries = { $count ->
    [one] { $countryCount } country
   *[other] { $countryCount } countries
}
# kind=sentence
profiles-company-profile-panel-where-this-company-is-hiring = From this company's open postings.
# kind=heading
profiles-company-profile-panel-comp-baseline = Comp bands
# kind=label wording=as-is
profiles-company-profile-panel-base = Base
# kind=label wording=as-is
profiles-company-profile-panel-bonus = Bonus
# kind=sentence
profiles-company-profile-panel-what-a-role-at-each = What a role at each level pays, and how much of it is equity rather than cash.
# kind=sentence note="After the Estimated pay section's intro, from the equity policy in RoleBand's own data, never from a level's figures. $rule: none (the company grants no stock), election (each employee chooses how much of their pay comes as stock)"
profiles-equity-policy = { $rule ->
    [none] This company grants no equity, so its compensation does not move with the stock price.
   *[election] Each employee chooses how much of their compensation comes as equity, so how much it moves with the stock price is up to them.
}
# kind=heading wording=as-is
profiles-company-profile-panel-benefits = Benefits
# kind=tooltip
profiles-company-profile-panel-base-stock-bonus = base { $base_usd } · equity { $stock_usd } · bonus { $bonus_usd }
# kind=tooltip wording=as-is
profiles-company-profile-panel-see-open-roles = See open roles
# kind=label wording=as-is
profiles-company-profile-panel-see-open-roles-at = { $count ->
    [one] See { $open_roles } open role at { $display_name }
   *[other] See { $open_roles } open roles at { $display_name }
}
# kind=status
profiles-company-profile-panel-loading = Loading this company's profile…

## features/company-profiles/CompanyProfilesView.tsx
# kind=label wording=as-is
profiles-company-profiles-view-to-see = to see{ $value }
# kind=button wording=as-is
profiles-company-profiles-view-show-all-companies = Show all companies
# kind=sentence wording=as-is
profiles-company-profiles-view-to-start-over = to start over.
# kind=button wording=as-is
profiles-company-profiles-view-clear-the-search = Clear the search
# kind=heading wording=as-is
profiles-company-profiles-view-companies-unavailable = Companies unavailable
# kind=error
profiles-company-profiles-view-could-not-load-companies = Couldn't load your companies. Try again.
# kind=status
profiles-company-profiles-view-loading-companies = Loading your companies…
# kind=sentence
profiles-company-profiles-view-track-one-in-and-its = Follow one in { $link } to see its comp bands, equity and headcount here, with sources.
# kind=link
profiles-company-profiles-view-settings-companies = Settings › Followed companies
# kind=label wording=as-is
profiles-company-profiles-view-all-profiles-current = all profiles current
# kind=button wording=as-is
profiles-company-profiles-view-show-all = Show all
# kind=label wording=as-is
profiles-company-profiles-view-needs-review-only = Needs review only
# kind=button
profiles-company-profiles-view-enrich-fields = Edit details
# kind=heading
profiles-roster-dataset = Researched companies
# kind=sentence
profiles-roster-dataset-hint = Levels and offer terms, researched company by company.
# kind=label
profiles-roster-no-sector = Not in a sector
# kind=sentence
profiles-roster-other-hint = Followed from the wider market.
# kind=sentence wording=as-is
profiles-company-profiles-view-no-companies-to-show = { $choice ->
    [v1] No flagged company matches “{ $query }”.
    [v2] No company matches “{ $query2 }”.
    [v3] Nothing needs review right now.
   *[v4] No companies to show.
}
# kind=label wording=as-is
profiles-company-profiles-view-match = { $count ->
    [one] matches
   *[other] match
}
# kind=label wording=as-is
profiles-company-profiles-view-all = { $choice ->
    [yes] the { $released } that { $value }
   *[no] all { $released2 }
}
# kind=heading wording=as-is
profiles-company-profiles-view-companies = Companies
# kind=heading
profiles-company-profiles-view-you-are-not-tracking-any = You don't follow any company yet
# kind=label wording=as-is
profiles-company-profiles-view-search-companies = Search companies
# kind=label wording=as-is
profiles-company-profiles-view-find-a-company-or-ticker = Find a company or ticker
# kind=label wording=as-is
profiles-company-profiles-view-that-need-review = { $count ->
    [one] that needs review
   *[other] that need review
}
# kind=label wording=as-is
profiles-company-profiles-view-need-review = { $count ->
    [one] needs review
   *[other] need review
}
# kind=heading wording=as-is
profiles-company-profiles-view-back-to-every-company-profile = Back to every company profile

## features/company-profiles/FieldReview.tsx
# kind=label wording=as-is
profiles-field-review-suggested = Suggested
# kind=button wording=as-is
profiles-field-review-save = Save
# kind=error wording=as-is
profiles-field-review-couldn-t-save-it-try = Couldn't save it. Try again.
# kind=label wording=as-is
profiles-field-review-set-to-from = Set { $label } to { $field } from { $source_label }
# kind=label wording=as-is
profiles-field-review-or-enter-a-value = Or enter a value…
# kind=label wording=as-is
profiles-field-review-custom-value-for = Custom value for { $label }
# kind=label note="The first, unselectable entry of a list of answers to choose from, such as Yes and No"
profiles-field-review-or-choose-a-value = Or choose a value…
# kind=error next=none note="A count typed into a company field that is not a whole number. $example is a number written the reader's way, such as 1,200"
profiles-field-review-not-a-whole-number = Enter a whole number, like { $example }.
# kind=toast note="After the reader sets a company field by hand. $label is the field's name (Ticker, Listed), $value what it now says"
profiles-field-review-pinned = { $label } set to { $value }
# kind=toast note="After the reader drops the value they set by hand: the field shows what its sources say again. $label is the field's name"
profiles-field-unpinned = { $label } follows its sources again
# kind=button note="On a company field the reader set by hand: drop that value and show what the field's sources say"
profiles-field-use-sources = Use sources
# kind=aria note="The same button, named with its field. $label is the field's name (Ticker, Listed)"
profiles-field-use-sources-for = Use sources for { $label }
# kind=error
profiles-field-could-not-use-sources = Couldn't go back to its sources. Try again.
# kind=error
profiles-field-could-not-undo = Couldn't undo that change. Try again.

## features/company-profiles/StockPricePanel.tsx
# kind=heading wording=as-is
profiles-stock-price-panel-stock-price = Stock price
# kind=sentence wording=as-is
profiles-stock-price-panel-price-history-unavailable-right-now = Price history unavailable right now.
# kind=empty note="A listed company's empty price chart while no price key is set, over a ghost of the chart. $key is a link (shared-price-feed-get-key) to Tiingo's page that shows a free key after sign-up; the way into Settings is the button profiles-stock-price-panel-add-key beside this sentence"
profiles-stock-price-panel-needs-key = Stock prices come from Tiingo. { $key } to fill this chart.
# kind=empty note="A listed company's empty price chart once a price key is set: its daily closes are fetched within Tiingo's limits"
profiles-stock-price-panel-waiting = Prices arrive shortly, as Tiingo's limits allow.
# kind=heading note="The stock panel's empty state title, over the line that says what to do"
profiles-stock-price-panel-empty-title = No stock prices yet
# kind=label note="A range option of the stock chart. $range: m1, m3, m6, y1 (1m, 3m, 6m, 1y)"
profiles-stock-price-panel-range = { $range ->
    [m1] 1M
    [m3] 3M
    [m6] 6M
   *[y1] 1Y
}
# kind=status note="Beside the price: the day's move. $money is a signed amount (-$1.03), $percent a signed percent (-0.48%)"
profiles-stock-price-panel-day-move = { $money } ({ $percent })
# kind=status note="Beside the price: the market day it closed. $date is a calendar day"
profiles-stock-price-panel-close = Close { $date }
# kind=status note="The move across the chart's range, coloured by its sign. $move is a signed percent (+9.8%); $range: m1, m3, m6, y1 (1m, 3m, 6m, 1y)"
profiles-stock-price-panel-range-move = { $move } over { $range ->
    [m1] 1 month
    [m3] 3 months
    [m6] 6 months
   *[y1] 1 year
}
# kind=button note="Under the empty price chart, beside profiles-stock-price-panel-needs-key: opens Settings on its Plugins tab, where the Tiingo key is saved"
profiles-stock-price-panel-add-key = Add your key
# kind=label wording=as-is
profiles-stock-price-panel-price-range = Price range
# kind=label wording=as-is
profiles-stock-price-panel-stock-price-2 = { $slug } stock price, { $range }
# kind=sentence wording=as-is
profiles-stock-price-panel-daily-closes-over-latest-unknown = { $choice ->
    [yes] { $length } daily closes over { $range }, latest ${ $toFixed }.
   *[no] { $length } daily closes over { $range }, latest unknown.
}
# kind=status
profiles-stock-price-panel-loading = Loading stock prices…

## features/company-profiles/labels.ts
# kind=label wording=as-is
profiles-labels-current = Current
# kind=label wording=as-is
profiles-labels-stale = Stale
# kind=label wording=as-is
profiles-labels-conflicting-signals = Conflicting signals
# kind=label wording=as-is
profiles-labels-incomplete = Incomplete
# kind=label wording=as-is
profiles-labels-senior = Senior
# kind=label wording=as-is
profiles-labels-staff = Staff
# kind=label wording=as-is
profiles-labels-principal = Principal
# kind=label wording=as-is
profiles-labels-director = Director+
# kind=label
profiles-labels-listed = Publicly traded
# kind=label wording=as-is
profiles-labels-ticker = Ticker
# kind=label wording=as-is
profiles-labels-headcount = Headcount
# kind=label wording=as-is
profiles-labels-website = Website
# kind=label wording=as-is
profiles-labels-equity-vehicle = Equity vehicle
# kind=label wording=as-is
profiles-labels-vesting = Vesting
# kind=label wording=as-is
profiles-labels-options = Options
# kind=label wording=as-is
profiles-labels-none = None
# kind=label
profiles-labels-cash-election = Cash or equity
# kind=label
profiles-labels-one-year-grants = One-year grants
# kind=label
profiles-labels-vested-at-grant = Vested when granted
# kind=label wording=as-is
profiles-labels-sources-disagree = Sources disagree
# kind=label wording=as-is
profiles-labels-not-checked-recently = Not checked recently
# kind=label wording=as-is
profiles-labels-nothing-on-record = Nothing on record
# kind=label note="A source's claim that a company field has no value, such as no ticker"
profiles-labels-no-value = none
# kind=label note="A yes-or-no company field's value, such as whether the company is listed on a stock exchange. $answer: yes or no"
profiles-yes-no = { $answer ->
    [yes] Yes
   *[no] No
}

## Benefits on a company profile: the dataset's universal
## categories and benefit types (backend/tracker/profiles/benefits_dataset/taxonomy.json),
## named as the taxonomy names them.
# kind=name note="A benefits category; other = labels no taxonomy alias maps"
profiles-benefits-category = { $category ->
    [health_wellbeing] Health and wellbeing
    [insurance_protection] Insurance and protection
    [retirement_financial] Retirement and financial programs
    [time_off] Time off
    [family_care] Family and care
    [work_flexibility_equipment] Work flexibility and equipment
    [learning_development] Learning and development
    [mobility_housing] Mobility and housing
    [meals_workplace] Meals and workplace amenities
    [discounts_community] Discounts and community
    [company_specific] Other company benefits
   *[other] Other
}
# kind=name note="A benefit type of the taxonomy"
profiles-benefits-type = { $type ->
    [medical_insurance] Health insurance
    [dental_insurance] Dental insurance
    [vision_insurance] Vision insurance
    [health_savings_account] Health savings account (HSA)
    [flexible_spending_account] Flexible spending account (FSA)
    [employee_assistance] Employee assistance program
    [wellness_allowance] Gym or wellness reimbursement
    [onsite_gym] On-site gym
    [fitness_classes] On-site fitness classes
    [gym_discount] Gym discount
    [onsite_clinic] On-site clinic
    [life_insurance] Life insurance
    [disability_insurance] Disability insurance
    [accident_insurance] Accidental death and dismemberment (AD&D) insurance
    [travel_insurance] Business travel insurance
    [pet_insurance] Pet insurance
    [retirement_plan] Retirement plan
    [us_401k] 401(k)
    [ca_rrsp] RRSP
    [roth_retirement_option] Roth 401(k)
    [after_tax_retirement_option] Mega backdoor Roth
    [employee_share_purchase] Employee stock purchase plan (ESPP)
    [student_loan_support] Student loan repayment
    [employee_credit] Employee credit
    [vacation] Paid time off
    [sick_leave] Sick leave
    [bereavement_leave] Bereavement leave
    [sabbatical] Sabbatical
    [military_leave] Military leave
    [volunteer_leave] Volunteer time off
    [maternity_leave] Maternity leave
    [paternity_leave] Paternity leave
    [fertility_support] Fertility support
    [adoption_support] Adoption support
    [surrogacy_support] Surrogacy support
    [nursing_facilities] On-site nursing room
    [remote_work] Remote work
    [workstation_equipment] Custom workstation
    [phone_allowance] Phone bill reimbursement
    [company_phone] Company phone
    [learning_support] Learning and development
    [tuition_support] Tuition reimbursement
    [immigration_support] Immigration support
    [relocation_support] Relocation bonus
    [transport_allowance] Transport allowance
    [company_shuttle] Company shuttle
    [campus_bikes] Bikes on campus
    [public_transport] Public transit
    [housing_support] Housing stipend
    [snacks] Free snacks
    [lunch] Free lunch
    [drinks] Free drinks
    [breakfast] Free breakfast
    [dinner] Free dinner
    [pet_friendly_workplace] Pet-friendly workplace
    [inclusive_facilities] Gender-neutral bathrooms
    [onsite_laundry] On-site laundry
    [onsite_shops] On-site employee store
    [vehicle_maintenance] On-site tire replacement
    [vehicle_cleaning] On-site car wash
    [employee_discounts] Employee discounts
    [charitable_matching] Donation matching
    [referral_bonus] Referral bonus
    [company_specific_perk] Unique perk
    [pandemic_support] COVID-related benefits
    [parental_leave] Parental leave
    [paid_holidays] Paid holidays
    [flexible_hours] Flexible hours
    [hybrid_work] Hybrid work
    [home_office_allowance] Home office allowance
    [mental_health_support] Mental health support
    [childcare_support] Childcare support
    [caregiver_leave] Caregiver leave
    [food_allowance] Food allowance
    [financial_advice] Financial advice
   *[other] Other
}
# kind=label note="The country a benefit record applies to"
profiles-benefits-in-country = In { $country }

## How offers are built (levels.pay.profile_offer) and benefits trust
# kind=heading
profiles-offer-heading = How offers are built
# kind=sentence
profiles-offer-sub = How this company puts compensation together, as the employer states it or employees report it.
# kind=empty
profiles-offer-not-researched = How this company builds offers hasn't been researched yet.
# kind=label
profiles-offer-searched-not-found = Searched, not found
# kind=status
profiles-offer-checked = Checked { $date }
# kind=label
profiles-offer-fact = { $fact ->
    [equity_rule] Equity
    [bonus_rule] Annual bonus
    [annual_refresh] Refresh grants
    [sign_on_bridges_vesting] Sign-on bonus
   *[base_cap_usd] Base salary cap
}
# kind=label
profiles-offer-equity-rule = { $rule ->
    [dollar_grant_by_level] Dollar grant by level
    [tc_target_minus_base] Tops up target compensation
    [employee_election] You choose the mix
   *[none] No equity
}
# kind=label
profiles-offer-bonus-rule = { $rule ->
    [pct_of_base] Set share of base
   *[none] No annual bonus
}
# kind=label
profiles-offer-refresh = { $choice ->
    [yes] Yearly, by performance
   *[no] No yearly refresh
}
# kind=label
profiles-offer-sign-on = Offsets back-loaded vesting
# kind=sentence
profiles-benefits-unreviewed = Collected as found and not reviewed yet.
# kind=sentence
profiles-benefits-unscoped = Where a benefit applies isn't recorded unless a country is shown.
# kind=sentence note="Under Estimated pay when RoleBand's own data answers pay. $stock: yes when the company has stock in our data"
profiles-level-base-sub = { $stock ->
    [yes] Estimated base, bonus and equity at each level of its software engineering ladder. A total shows only where every part is known.
   *[no] Estimated base and bonus at each level of its software engineering ladder. Equity isn't known yet, so there's no total.
}
# kind=label note="A level's annual bonus from the company's stated policy. $choice: pct (a target share of base), none (no annual bonus), unknown (policy not known)"
profiles-level-base-bonus = { $choice ->
    [pct] { $amount } ({ $pct } target)
    [none] No annual bonus
   *[unknown] Not known
}
# kind=label note="Beside a level whose base is lower than the level under it"
profiles-level-base-below-lower = Below the lower level
# kind=label note="A level's stock or total that our data does not hold"
profiles-level-base-unknown = Not known
# kind=label note="Stock at a company whose pay policy grants none"
profiles-level-base-no-stock = No equity
# kind=label note="In the Company level column, for a level the company's ladder skips. $level: the level's name, such as Staff"
profiles-level-base-no-code = No { $level } level
# kind=empty
profiles-level-base-none = No base salaries yet for this company's software engineering levels.
# kind=label
profiles-benefits-estimate = { $value }/yr, estimated
# kind=label note="How often the company's postings name this benefit. $count counts capture blocks, not separate sources"
profiles-benefits-mentions = { $count ->
    [one] Once in its postings
   *[other] { $count } times in postings
}
# kind=button note="Opens the other wordings of one benefit, recorded from other sources or postings"
profiles-benefits-other-wordings = { $open ->
    [yes] Hide other wordings
   *[no] { $count ->
        [one] { $count } other wording
       *[other] { $count } other wordings
    }
}
# kind=label note="Benefits recorded by name only, with no terms. $names is a list of benefit names"
profiles-benefits-also-listed = Also listed: { $names }
# kind=heading note="Sentences from the company's postings that name several benefits at once, shown once here instead of under each benefit"
profiles-benefits-shared = Said of several benefits in its postings
# kind=empty
profiles-benefits-not-collected = Benefits for this company aren't collected yet. That doesn't mean it offers none.
# kind=empty note="A plugin answers this part of every profile and has not read this company yet; RoleBand's own data is never shown in its place. $plugin is the plugin's own name"
profiles-not-covered = { $plugin } hasn't read this company yet. Turn it off in Settings › Plugins to see the built-in data.
# kind=status note="Company size while a plugin answers it and has not read this company yet; RoleBand's own figure is never shown in its place. $plugin is the plugin's own name"
profiles-field-not-covered = Not read by { $plugin } yet
