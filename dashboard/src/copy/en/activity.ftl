## The Activity screen: what connected assistant apps read, changed and were refused.

## features/intelligence/activity/ActivityScreen.tsx
# kind=label note="Over the Activity screen's title: the card in Settings › AI this screen belongs to"
activity-eyebrow = Assistant apps
# kind=heading note="The screen listing every read, change and refusal by connected assistant apps"
activity-title = Activity
# kind=button note="Opens the choices of what assistant apps may read and change"
activity-customize = Customize
# kind=aria
activity-search = Search activity
# kind=aria note="The toolbar of the Activity list's search and filters"
activity-filters = Filter activity
# kind=button note="Shows every entry, whatever its kind"
activity-kind-all = All
# kind=button note="Shows only what assistant apps changed"
activity-kind-changes = Changes
# kind=button note="Shows only what assistant apps read"
activity-kind-reads = Reads
# kind=button note="Shows only what assistant apps asked for and did not get"
activity-kind-refused = Refused
# kind=aria note="The menu that narrows the list to one kind of data"
activity-category-menu = Kind of data
# kind=button note="The kind-of-data menu's button while no kind is picked"
activity-category-any = Any data
# kind=aria note="The menu that narrows the list to a span of days"
activity-range-menu = Dates
# kind=button
activity-range-today = Today
# kind=button
activity-range-week = Last 7 days
# kind=button
activity-range-month = Last 30 days
# kind=button
activity-range-all = Any time
# kind=status
activity-loading = Loading activity…
# kind=heading
activity-load-failed = Couldn't load activity
# kind=sentence
activity-refresh-failed = Couldn't update activity. Showing the last result.
# kind=label
activity-empty-title = { $choice ->
    [yes] Nothing matches
   *[no] Nothing yet
}
# kind=sentence
activity-empty-body = { $choice ->
    [yes] No entry matches these filters.
   *[no] What connected assistant apps read and change appears here.
}

## features/intelligence/activity/ActivityList.tsx
# kind=aria note="The list of entries, grouped by day"
activity-list = Entries
# kind=label note="A day heading in the list"
activity-day-today = Today
# kind=label note="A day heading in the list"
activity-day-yesterday = Yesterday
# kind=status note="Which entries this page shows, counted from the newest: 1 to 50"
activity-page-range = { $first } to { $last }
# kind=button note="The next page: older entries"
activity-older = Older
# kind=button note="The previous page: newer entries"
activity-newer = Newer
# kind=label note="The tag on a refused entry: the kind of data was not shared"
activity-tag-not-shared = Not shared
# kind=label note="The tag on a refused entry: access or changes were switched off"
activity-tag-turned-off = Turned off
# kind=label note="The tag on a change that belongs to no kind of change"
activity-tag-change = Change

## features/intelligence/activity/activityText.ts
# kind=label note="A kind of data: the roles and their postings"
activity-category-postings = Postings
# kind=label note="A kind of data: pay estimates and market figures"
activity-category-market-statistics = Market statistics
# kind=label note="A kind of data: the roles the person saved and how far each has got, with their notes"
activity-category-progress-and-notes = Progress and notes
# kind=label note="A kind of data: the offer the person entered"
activity-category-offer = Offer
# kind=label note="A kind of data: the person's profile and aim"
activity-category-profile = Profile
# kind=label note="A kind of change: saving roles and moving them along, with notes and next steps"
activity-group-tracking-progress = Tracking progress
# kind=label note="A kind of change: notes an assistant keeps about what it found"
activity-group-keeping-findings = Keeping findings
# kind=label note="A kind of change: what the radar looks for"
activity-group-tuning-the-radar = Tuning the radar
# kind=label note="A kind of change: which companies are followed and how their postings are collected"
activity-group-controlling-collection = Controlling collection
# kind=status note="An app read postings; the count is unknown"
activity-read-postings = Read postings
# kind=status
activity-read-postings-count = { $count ->
    [one] Read { $count } posting
   *[other] Read { $count } postings
}
# kind=status
activity-read-market-statistics = Read market statistics
# kind=status
activity-read-progress = Read your progress and notes
# kind=status
activity-read-offer = Read your offer
# kind=status
activity-read-profile = Read your profile
# kind=status note="An app checked that it can reach this computer's data, and what it may do"
activity-read-connection = Checked the connection
# kind=status note="An app asked for a kind of data the person does not share"
activity-asked-postings = Asked for postings
# kind=status
activity-asked-market-statistics = Asked for market statistics
# kind=status
activity-asked-progress = Asked for your progress and notes
# kind=status
activity-asked-offer = Asked for your offer
# kind=status
activity-asked-profile = Asked for your profile
# kind=status note="An app asked while access for assistant apps was switched off"
activity-asked-while-off = Asked while access was off
# kind=status note="An app tried to change something while changes by assistant apps were switched off"
activity-tried-while-changes-off = Tried a change while changes were off
# kind=status note="$title is a role's title and $company its company, as written"
activity-saved-role = Saved { $title } at { $company }
# kind=status note="$stage is a stage of a role the person pursues, such as Interviewing"
activity-moved-role = Moved { $title } at { $company } to { $stage }
# kind=status
activity-updated-role = Updated { $title } at { $company }
# kind=status note="A collection recipe drafted for a careers site; $recipe names the recipe"
activity-drafted-recipe = Drafted a recipe for { $recipe }
# kind=status note="A change this screen has no words for yet"
activity-made-change = Made a change

## features/intelligence/activity/ActivityInspector.tsx
# kind=aria note="The panel showing the entry picked in the list"
activity-inspector = Picked entry
# kind=status note="The panel while it reads an entry a link named, from an older page"
activity-entry-loading = Loading this entry…
# kind=sentence note="The panel when a link names an entry the log does not hold"
activity-entry-missing = This entry isn't in the activity log.
# kind=sentence
activity-entry-failed = Couldn't load this entry.
# kind=label note="The picked entry's kind and when it happened: Change · Mon, Nov 16, 14:31"
activity-inspector-when = { $kind } · { $when }
# kind=label note="The picked entry's kind: a read"
activity-kind-read = Read
# kind=label same-as=activity-tag-change note="The picked entry's kind: a change"
activity-kind-change = Change
# kind=label
activity-kind-refusal = Refused
# kind=aria
activity-what-changed = What changed
# kind=label note="A fact about the picked entry: the kind of change it belongs to"
activity-fact-group = Group
# kind=label note="A fact about the picked entry: the command the app ran"
activity-fact-operation = Operation
# kind=label same-as=activity-kind-read note="A fact about the picked entry: the kinds of data it read"
activity-fact-read = Read
# kind=label note="A fact about a refused entry: the kind of data it asked for"
activity-fact-asked-for = Asked for
# kind=label note="What an entry read, when it read none of the kinds of data"
activity-fact-nothing = Nothing of yours
# kind=label note="A field of a role the person pursues"
activity-field-stage = Stage
# kind=label
activity-field-priority = Priority
# kind=label
activity-field-notes = Notes
# kind=label
activity-field-next-action = Next step
# kind=label note="When the next step falls due"
activity-field-next-action-due = Due
# kind=label note="A recipe's draft number"
activity-field-draft = Draft
# kind=label note="A value an app removed"
activity-value-cleared = Cleared
# kind=status note="A recipe's draft number: Draft 3"
activity-value-draft = Draft { $version }

## The card on the AI tab that leads to this screen

# kind=heading same-as=activity-title note="The AI tab's card that opens the Activity screen"
activity-card-title = Activity
# kind=sentence note="What the Activity screen holds, under the card's heading on the AI tab"
activity-card-body = Each read, change and refusal by an assistant app, newest first.
# kind=link note="Opens the Activity screen from the AI tab"
activity-card-open = Open activity
