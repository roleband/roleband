## companies: moved as it was found (wording=as-is)

## features/companies/AddMoreCompanies.tsx
# kind=heading wording=as-is
companies-add-more-companies-add-more-companies = Add more companies
# kind=button wording=as-is
companies-add-more-companies-add-by-link = Add by link
# kind=button wording=as-is
companies-add-more-companies-stop-scanning = Stop scanning
# kind=button wording=as-is
companies-add-more-companies-find-the-ones-hiring-for = Find the ones hiring for you
# kind=heading wording=as-is
companies-add-more-companies-add-a-company-by-link = Add a company by link
# kind=label wording=as-is
companies-add-more-companies-company-name = Company name
# kind=label wording=as-is
companies-add-more-companies-careers-page-link = Careers page link
# kind=button wording=as-is
companies-add-more-companies-cancel = Cancel
# kind=heading wording=as-is
companies-add-more-companies-a-specific-company = A specific company
# kind=label
companies-add-more-companies-added-by-its-careers-page = By careers page link
# kind=sentence wording=as-is
companies-add-more-companies-not-on-this-list-paste = Not on this list? Paste the link and you'll see whether it can be scanned.
# kind=label wording=as-is
companies-add-more-companies-the-wider-market = The wider market
# kind=aria wording=as-is
companies-add-more-companies-stop-scanning-the-wider-market = Stop scanning the wider market
# kind=heading wording=as-is
companies-add-more-companies-the-wider-market-heading = The wider market
# kind=status
companies-add-more-companies-about-companies-on-the-same = About { $about } more companies that can be scanned
# kind=sentence
companies-add-more-companies-each-one-is-checked-daily = Each one is scanned daily, and only the ones hiring for roles on your radar join your list.
# kind=label wording=as-is note="$scan is paused while the computer runs on battery"
companies-add-more-companies-first-scan-state = { $scan ->
    [paused] About { $about } companies, first scan paused on battery
   *[running] About { $about } companies, first scan running
}
# kind=sentence
companies-add-more-companies-first-scan-note = { $scan ->
    [paused] Resumes when you plug in. Companies found so far are under Other companies.
   *[running] Companies hiring for you appear under Other companies. The scan continues if you leave this page.
}
# kind=label wording=as-is
companies-add-more-companies-scanned-of-about = scanned of about { $to_check }
# kind=label wording=as-is
companies-add-more-companies-hiring-for-you-so-far = hiring for you so far
# kind=label wording=as-is
companies-add-more-companies-companies-scanned = Companies scanned
# kind=status
companies-add-more-companies-about-companies-checked-daily = About { $about } companies, scanned daily
# kind=sentence
companies-add-more-companies-daily-check-note = { $scan ->
    [paused] Paused on battery. Daily scans resume when you plug in.
   *[running] Quiet ones are scanned again tomorrow.
}
# kind=label wording=as-is
companies-add-more-companies-hiring-for-you = hiring for you
# kind=label wording=as-is
companies-add-more-companies-quiet-today = quiet today
# kind=error next=none note="The first sentence of a failure: why it failed follows, from the failure's code, or Try again. when nothing explains it"
companies-add-more-companies-couldn-t-add-that-company = Couldn't add that company.
# kind=error
companies-add-more-companies-try-again = Try again.
# kind=label wording=as-is
companies-add-more-companies-add-by-link-dialog = Add a company by link
# kind=label wording=as-is
companies-add-more-companies-acme = Acme
# kind=aria wording=as-is
companies-add-more-companies-careers-page-link-aria = Careers page link
# kind=label wording=as-is
companies-add-more-companies-add-company = { $state ->
    [adding] Adding…
   *[idle] Add company
}

## features/companies/CompaniesData.tsx
# kind=label wording=as-is
companies-data-undo = Undo
# kind=error next=none note="The first sentence of a failure: why it failed follows, from the failure's code, or Try again. when nothing explains it"
companies-data-couldn-t-undo-that-change = Couldn't undo that change.
# kind=sentence wording=as-is
companies-data-change-undone = Change undone.
# kind=error next=none note="$name is a company or a sector. The first sentence of a failure: why it failed follows, from the failure's code, or Try again. when nothing explains it"
companies-data-follow-failed = { $direction ->
    [follow] Couldn't follow { $name }.
   *[unfollow] Couldn't unfollow { $name }.
}
# kind=sentence
companies-data-unfollowed = Stopped following { $display }.
# kind=sentence note="$coverage is covered when RoleBand can already read the company's careers page"
companies-data-followed = { $coverage ->
    [covered] Following { $company }.
   *[uncovered] Following { $company }. Scanning starts as soon as its careers page can be read.
}
# kind=toast note="Following or unfollowing every company shown in a sector; $paused counts the ones RoleBand cannot scan yet"
companies-data-sector-follow-result = { $direction ->
    [follow] Following every company shown in { $sector }.{ $paused ->
        [0] { "" }
        [one] { " " }{ $paused } isn't scanned yet.
       *[other] { " " }{ $paused } aren't scanned yet.
    }
   *[unfollow] Stopped following { $sector }.
}
# kind=sentence note="Scanning the wider market: waiting for power, scanning, or stopped; $added counts the companies the scan had added"
companies-data-wider-market-result = { $state ->
    [waiting] On battery: the scan of about { $size } more companies starts when you plug in.
    [scanning] Scanning about { $size } more companies, best-known first.
   *[stopped] Stopped scanning.{ $added ->
        [0] { "" }
        [one] { " " }The { $added } company it added is no longer followed.
       *[other] { " " }The { $added } companies it added are no longer followed.
    }
}
# kind=error next=none note="The first sentence of a failure: why it failed follows, from the failure's code, or Try again. when nothing explains it"
companies-data-wider-market-failed = { $direction ->
    [start] Couldn't start scanning the wider market.
   *[stop] Couldn't stop scanning the wider market.
}
# kind=error next=none note="The first sentence of a failure: why it failed follows, from the failure's code, or Try again. when nothing explains it"
companies-data-curated-follow-failed = { $direction ->
    [follow] Couldn't follow the { $count ->
        [one] company
       *[other] companies
    }.
   *[unfollow] Couldn't unfollow the { $count ->
        [one] company
       *[other] companies
    } outside your { $curatedList }.
}
# kind=sentence
companies-data-curated-follow-result = { $direction ->
    [follow] Following { $count } more { $count ->
        [one] company
       *[other] companies
    }.
   *[unfollow] Stopped following { $count } { $count ->
        [one] company
       *[other] companies
    } outside your { $curatedList }.
}
# kind=error next=none note="$visibility is the state the write asked for. The first sentence of a failure: why it failed follows, from the failure's code, or Try again. when nothing explains it"
companies-data-visibility-failed = { $visibility ->
    [shown] Couldn't put { $company } back on your radar.
   *[hidden] Couldn't hide { $company } from your radar.
}
# kind=sentence wording=as-is note="$visibility is the state the company now has"
companies-data-visibility-changed = { $visibility ->
    [hidden] { $company } hidden from your radar.
   *[shown] { $company } back on your radar.
}
# kind=error next=none note="$state is the choice the write asked for: schedule or request. The first sentence of a failure: why it failed follows, from the failure's code, or Try again. when nothing explains it"
companies-data-keep-scanning-failed = { $state ->
    [schedule] Couldn't add { $company } to your scan schedule.
   *[request] Couldn't take { $company } off your scan schedule.
}
# kind=toast note="$state is the choice the company now has: schedule or request"
companies-data-keep-scanning-changed = { $state ->
    [schedule] { $company } is scanned on your schedule.
   *[request] { $company } is scanned when you ask.
}
# kind=sentence note="Added after a follow when the job site the followed companies use is paused or turned off, so their first scan cannot start yet"
companies-data-reads-waiting = { $count ->
    [one] Its first scan waits until its job site can be scanned again.
   *[other] Their first scans wait until their job site can be scanned again.
}
# kind=toast note="After answering the review of followed companies that wait for consent: how many are still followed"
companies-data-review-kept = { $count ->
    [one] Following { $count } company.
   *[other] Following { $count } companies.
}
# kind=toast note="After answering the review of followed companies that wait for consent: how many the person chose to unfollow"
companies-data-review-dropped = { $count ->
    [one] Stopped following { $count } company.
   *[other] Stopped following { $count } companies.
}
# kind=error next=none note="The first sentence of a failure: why it failed follows, from the failure's code, or Try again. when nothing explains it"
companies-data-review-failed = Couldn't save your answer. Nothing changed.
# kind=sentence
companies-data-company-added-to-your-roster = Company added to Followed companies.

## features/companies/CompaniesIndex.tsx
# kind=label wording=as-is
companies-index-sectors = Sectors
# kind=label wording=as-is
companies-index-add-more-companies = Add more companies
# kind=aria wording=as-is
companies-index-sectors-aria = Sectors

## features/companies/CompaniesSection.tsx
# kind=label wording=as-is
companies-section-loading-companies = Loading companies…
# kind=label wording=as-is
companies-section-company = Company
# kind=label wording=as-is
companies-section-coverage = Coverage
# kind=label wording=as-is
companies-section-open = Open
# kind=aria wording=as-is
companies-section-companies = Companies
# kind=heading
companies-section-load-failed = Couldn't load companies
# kind=sentence
companies-section-refresh-failed = Couldn't update companies. Showing the last result.

## features/companies/CompanyRegisterRows.tsx
# kind=label wording=as-is note="$mark is a dot shown when the count leaves roles out, explained on hover"
companies-company-register-rows-open-count = { $count } open{ $mark }
# kind=label wording=as-is
companies-company-register-rows-aka = aka { $aliasHit }
# kind=label wording=as-is
companies-company-register-rows-limits-collection = limits collection
# kind=label wording=as-is
companies-company-register-rows-also = also { $name }
# kind=sentence wording=as-is
companies-company-register-rows-showing-of-matches-keep-typing = Showing { $shown } of { $matchCount } matches. Keep typing to narrow the list.
# kind=label wording=as-is
companies-company-register-rows-planned = Planned
# kind=label
companies-company-register-rows-waiting-to-scan = Waiting to scan
# kind=label wording=as-is note="Why a followed company's coverage needs attention, from the coverage cause"
companies-company-register-rows-coverage-problem = { $cause ->
    [empty_listing] Lists no roles
    [board_missing] Careers page gone
   *[other] Couldn't scan
}
# kind=label wording=as-is
companies-company-register-rows-blocked = Blocked
# kind=label wording=as-is
companies-company-register-rows-needs-consent = Needs consent
# kind=label wording=as-is note="$connector is the company's connector state; every state here but ready is live"
companies-company-register-rows-live-or-ready = { $connector ->
    [ready] Ready
   *[other] Live
}
# kind=sentence wording=as-is
companies-company-register-rows-scanned-ago = Scanned { $scanned } ago.
# kind=label wording=as-is
companies-company-register-rows-label-scanned-ago = { $label } · scanned { $scanned } ago
# kind=sentence
companies-company-register-rows-scanned-ago-roleband-scans-when = Scanned { $scanned } ago. { $display } is scanned when you choose Scan now.
# kind=status
companies-company-register-rows-not-counted-last-read-ago = { $label } · not counted, last scanned { $lastRead } ago
# kind=sentence
companies-company-register-rows-roleband-last-read-s-roles = Roles at { $display } come from a scan { $lastRead } ago, too old to count. They count again after its next full scan.
# kind=label wording=as-is
companies-company-register-rows-partly-counted = { $label } · partly counted
# kind=sentence
companies-company-register-rows-s-scans-have-not-read = Some roles at { $display } aren't counted yet. They count after its next full scan.
# kind=label wording=as-is
companies-company-register-rows-not-counted-yet = { $label } · not counted yet
# kind=sentence note="$reason is why the company's roles are not in the radar's count"
companies-company-register-rows-not-counted-why = { $reason ->
    [stale] Roles at { $company } come from an older scan. They count after its next full scan.
   *[other] Roles at { $company } count after its next scan.
}
# kind=label wording=as-is
companies-company-register-rows-following-not-scanned-yet = Following · not scanned yet
# kind=sentence
companies-company-register-rows-roleband-starts-scanning-as-soon = Scanning { $display } starts as soon as its careers page can be read.
# kind=tooltip wording=as-is
companies-company-register-rows-open-role-counts-are-unavailable = Open role counts are unavailable
# kind=label wording=as-is
companies-company-register-rows-open-roles-loading = Open roles loading
# kind=sentence
companies-company-register-rows-of-s-roles-name-a = { $unplaced } of the roles at { $display } name a place that isn't recognized, so they don't show for any place you choose.
# kind=sentence
companies-company-register-rows-of-s-roles-fit-no = { $unsorted } of the roles at { $display } fit no known discipline, so they don't show for any discipline you choose.
# kind=label
companies-company-register-rows-open-careers-page = Open careers page: { $display }
# kind=tooltip wording=as-is
companies-company-register-rows-careers-page = Careers page
# kind=aria note="The eye button: $visibility is the company's state now"
companies-company-register-rows-show-or-hide-on-radar = { $visibility ->
    [shown] Hide { $company } from your radar
   *[hidden] Show { $company } on your radar
}
# kind=label wording=as-is
companies-company-register-rows-radar-visibility = { $visibility ->
    [shown] On your radar
   *[hidden] Hidden from your radar
}
# kind=aria note="The schedule button of a company scanned only at its person's direction: $state is the company's choice now, schedule or request"
companies-company-register-rows-keep-scanning = { $state ->
    [schedule] Stop scanning { $company } on schedule
   *[request] Scan { $company } on schedule
}
# kind=tooltip note="$state is the company's choice now: schedule or request"
companies-company-register-rows-keep-scanning-state = { $state ->
    [schedule] Scanned on your schedule
   *[request] Scanned when you ask
}
# kind=label wording=as-is
companies-company-register-rows-scan-now = Scan { $display } now
# kind=tooltip note="While a scan runs, the company joins it and is read next"
companies-company-register-rows-scan-now-hint = { $scan ->
    [running] Add to the running scan
    [waiting] A scan is already queued
   *[idle] Scan this company now
}
# kind=toast
companies-company-register-rows-scan-joined = { $display } is next in the running scan.
# kind=label wording=as-is
companies-company-register-rows-scanning = Scanning { $display }…
# kind=error
companies-company-register-rows-couldn-t-start-a-scan = Couldn't start a scan for { $display }. Try again.
# kind=label wording=as-is
companies-company-register-rows-followed = { $followed }/{ $total } followed
# kind=toast wording=as-is
companies-company-register-rows-covered-count = { $coverage ->
    [none] none covered
   *[some] { $covered } covered
}
# kind=toast wording=as-is
companies-company-register-rows-planned-hidden = { $hiddenPlanned } planned hidden
# kind=label wording=as-is
companies-company-register-rows-sector-follow-all = { $direction ->
    [unfollow] Unfollow all { $sector } companies
   *[follow] Follow all { $sector } companies
}
# kind=status note="Why a sector has nothing to follow: $coverage is none when RoleBand can scan none of its companies"
companies-company-register-rows-nothing-to-follow-why = { $coverage ->
    [none] No company in this sector can be scanned yet
   *[some] No company here matches your filters
}
# kind=label wording=as-is
companies-company-register-rows-sector-action = { $action ->
    [none] Nothing to follow
    [unfollow] Unfollow all
   *[follow] Follow all
}

## features/companies/CuratedList.tsx
# kind=label wording=as-is
companies-curated-list-confirm = Confirm

## features/companies/RegisterChrome.tsx
# kind=label wording=as-is
companies-register-chrome-followed-companies-wait-for-your = { $count ->
    [one] { $count } followed company waits for your consent
   *[other] { $count } followed companies wait for your consent
}
# kind=sentence
companies-register-chrome-roleband-doesn-t-scan-them = { $count ->
    [one] It isn't scanned until you answer.
   *[other] They aren't scanned until you answer.
}
# kind=button note="Opens one question for every followed company that waits for consent"
companies-register-chrome-review = Review
# kind=label wording=as-is
companies-register-chrome-companies-failed-the-last-scan = { $count ->
    [one] { $count } company failed the last scan
   *[other] { $count } companies failed the last scan
}
# kind=button wording=as-is
companies-register-chrome-rescan = Rescan { $count }
# kind=label wording=as-is note="The toolbar's counts: $followed, $openRoles, $live and $ready are the figures, $sep the dot between them"
companies-register-chrome-toolbar-stats = { $followed } of { $total } followed { $sep } { $openRoles } open roles { $sep } { $live } live { $sep } { $ready } ready
# kind=label wording=as-is
companies-register-chrome-following-only = Following only
# kind=label wording=as-is
companies-register-chrome-show-planned = Show planned
# kind=button wording=as-is
companies-register-chrome-follow-all = Follow all
# kind=button wording=as-is
companies-register-chrome-curated-list-only = Curated list only
# kind=sentence wording=as-is note="$showAll is the Show all companies button; $search is query when a search also holds rows back"
companies-register-chrome-show-all-to-see = { $showAll } to see the { $released } { $search ->
        [query] { $released ->
            [one] match
           *[other] matches
        } you don't follow
       *[none] companies
    }.
# kind=button wording=as-is
companies-register-chrome-show-all-companies = Show all companies
# kind=sentence wording=as-is note="$showPlanned is the Show planned button"
companies-register-chrome-show-planned-to-see = { $showPlanned } to see { $released } more.
# kind=button wording=as-is
companies-register-chrome-show-planned-button = Show planned
# kind=sentence wording=as-is note="$clearSearch is the Clear the search button"
companies-register-chrome-clear-search-to-see = { $clearSearch } to see all { $catalogTotal }.
# kind=button wording=as-is
companies-register-chrome-clear-the-search = Clear the search
# kind=label wording=as-is
companies-register-chrome-more = { $names } +{ $more } more
# kind=label wording=as-is
companies-register-chrome-followed-companies-are-blocked = { $count ->
    [one] { $count } followed company is blocked
   *[other] { $count } followed companies are blocked
}
# kind=label wording=as-is
companies-register-chrome-followed-companies-are-not-scanned = { $count ->
    [one] { $count } followed company is not scanned yet
   *[other] { $count } followed companies are not scanned yet
}
# kind=label wording=as-is
companies-register-chrome-followed-companies-are-hidden-from = { $count ->
    [one] { $count } followed company is hidden from your radar
   *[other] { $count } followed companies are hidden from your radar
}
# kind=aria wording=as-is
companies-register-chrome-companies-needing-attention = Companies needing attention
# kind=label wording=as-is
companies-register-chrome-a-scan-is-already-running = A scan is already running
# kind=label wording=as-is
companies-register-chrome-rescanning-companies = { $count ->
    [one] Rescanning { $count } company…
   *[other] Rescanning { $count } companies…
}
# kind=error
companies-register-chrome-couldn-t-start-that-rescan = Couldn't start the rescan. Try again.
# kind=label wording=as-is
companies-register-chrome-search-companies = Search companies
# kind=label wording=as-is
companies-register-chrome-find-a-company-alias-or = Find a company, alias or sector
# kind=label wording=as-is
companies-register-chrome-a-search-shows-planned-companies = A search shows planned companies too
# kind=sentence wording=as-is note="The empty register's title, by the filters holding rows back: a search, Following only, hidden planned companies, or none"
companies-register-chrome-register-empty = { $blamed ->
    [search-following] No company you follow matches “{ $search }”.
    [search] No company matches “{ $search }”.
    [following-planned] You aren't following any covered company yet.
    [following] You aren't following any company yet.
    [planned] Every company here is planned, not covered yet.
   *[none] No companies yet.
}

## features/companies/companiesModel.ts
# kind=tooltip
companies-model-ready-to-enable = Ready: follow it to start scanning
# kind=label wording=as-is
companies-model-your-additions = Your additions
# kind=label wording=as-is
companies-model-other-companies = Other companies

## features/companies/followCopy.ts
# kind=label wording=as-is
companies-follow-copy-thousands-of-roles = thousands of roles
# kind=label wording=as-is
companies-follow-copy-hundreds-of-roles = hundreds of roles
# kind=label wording=as-is
companies-follow-copy-more-roles = more roles
# kind=heading
companies-follow-copy-follow-more = Follow the whole list?
# kind=sentence
companies-follow-copy-roleband-starts-you-with-a = Your radar starts with a { $curatedList } of well-known companies. More companies bring more roles, and each scan takes longer.
# kind=consent note="A bulk follow dialog's fact, shown only when some of the companies limit automated collection. With the dialog's other sentences, the text the server stores as this person's consent"
companies-follow-copy-some-of-these-companies-limit = Some of these companies limit automated collection on their careers sites.
# kind=consent note="Said once under a bulk follow dialog's facts, whichever of them it shows"
companies-follow-copy-by-following-them = By following them, you choose to collect their public postings.
# kind=consent note="Said once under the facts of the dialog that adds the other companies, whichever of them it shows"
companies-follow-copy-by-picking-this = By picking this, you choose to collect their public postings.
# kind=sentence note="A quiet line above the Follow the whole list answers, kept on one line"
companies-follow-copy-unfollow-any-time = Unfollow any time in Settings › Followed companies.
# kind=label wording=as-is
companies-follow-copy-keep = Keep { $curatedList }
# kind=label wording=as-is
companies-follow-copy-follow-all = Follow all { $count }
# kind=tooltip wording=as-is
companies-follow-copy-unfollow-outside-your = Unfollow { $count } { $count ->
        [one] company
       *[other] companies
    } outside your { $curatedList }?
# kind=sentence
companies-follow-copy-roleband-stops-scanning-them-your = { $count ->
    [one] Scanning it stops. Your { $curatedList }, and any company you added yourself, stays followed.
   *[other] Scanning them stops. Your { $curatedList }, and any company you added yourself, stays followed.
}
# kind=label wording=as-is
companies-follow-copy-keep-following = Keep following
# kind=heading note="Title of the question for followed companies that wait for consent. $rest counts the ones not named"
companies-follow-copy-keep-following-these = { $rest ->
    [0] Keep following { $first } and { $second }?
   *[other] Keep following { $first }, { $second } and { $rest } more?
}
# kind=heading
companies-follow-copy-keep-following-one = Keep following { $display }?
# kind=sentence note="Why followed companies wait: their careers sites changed how they can be read, and they stay unscanned until the person answers"
companies-follow-copy-sites-changed = { $count ->
    [one] Its careers site changed how it can be read. Until you answer, it isn't scanned.
   *[other] Their careers sites changed how they can be read. Until you answer, they aren't scanned.
}
# kind=button
companies-follow-copy-not-now = Not now
# kind=button note="Agrees for every company in the question; $count is how many stay followed"
companies-follow-copy-keep-following-count = Keep following { $count }
# kind=link note="Opens a list to pick which of the waiting companies to unfollow"
companies-follow-copy-let-me-choose = Let me choose
# kind=heading
companies-follow-copy-which-to-unfollow = Which companies to unfollow?
# kind=label
companies-follow-copy-find-a-company = Find a company
# kind=link note="$state is all when every company shown is ticked"
companies-follow-copy-select-all = { $state ->
    [all] Clear all
   *[some] Select all
}
# kind=aria
companies-follow-copy-companies-to-unfollow = Companies to unfollow
# kind=status
companies-follow-copy-count-to-unfollow = { $count } to unfollow
# kind=label wording=as-is
companies-follow-copy-unfollow = Unfollow { $count }
# kind=tooltip wording=as-is
companies-follow-copy-follow-all-in = Follow all { $count } { $count ->
        [one] company
       *[other] companies
    } in { $sector }?
# kind=sentence wording=as-is
companies-follow-copy-this-will-likely-add-to = This will likely add { $estimate } to your radar and make each scan longer. You can unfollow any company later.
# kind=label wording=as-is
companies-follow-copy-cancel = Cancel
# kind=tooltip wording=as-is
companies-follow-copy-follow = Follow { $display }?
# kind=consent note="The walled follow dialog's second sentence; with the site-wall sentence before it, the text the server stores as this person's consent"
companies-follow-copy-by-following-you-choose-to = By following, you choose to collect { $display }'s public postings. Unfollow at any time to stop.
# kind=label wording=as-is
companies-follow-copy-follow-company = Follow { $display }
# kind=consent note="The follow dialog for a company whose careers site is scanned only at the person's direction. With the dialog's other sentences, the text the server stores as this person's agreement"
companies-follow-copy-scanned-at-your-direction = Its careers site is scanned only at your direction.
# kind=consent note="A bulk follow dialog's fact, shown only when some of the companies are scanned only at the person's direction. With the dialog's other sentences, the text the server stores as this person's agreement"
companies-follow-copy-some-are-scanned-at-your-direction = Some of these companies' careers sites are scanned only at your direction.
# kind=label note="The follow dialog's switch, on at first: on, the companies join the scan schedule; off, they are scanned now and then when the person asks"
companies-follow-copy-keep-scanning = { $count ->
    [one] Keep scanning this company
   *[other] Keep scanning these companies
}
# kind=button note="The follow dialog's answer for companies scanned only at the person's direction: follows them and starts their scan"
companies-follow-copy-follow-and-scan = Follow and scan
# kind=tooltip wording=as-is
companies-follow-copy-scan-about-more-companies = Scan about { $about } more companies?
# kind=sentence wording=as-is
companies-follow-copy-only-companies-hiring-for-roles = Only companies hiring for roles on your radar join your followed list. The rest stay out of sight.
# kind=sentence
companies-follow-copy-roleband-scans-the-best-known = The first scan takes a few hours, best-known companies first. Then each is scanned daily, so a role that fits shows up the day it's posted.
# kind=sentence wording=as-is
companies-follow-copy-you-can-stop-at-any = You can stop at any time.
# kind=label wording=as-is
companies-follow-copy-start-scanning = Start scanning
# kind=tooltip
companies-follow-copy-follow-every-company-question = Follow the other companies too?
# kind=sentence
companies-follow-copy-your-radar-covers-the-whole = Your radar adds the other companies to the ones on the list.
# kind=sentence
companies-follow-copy-with-more-companies-scans-take = With more companies, scans take longer.
# kind=sentence
companies-follow-copy-change-it-any-time-in = Change it any time in Settings › Followed companies.
# kind=label
companies-follow-copy-follow-every-company = Follow them
# kind=tooltip wording=as-is
companies-follow-copy-unfollow-company-question = Unfollow { $display }?
# kind=sentence
companies-follow-copy-s-job-listings-stop-being = Postings from { $display } are no longer collected. You can follow it again at any time.
# kind=label wording=as-is same-as=companies-follow-copy-unfollow
companies-follow-copy-unfollow-company = Unfollow { $display }

## features/companies/CompaniesIndex.tsx
# kind=label wording=as-is note="A sector's count in the index while searching: its rows that match"
companies-index-match-count = { $count } match
# kind=label wording=as-is note="A sector's count in the index: followed of all"
companies-index-followed-of = { $followed }/{ $total }

## features/companies/CompanyRegisterRows.tsx
# kind=toast wording=as-is
companies-company-register-rows-sector-open = { $openRoles } open

## A company's connector, said from its state and, when parked, why (states from
## backend/tracker/company_discovery.py). `ready`
## is companies-model-ready-to-enable.
# kind=tooltip
companies-connector-live = Scanned automatically
# kind=tooltip
companies-connector-family = Ready: its careers page can be read
# kind=tooltip
companies-connector-active = Added by you and scanned
# kind=tooltip
companies-connector-planned = Support planned
# kind=tooltip
companies-connector-parked = Its site refuses scans
# kind=tooltip
companies-parked-bot-protected = Its careers page blocks automated reading
# kind=tooltip
companies-parked-robots-disallow = { $company } asks not to have its careers page read automatically
# kind=tooltip
companies-parked-prohibits-collection = Its careers page forbids automated collection
# kind=status note="A pending company whose careers page named a known board family: the family, and why it waits"
companies-company-register-rows-board-found = { $reason ->
    [policy_refused] Uses { $family }, which doesn't allow scanning
   *[board_silent] Uses { $family }, which didn't load
}
# kind=status note="A board family's own name, a brand: not translated, not sentence-cased"
companies-company-register-rows-board-family = { $family ->
    [jibe] Jibe
    [radancy] Radancy TalentBrew
    [avature] Avature
   *[other] { $family }
}

## First-run setup: which companies the radar scans (features/companies/SetupCompanies.tsx)

# kind=label
companies-setup-followed-now = Followed now
# kind=status note="After a list of company names: and 27 more"
companies-setup-and-more = and { $count } more
# kind=label
companies-setup-well-known = Well-known companies
# kind=status
companies-setup-well-known-detail = { $count ->
    [one] { $count } { -company(num: "one") }, first roles in minutes
   *[other] { $count } { -company(num: "other") }, first roles in minutes
}
# kind=label
companies-setup-every-listed = Every listed company
# kind=status
companies-setup-every-listed-detail = { $count ->
    [one] { $count } { -company(num: "one") } across many sectors
   *[other] { $count } { -company(num: "other") } across many sectors
}
# kind=label note="The listed companies and the other companies beyond the list"
companies-setup-everything = Plus other companies
# kind=status note="$about is a rounded count: About 12,500 more"
companies-setup-everything-detail = About { $about } more; the first scan takes a few hours
# kind=aria
companies-setup-choice-aria = Which companies are scanned
# kind=sentence
companies-setup-later = Follow or unfollow any company later in Settings › Followed companies.
# kind=status
companies-setup-load-failed = Couldn't load the company list. The well-known companies stay followed.
# kind=button
companies-setup-back = Back
# kind=button
companies-setup-start = { $choice ->
    [yes] Starting…
   *[no] Start the radar
}
