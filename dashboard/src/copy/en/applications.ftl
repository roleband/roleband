## Application pipeline (features/applications). The card's noun is
## application once the pipeline frame is set; the role's stages are the
## taxonomy's stage names.

## The board
# kind=status note="Under the page title: how many applications are moving, ended by the person, ended by the company; $needNext is the link that follows, applications-board-need-next"
applications-board-summary = { $moving } in motion · { $decided } decided · { $closed } closed · { $needNext }
# kind=link note="The summary's last part, a link that turns on the Needs a next step filter: how many past Considering have no next step or interview"
applications-board-need-next = { $count ->
        [one] { $count } needs
       *[other] { $count } need
    } a next step
# kind=heading
applications-board-load-failed = Couldn't load your pipeline
# kind=name note="The column of the endings the person chose: Accepted, Declined, Withdrawn"
applications-column-decided = Decided
# kind=name note="The column of the endings the company or the world decided: Rejected, Role closed"
applications-column-closed = Closed
# kind=empty note="The first column, Considering, while nothing is starred"
applications-column-empty-saved = Star a role on your radar to start here.
# kind=empty note="Any other column with no application in it"
applications-column-empty = Nothing here yet.
# kind=empty note="One ending's section inside Decided or Closed, with no application in it"
applications-section-empty = None yet.
# kind=status note="A column's count while filters are on: how many of its applications match"
applications-column-count-of = { $count } of { $total }
# kind=empty note="A column whose applications all fail the filters"
applications-column-no-matches = No matches.
# kind=aria note="Opens one column's menu"
applications-column-menu = { $column } column options
# kind=button
applications-column-hide = Hide column
# kind=tooltip note="Why Hide column is off: the board always shows one column"
applications-column-hide-last = One column always stays on the board

## Each view's toolbar, over the board and over Up next
# kind=aria
applications-search-label = Search applications by company or title
# kind=tooltip note="The search field's placeholder"
applications-search-placeholder = Search company or title…
# kind=button note="Beside the search while filtering: keep every card and fade the rest instead of hiding them"
applications-filter-highlight-instead = Highlight instead
# kind=button note="Clears the search and every quick filter"
applications-filter-reset = Reset all
# kind=aria note="A chip for one quick filter that is on; pressing it turns the filter off"
applications-filter-remove = Remove the filter { $filter }
# kind=aria
applications-filter-menu = Filter applications
# kind=heading
applications-filter-quick = Quick filters
# kind=label note="A quick filter: a next step whose day has passed"
applications-quick-overdue = Overdue
# kind=label note="A quick filter: a next step or interview within the next seven days"
applications-quick-due-week = Due in 7 days
# kind=label note="A quick filter: past Considering, with no next step and no interview"
applications-quick-needs-next = Needs a next step
# kind=label note="A quick filter: no activity for longer than its stage expects"
applications-quick-quiet = Gone quiet
# kind=label note="A quick filter: priority 4 or 5 of 5"
applications-quick-high-priority = Priority 4+
# kind=heading note="The filter menu's last group: what an application that does not match does"
applications-filter-while = While filtering
# kind=label
applications-mode-only = Show only matches
# kind=sentence note="Under Show only matches in the filter menu"
applications-mode-only-hint = What doesn't match leaves the view.
# kind=label
applications-mode-highlight = Highlight matches
# kind=sentence note="Under Highlight matches in the filter menu"
applications-mode-highlight-hint = Everything stays, and what doesn't match fades.
# kind=button note="Opens the column menu; also the menu's name"
applications-columns = Columns
# kind=aria note="The column menu's opener while columns are hidden; the button itself shows an eye icon and the number"
applications-columns-hidden = Columns, { $count } hidden
# kind=heading
applications-columns-show = Show columns
# kind=button
applications-columns-show-all = Show all columns
# kind=empty note="Up next while the filters match nothing due"
applications-upnext-no-matches = Nothing due matches these filters.

## A card
# kind=aria
applications-card-actions = Move or change { $title }
# kind=status note="The card's due field when the next interview is the sooner date. $offset is days from today; $date is a formatted day"
applications-card-due-interview = { $offset ->
        [0] Interview today
        [1] Interview tomorrow
       *[other] Interview { $date }
    }
# kind=status note="The card's due field when the next step's due date is the sooner date. $offset is days from today; $date is a formatted day"
applications-card-due-step = { $offset ->
        [0] Due today
        [1] Due tomorrow
       *[other] Due { $date }
    }
# kind=status
applications-card-overdue = { $days ->
        [one] 1 day overdue
       *[other] { $days } days overdue
    }
# kind=label note="The company took the posting down while the application is on the board"
applications-card-posting-closed = Posting closed
# kind=aria
applications-card-comments = { $count ->
        [one] 1 comment
       *[other] { $count } comments
    }
# kind=aria note="Shown as five dots, the first $priority filled"
applications-card-priority = Priority { $priority } of 5
# kind=label note="Days the application has spent in its stage, in a narrow card footer; the full words show on hover"
applications-card-days-short = { $days }d
# kind=tooltip
applications-card-days-in-stage = { $days ->
        [one] 1 day in this stage
       *[other] { $days } days in this stage
    }
# kind=tooltip note="The stage has gone quiet: nothing has happened to the application for $quiet days"
applications-card-quiet = { $days ->
        [one] 1 day in this stage
       *[other] { $days } days in this stage
    }, nothing new for { $quiet ->
        [one] 1 day
       *[other] { $quiet } days
    }
# kind=status note="On a card in Decided or Closed: the ending, then the stage it ended at, such as Withdrawn at Interviewing"
applications-card-ended = { $ending } at { $stage }

## A card's menu
# kind=aria
applications-menu-label = Move { $title }
# kind=label
applications-menu-move-to = Move to
# kind=button note="Only on a card in Considering: removes the star, and with it the card"
applications-menu-remove = Remove from pipeline

## A move, said after it lands
# kind=toast
applications-moved = Moved { $title } to { $stage }
# kind=toast note="A move into a column the board hides: $column is that column's name"
applications-moved-hidden = Moved { $title } to { $stage }. The { $column } column is hidden.
# kind=button
applications-move-undo = Undo
# kind=toast
applications-move-failed = Couldn't move { $title }. Try again.
# kind=toast
applications-undo-failed = Couldn't move { $title } back. Try again.
# kind=toast note="The move landed but the interview the move asked for did not save; the move's own message, with Undo, shows beside this one"
applications-move-interview-failed = Couldn't save the interview for { $title }. Add it on the application's page.
# kind=toast
applications-removed = Removed { $title } from the pipeline
# kind=toast
applications-remove-failed = Couldn't remove { $title }. Try again.

## Moving into Interviewing asks when the interview is
# kind=heading
applications-interview-title = When is the interview?
# kind=sentence
applications-interview-moves = { $company } · { $title } moves to { $stage }.
# kind=label
applications-interview-round = What round
# kind=label note="The round's name when the person names none"
applications-interview-default-label = Interview
# kind=label
applications-interview-date = Date
# kind=label
applications-interview-time = Time, if set
# kind=label
applications-interview-format = Format
# kind=label note="No format chosen"
applications-interview-format-none = Not set
# kind=label
applications-interview-format-video = Video
# kind=label
applications-interview-format-phone = Phone
# kind=label
applications-interview-format-onsite = On site
# kind=label
applications-interview-link = Link, if any
# kind=label
applications-interview-link-placeholder = Paste the meeting link
# kind=button
applications-interview-cancel = Cancel
# kind=button
applications-interview-submit = Move to { $stage }
# kind=heading
applications-interview-add-title = Add an interview
# kind=heading
applications-interview-edit-title = Edit the interview
# kind=button
applications-interview-edit-submit = Save interview
# kind=button
applications-interview-delete = Delete interview
# kind=label
applications-interview-outcome = Outcome
# kind=label note="No outcome recorded yet"
applications-interview-outcome-none = Not yet
# kind=label
applications-interview-outcome-passed = Passed
# kind=label
applications-interview-outcome-not-passed = Not passed
# kind=label
applications-interview-outcome-cancelled = Cancelled
# kind=label
applications-interview-notes = Notes
# kind=toast
applications-interview-failed = Couldn't save the interview. Try again.

## The pipeline's tabs
# kind=aria
applications-tabs-label = Pipeline views

## The List: the backlog, every role still in Considering, as a row of a table
# kind=label note="The List's column of the next interview or next step, and when it is due"
applications-list-head-next = Next step
# kind=label note="The List's last column, read to screen readers only: Not for me, Compare, the star and the row's moves"
applications-list-head-actions = Actions
# kind=heading note="The List when nothing is starred or pursued"
applications-list-empty = Nothing in your pipeline yet
# kind=sentence note="$icon is the star glyph itself"
applications-list-empty-hint = Tap the { $icon } on any role on your radar to add it here.
# kind=heading note="The List when roles are starred but none is still in Considering: work has started on every one"
applications-list-clear = Nothing waiting to start
# kind=link note="Under the cleared List: opens the Board, where the roles under way are"
applications-list-clear-board = See the roles under way on the Board
# kind=empty note="The List while the filters match no application"
applications-list-no-matches = No applications match these filters.
# kind=toast note="A row's Not for me took the role off the pipeline" same-as=compare-use-compare-controller-not-for-me
applications-list-not-for-me = Not for me · { $title }
# kind=button note="A column header's menu: the column trades places with the one shown before it"
applications-list-column-left = Move left
# kind=button note="A column header's menu: the column trades places with the one shown after it"
applications-list-column-right = Move right
# kind=button note="The Columns menu: back to the first order and the first hidden set"
applications-list-columns-reset = Reset columns

## Up next: interviews and dated next steps, by day
# kind=heading
applications-upnext-overdue = Overdue
# kind=heading note="A day's heading. $offset is days from today; $date is a formatted day"
applications-upnext-day = { $offset ->
        [0] Today
        [1] Tomorrow
       *[other] { $date }
    }
# kind=label note="$label is the round's name, as the person wrote it"
applications-upnext-interview = Interview: { $label }
# kind=label note="$step is the next step, as the person wrote it"
applications-upnext-step = Next step: { $step }
# kind=label note="When a next step that is not overdue falls due: a step is due by the end of its day"
applications-upnext-step-when = By end of day
# kind=empty
applications-upnext-empty = Nothing is due. Set a next step or add an interview on an application, and it shows here.
# kind=aria note="The month calendar beside Up next"
applications-month-label = Calendar
# kind=aria
applications-month-prev = Previous month
# kind=aria
applications-month-next = Next month
# kind=button note="Brings the calendar back to this month and picks today"
applications-month-today = Today
# kind=label note="A day's count of interview rounds, in a day's description and the legend"
applications-month-interviews = { $count ->
        [one] 1 interview
       *[other] { $count } interviews
    }
# kind=label note="A day's count of dated next steps, in a day's description"
applications-month-steps = { $count ->
        [one] 1 next step
       *[other] { $count } next steps
    }
# kind=aria note="A day in the calendar. $date is the formatted day; $summary lists what falls on it, applications-month-interviews and applications-month-steps"
applications-month-day = { $date }: { $summary }
# kind=label note="The legend's mark for an interview round" same-as=applications-interview-default-label
applications-month-legend-interview = Interview
# kind=label note="The legend's mark for a dated next step" same-as=applications-list-head-next
applications-month-legend-step = Next step
# kind=empty note="Under the calendar, for a picked day with nothing on it"
applications-month-day-empty = Nothing on this day.
# kind=heading
applications-month-failed = Couldn't load the calendar

## One application's page
# kind=aria
applications-page-bar = Application
# kind=label note="The back link to the board, with the application's stage: Pipeline is the place's short name"
applications-page-back = Pipeline / { $stage }
# kind=button
applications-page-back-board = Open the board
# kind=heading
applications-page-load-failed = Couldn't load this application
# kind=status note="Where the application stands among the cards of its column" same-as=applications-column-count-of
applications-page-place = { $index } of { $total }
# kind=aria
applications-page-previous = Previous in this column: { $title }
# kind=aria
applications-page-next = Next in this column: { $title }
# kind=aria
applications-page-more = More actions
# kind=aria
applications-page-more-label = More actions for this application
# kind=button
applications-page-copy-link = Copy link
# kind=button
applications-page-withdraw = Withdraw
# kind=toast
applications-link-copied = Link copied
# kind=toast
applications-link-copy-failed = The browser blocked copying. Copy the address from the address bar instead.
# kind=label note="The stage button in the page's header: the stage and how long the application has been in it"
applications-stage-button = { $stage } · { $days ->
        [one] 1 day
       *[other] { $days } days
    }
# kind=aria
applications-stage-menu-label = Change the stage of { $title }
# kind=toast
applications-change-failed = Couldn't save that change to { $title }. Try again.

## Where the posting's history crosses the application's
# kind=status
applications-crossing-closed = { $days ->
        [0] The posting closed on the day you applied.
        [one] The posting closed 1 day after you applied.
       *[other] The posting closed { $days } days after you applied.
    }
# kind=status
applications-crossing-reopened = { $days ->
        [0] The posting reopened on the day you applied.
        [one] The posting reopened 1 day after you applied.
       *[other] The posting reopened { $days } days after you applied.
    }
# kind=status
applications-crossing-pay = { $days ->
        [0] The pay range changed on the day you applied.
        [one] The pay range changed 1 day after you applied.
       *[other] The pay range changed { $days } days after you applied.
    }
# kind=aria
applications-crossing-dismiss = Dismiss

## Next: the next interview and the next step
# kind=heading
applications-next-title = Next
# kind=empty
applications-next-interview-none = No interview booked.
# kind=label note="An all-day interview's day"
applications-next-interview-all-day = { $date }, all day
# kind=label note="A timed interview's day and time"
applications-next-interview-at = { $date }, { $time }
# kind=label note="When an interview is, then its format"
applications-next-interview-meta = { $when } · { $format }
# kind=button note="Opens the interview's meeting link"
applications-next-interview-join = Join
# kind=aria
applications-next-interview-join-label = Join { $label }
# kind=button
applications-next-interview-edit = Edit interview
# kind=empty
applications-next-empty = No next step yet.
# kind=button
applications-next-set = Set next step
# kind=button
applications-next-edit = Edit step
# kind=button note="The page's one primary action: the next step is done"
applications-next-done = Mark done
# kind=label
applications-next-prompt = What's the next step?
# kind=label
applications-next-due = Due by, if set
# kind=button note="Leaves the next step empty after one is marked done"
applications-next-not-now = Not now
# kind=button
applications-next-save = Save step

## Notes
# kind=heading
applications-notes-title = Notes
# kind=button
applications-notes-add = Add notes
# kind=button
applications-notes-edit = Edit notes
# kind=empty
applications-notes-empty = No notes yet.
# kind=aria
applications-notes-label = Notes
# kind=button
applications-notes-more = Show all
# kind=button
applications-notes-less = Show less
# kind=button
applications-notes-save = Save notes

## Activity: comments and recorded changes
# kind=heading
applications-feed-title = Activity
# kind=aria
applications-feed-mode-label = Show
# kind=label
applications-feed-mode-comments = Comments
# kind=label
applications-feed-mode-all = All activity
# kind=empty
applications-feed-empty = No comments or changes yet.
# kind=button note="A folded run of recorded changes. $changes lists what changed, already joined"
applications-feed-fold = { $count ->
        [one] 1 update: { $changes }
       *[other] { $count } updates: { $changes }
    }
# kind=status note="A recorded change: the role was starred into the pipeline"
applications-feed-added = Added to the pipeline
# kind=status
applications-feed-added-at = Added at { $stage }
# kind=status
applications-feed-moved = Moved to { $stage }
# kind=status
applications-feed-priority = Priority changed
# kind=status
applications-feed-notes = Notes edited
# kind=status
applications-feed-next-step = Next step changed
# kind=status note="A recorded change with no field this page names"
applications-feed-updated = Updated
# kind=label note="After a recorded change an agent made"
applications-feed-by-agent = by an agent
# kind=aria
applications-comment-label = Comment
# kind=label
applications-comment-placeholder = Write what happened
# kind=button
applications-comment-submit = Comment
# kind=label
applications-comment-author-you = You
# kind=label
applications-comment-author-agent = Agent
# kind=label note="After a comment that was changed after it was posted"
applications-comment-edited = Edited
# kind=aria
applications-comment-edit = Edit comment
# kind=aria
applications-comment-delete-label = Delete comment
# kind=label
applications-comment-delete-confirm = Delete this comment?
# kind=button
applications-comment-delete = Delete
# kind=button
applications-comment-save = Save
# kind=toast
applications-comment-failed = Couldn't save your comment. Try again.
# kind=toast
applications-comment-delete-failed = Couldn't delete that comment. Try again.

## The page's right column
# kind=heading
applications-facts-application = Application
# kind=heading
applications-facts-posting = Posting
# kind=heading
applications-facts-interviews = Interviews
# kind=label
applications-fact-priority = Priority
# kind=label
applications-fact-days = In this stage
# kind=label note="How long the application has been in its stage, beside In this stage"
applications-fact-days-value = { $days ->
        [one] 1 day
       *[other] { $days } days
    }
# kind=label
applications-fact-applied = Applied
# kind=label note="The person has not applied yet" same-as=applications-interview-outcome-none
applications-fact-applied-not = Not yet
# kind=label
applications-fact-starred = Starred
# kind=label
applications-fact-starred-yes = Yes
# kind=label
applications-fact-starred-no = No
# kind=label
applications-fact-last-activity = Last activity
# kind=label
applications-fact-status = Status
# kind=label
applications-fact-status-open = Open
# kind=label
applications-fact-status-closed = Closed
# kind=label
applications-fact-pay = Pay
# kind=label
applications-fact-pay-none = Not posted
# kind=label note="Beside the pay when it changed after the person applied"
applications-fact-pay-changed = Changed
# kind=label
applications-fact-level = Level
# kind=label
applications-fact-location = Location
# kind=label
applications-fact-location-more = and { $count } more
# kind=label
applications-fact-first-seen = First seen
# kind=button note="Opens the full posting over the page"
applications-read-posting = Read the posting
# kind=button
applications-interview-add = Add interview
# kind=aria
applications-interview-edit-label = Edit { $label }
# kind=empty
applications-interviews-empty = No interviews yet.
