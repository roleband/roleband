## Application pipeline (features/applications). The card's noun is
## application once the pipeline frame is set; the role's stages are the
## taxonomy's stage names.

## The board
# kind=heading
applications-board-load-failed = Couldn't load your pipeline
# kind=aria note="A pointer-only button at the board's left edge; scrolls one column back"
applications-board-scroll-back = Show earlier columns
# kind=aria note="A pointer-only button at the board's right edge; scrolls one column on"
applications-board-scroll-on = Show later columns
# kind=name note="The column of the endings the person chose: Accepted, Declined, Withdrawn"
applications-column-decided = Decided
# kind=name note="The column of the endings the company or the world decided: Rejected, Role closed"
applications-column-closed = Rejected or closed
# kind=empty note="The first column, Considering, while it holds nothing and other columns do"
applications-column-empty-saved = Save a role on your radar to start here.
# kind=empty note="Any other column with no application in it"
applications-column-empty = Nothing here yet.
# kind=status note="A column's count while filters are on: how many of its applications match"
applications-column-count-of = { $count } of { $total }
# kind=empty note="A column whose applications all fail the filters, while another column has a match"
applications-column-no-matches = No matches.
# kind=empty note="Any pipeline view whose filters leave nothing: the List, Up next, or every column of the Board. Reset all follows it"
applications-no-matches = Nothing matches these filters.
# kind=heading note="Any pipeline view while nothing is saved or pursued"
applications-empty = Nothing in your pipeline yet
# kind=sentence note="Under the empty pipeline's heading: the way a role comes in"
applications-empty-hint = Save a role on your radar to add it here.
# kind=link note="Under the empty pipeline: opens Radar"
applications-empty-radar = Open Radar
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
# kind=label note="A quick filter: the roles at Urgent or High priority"
applications-quick-high-priority = High priority
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
# kind=status note="An Applied card's lead: when the person applied. $ago is a relative day: today, yesterday, 10 days ago"
applications-card-applied = Applied { $ago }
# kind=status note="On an Applied card: nothing has happened to the application for a while"
applications-card-gone-quiet = Gone quiet
# kind=status note="When a timed interview is, on a card: $day is applications-posting-due-day, $time a clock time. Tomorrow, 2:30 PM"
applications-card-day-time = { $day }, { $time }
# kind=status same-as=applications-card-day-time note="A round that took place with no outcome yet: its name, as the person wrote it, and its day. Panel, Thu"
applications-card-round-past = { $label }, { $day }
# kind=status note="After a round that took place with no outcome yet, on an Interviewing card"
applications-card-ask-outcome = How did it go?
# kind=label note="The company took the posting down while the application is on the board"
applications-card-posting-closed = Posting closed
# kind=aria note="A card's priority mark; $level is No priority, Urgent, High, Medium or Low"
applications-card-priority = Priority: { $level }
## Priority levels, as the person names them
# kind=label
applications-priority-none = No priority
# kind=label
applications-priority-urgent = Urgent
# kind=label same-as=notifications-notification-filters-high
applications-priority-high = High
# kind=label
applications-priority-medium = Medium
# kind=label
applications-priority-low = Low
# kind=aria note="The priority menu of one role; $title is the role's title"
applications-priority-menu = Priority of { $title }
# kind=status note="On a card in Decided or Closed: the ending, then the stage it ended at, such as Withdrawn at Interviewing"
applications-card-ended = { $ending } at { $stage }

## A card's menu
# kind=aria
applications-menu-label = Move { $title }
# kind=label
applications-menu-move-to = Move to
# kind=button note="Only on a card in Considering: unsaves the role, and with it the card"
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
# kind=toast note="A move into Interviewing failed, and so did taking back the interview it had saved"
applications-move-failed-interview-kept = Couldn't move { $title }, but its interview was saved. Open the application to change or delete it.
# kind=toast
applications-removed = Removed { $title } from your pipeline
# kind=toast
applications-remove-failed = Couldn't remove { $title }. Try again.

## Moving into Interviewing asks when the interview is
# kind=heading
applications-interview-title = When is the interview?
# kind=label note="Names the role an interview belongs to, above the form, when adding, editing or moving into Interviewing"
applications-interview-for = { $title } at { $company }
# kind=label note="The summary line before a day is picked"
applications-interview-pick-day = Pick the day
# kind=label same-as=applications-next-interview-meta note="The summary line: a day and a time"
applications-interview-when-timed = { $date } · { $time }
# kind=heading note="The summary line: a day with no time yet"
applications-interview-when-day = { $date } · no time yet
# kind=label note="Under the month and the times; zone is the reader's own, by name"
applications-interview-zone = Times in { $zone }
# kind=label note="The first choice in the list of times"
applications-interview-no-time = No time yet
# kind=aria note="Names the list of quarter hours"
applications-interview-times = Times
# kind=error next=none note="The message is itself the way out"
applications-interview-time-invalid = Type a time like { $example }.
# kind=error next=none note="The message is itself the way out"
applications-interview-day-missing = Pick the day of the interview.
# kind=label note="Heads the round, the format and the link, which may be left empty"
applications-interview-optional = Optional
# kind=label
applications-interview-round-recruiter = Recruiter screen
# kind=label
applications-interview-round-hiring-manager = Hiring manager
# kind=label
applications-interview-round-technical = Technical
# kind=label
applications-interview-round-panel = Panel
# kind=label
applications-interview-round-final = Final round
# kind=label
applications-interview-round = Round
# kind=aria note="The plus after the common rounds, which opens a field to name another"
applications-interview-round-add = Name another round
# kind=label note="The field the plus opens, in the row of rounds"
applications-interview-round-name = Round name
# kind=label note="The round's name when the person names none"
applications-interview-default-label = Interview
# kind=label
applications-interview-time = Time
# kind=label
applications-interview-format = Format
# kind=label
applications-interview-format-video = Video
# kind=label
applications-interview-format-phone = Phone
# kind=label
applications-interview-format-onsite = On-site
# kind=label
applications-interview-link = Meeting link
# kind=label
applications-interview-link-placeholder = Paste the meeting link
# kind=error next=none note="Under the meeting link when it has no http:// or https://; the message is itself the way out"
applications-interview-link-invalid = Paste the whole link, starting with https://.
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
applications-interview-outcome-not-passed = Didn't pass
# kind=label
applications-interview-outcome-cancelled = Cancelled
# kind=label
applications-interview-notes = Notes
# kind=error note="In the interview form beside Save when its save failed; the form keeps what was typed"
applications-interview-failed = Couldn't save the interview. Try again.
# kind=toast
applications-interview-delete-failed = Couldn't delete the interview. Try again.
# kind=label note="Asked in the interview form's actions before an interview is deleted"
applications-interview-delete-confirm = Delete this interview?

## The pipeline's tabs
# kind=aria
applications-tabs-label = Pipeline views

## The List: the backlog, every role still in Considering, as a row of a table
# kind=label note="The List's column of the next interview or next step, and when it is due"
applications-list-head-next = Next step
# kind=label note="The List's last column, read to screen readers only: Not for me, Compare, Save and the row's moves"
applications-list-head-actions = Actions
# kind=heading note="The List when roles are saved but none is still in Considering: work has started on every one"
applications-list-clear = Nothing waiting to start
# kind=link note="Under the cleared List: opens the Board, where the roles under way are"
applications-list-clear-board = See the roles under way on the Board
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
# kind=label same-as=settings-plan-all-day note="An all-day round, under its day's heading"  hygiene: allow (a message id)
applications-upnext-all-day = All day
# kind=aria note="The round button that marks a next step done; $step is the step, as the person wrote it"
applications-upnext-done-label = Mark done: { $step }
# kind=toast note="A next step was marked done from Up next; $step is the step, as the person wrote it"
applications-upnext-done = Done · { $step }
# kind=heading same-as=applications-card-ask-outcome note="The group of rounds that took place and wait for their outcome"
applications-upnext-outcome = How did it go?
# kind=aria note="The three outcome buttons of one round; $label is the round's name"
applications-upnext-outcome-label = Outcome of { $label }
# kind=toast note="A round's outcome was set from Up next; $label is the round's name, $outcome is Passed, Didn't pass or Cancelled"
applications-upnext-outcome-set = { $label }: { $outcome }
# kind=toast
applications-upnext-undo-failed = Couldn't undo that change to { $title }. Try again.
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
        [0] The posting was reposted on the day you applied.
        [one] The posting was reposted 1 day after you applied.
       *[other] The posting was reposted { $days } days after you applied.
    }
# kind=status
applications-crossing-pay = { $days ->
        [0] The posted range changed on the day you applied.
        [one] The posted range changed 1 day after you applied.
       *[other] The posted range changed { $days } days after you applied.
    }
# kind=aria
applications-crossing-dismiss = Dismiss

## Next: the next interview and the next step
# kind=empty
applications-next-interview-none = No interview booked.
# kind=label note="An all-day interview's day"
applications-next-interview-all-day = { $date }, all day
# kind=label note="A timed interview's day and time"
applications-next-interview-at = { $date }, { $time }
# kind=label same-as=applications-interview-when-timed note="When an interview is, then its format"
applications-next-interview-meta = { $when } · { $format }
# kind=button note="Opens the interview's meeting link"
applications-next-interview-join = Join
# kind=aria
applications-next-interview-join-label = Join { $label }
# kind=button
applications-next-save = Save step

## Notes
# kind=heading
applications-notes-title = Notes
# kind=aria
applications-notes-label = Notes

## Activity: comments and recorded changes
# kind=status note="A recorded change: the role was saved into the pipeline"
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
# kind=status note="A recorded change: a next step was added; $step is the step, as the person wrote it"
applications-feed-step-added = Next step added: { $step }
# kind=status note="A recorded change: a next step's words or day changed; $step is the step after the change"
applications-feed-step-edited = Next step changed: { $step }
# kind=status note="A recorded change: a next step was ticked done; $step is the step"
applications-feed-step-done = Done: { $step }
# kind=status note="A recorded change: a next step ticked done was opened again; $step is the step"
applications-feed-step-reopened = Next step opened again: { $step }
# kind=status note="A recorded change: a next step was removed; $step is the step"
applications-feed-step-removed = Next step removed: { $step }
# kind=status note="A recorded change with no field this page names"
applications-feed-updated = Updated
# kind=label note="After a recorded change an agent made"
applications-feed-by-agent = by an assistant app
# kind=aria note="Names the menu a month divider opens, which moves the feed to another point in the application's history"
applications-feed-jump-label = Jump to
# kind=aria note="A month divider in the feed. $month is the month's name, already formatted"
applications-feed-jump-month = { $month }, jump to another point
# kind=label note="Jump menu: the newest entry of the feed"
applications-feed-jump-recent = Most recent
# kind=label note="Jump menu: the entry nearest the day the application moved to Applied"
applications-feed-jump-applied = When you applied
# kind=label note="Jump menu: the entry nearest the first interview that took place"
applications-feed-jump-interview = First interview
# kind=label note="Jump menu: the entry nearest the day the application moved to Offer"
applications-feed-jump-offer = The offer
# kind=label note="Jump menu: the oldest entry of the feed"
applications-feed-jump-beginning = The beginning
# kind=status note="Beside a month in the jump menu: how many comments it holds"
applications-feed-jump-comments = { $count ->
        [one] 1 comment
       *[other] { $count } comments
    }
# kind=aria
applications-comment-label = Comment
# kind=label
applications-comment-author-you = You
# kind=label
applications-comment-author-agent = Assistant app
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
applications-fact-starred = Saved
# kind=label
applications-fact-last-activity = Last activity
# kind=label
applications-fact-pay = Posted range
# kind=label
applications-fact-pay-none = Not posted
# kind=label
applications-fact-level = Level
# kind=button note="Opens the full posting over the page"
applications-read-posting = Read the posting
# kind=button
applications-interview-add = Add interview
# kind=aria
applications-interview-edit-label = Edit { $label }

## The posting's Pipeline section, above its Details
# kind=heading note="The section of a role in the pipeline, on its posting: where the application stands and what waits"
applications-posting-row = Pipeline
# kind=label note="Pipeline row: the application's stage, a link to the application"
applications-posting-stage = Stage
# kind=label note="Pipeline row value for an application moved into its stage today, in place of a count of days"
applications-posting-since-today = Since today
# kind=label note="Pipeline row of an ended application: the day it ended"
applications-posting-ended = Ended
# kind=label same-as=applications-month-legend-interview note="Pipeline row: when the next interview is"
applications-posting-interview = Interview
# kind=label same-as=applications-month-legend-step note="Pipeline row: the next step"
applications-posting-next-step = Next step
# kind=label note="Pipeline row: the day the next step is due, shown only when a due date is set"
applications-posting-due = Due
# kind=status note="Value of the Pipeline section's Due row. $offset is days from today; $date is a formatted day"
applications-posting-due-day = { $offset ->
        [0] Today
        [1] Tomorrow
       *[other] { $date }
    }
# kind=heading note="Title of the application's history: when it reached each stage, and its interviews"
applications-posting-history-title = Application history
# kind=label note="A line in the application's history: an interview, by its round; $label is the round the person named"
applications-posting-history-interview = { $label } interview
# kind=label note="Date column of the history's last line, the application as it stands now"
applications-posting-history-today = Today
# kind=label note="The history's last line: the stage the application is in and how long it has been there"
applications-posting-history-now = { $days ->
        [one] { $stage } for 1 day
       *[other] { $stage } for { $days } days
    }

## The role page: its tabs, title and side column
## The workspace: the stage's fixed sections and the free notes page
# kind=heading
applications-ws-next = Next steps
# kind=label note="The empty next step: an input the person types the step into"
applications-ws-next-add = Add a next step
# kind=aria note="Edits the next step's words in place; $step is the step"
applications-ws-next-edit = Edit the next step: { $step }
# kind=label same-as=applications-posting-due note="Before the next step's day field"
applications-ws-next-due = Due
# kind=button note="In a next step's edit, takes the step off the list with nothing kept, for one added by mistake"
applications-ws-next-remove = Remove
# kind=sentence note="The notes page's hint while it is empty; / opens the menu of headings, lists and checklists"
applications-ws-notes-hint = Write what you know and who you met. Type / for headings, lists and checklists.
# kind=sentence note="Under the notes page while it is longer than can be kept; $over is how many characters past the limit. Nothing is saved until it is shorter"
applications-notes-too-long = Not saved: { $over } characters over the limit.
# kind=aria note="The menu a / in the notes opens: the kinds of block it can put on the page"
applications-notes-blocks = Blocks
# kind=label note="A notes block: plain text"
applications-notes-block-text = Text
# kind=label note="A notes block: a heading; $level is 1, 2 or 3, its size"
applications-notes-block-heading = Heading { $level }
# kind=label note="A notes block: a list with a dot before each line"
applications-notes-block-bullets = Bulleted list
# kind=label note="A notes block: a list numbered 1, 2, 3"
applications-notes-block-numbers = Numbered list
# kind=label note="A notes block: a list of lines each with a box to tick"
applications-notes-block-checklist = Checklist
# kind=label note="A notes block: a quotation set in from the text"
applications-notes-block-quote = Quote
# kind=label note="A notes block: a line across the page"
applications-notes-block-divider = Divider
# kind=aria note="A checklist line's box in the notes; $line is the line's words, $checked yes when it is ticked"
applications-notes-check = { $checked ->
    [yes] Done: { $line }
   *[no] To do: { $line }
}
# kind=sentence note="The / menu when what was typed after the / names no block"
applications-notes-block-none = No block by that name.
# kind=label same-as=applications-card-ask-outcome note="Opens the three outcomes of a past round"
applications-ws-ask-outcome = How did it go?
# kind=aria note="The eye beside a block's caption: takes the block off this stage's Workspace. $section is the block's name"
applications-ws-hide = Hide { $section }
# kind=aria same-as=applications-menu-label note="The grip beside a block: dragged, it moves the block; pressed, it opens Move up and Move down. $section is the block's name"
applications-ws-move = Move { $section }
# kind=label
applications-ws-move-up = Move up
# kind=label
applications-ws-move-down = Move down
# kind=toast note="The toast after a block is hidden, beside Undo. $section is the block's name"
applications-ws-hidden = { $section } hidden
# kind=aria note="The plus under the last block: offers the hidden blocks"
applications-ws-add = Add a section
# kind=tooltip note="What the Interviews block holds, under its name in the add menu"
applications-ws-about-interviews = Rounds, their days and how each went
# kind=tooltip note="What the Next step block holds, under its name in the add menu"
applications-ws-about-next = What you do next, and by when
# kind=tooltip note="What the Notes block holds, under its name in the add menu"
applications-ws-about-notes = What you know and who you met
# kind=tooltip note="What the Outcome block holds, under its name in the add menu"
applications-ws-about-outcome = How the application ended
# kind=tooltip note="What the Activity block holds, under its name in the add menu"
applications-ws-about-activity = Comments and what changed

# kind=heading
applications-feed-title = Activity
# kind=empty
applications-feed-empty = No comments or changes yet.
# kind=button note="A folded run of recorded changes. $changes lists what changed, already joined"
applications-feed-fold = { $count ->
        [one] 1 update: { $changes }
       *[other] { $count } updates: { $changes }
    }
# kind=label
applications-comment-placeholder = Write what happened
# kind=button
applications-comment-submit = Comment
