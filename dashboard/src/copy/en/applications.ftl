## Application pipeline (features/applications). The card's noun is
## application once the pipeline frame is set; the role's stages are the
## taxonomy's stage names.

## The board
# kind=status note="Under the page title: how many applications are moving, ended by the person, ended by the company, and how many past Considering have no next step or interview"
applications-board-summary = { $moving } in motion · { $decided } decided · { $closed } closed · { $needNext } { $needNext ->
        [one] needs
       *[other] need
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
# kind=button
applications-closed-hide = Hide
# kind=aria
applications-closed-hide-label = Hide the Closed column
# kind=aria note="The hidden Closed column, folded to a button that brings it back"
applications-closed-show = Show the Closed column

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
# kind=button
applications-move-undo = Undo
# kind=toast
applications-move-failed = Couldn't move { $title }. Try again.
# kind=toast
applications-undo-failed = Couldn't move { $title } back. Try again.
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

## One application's page
# kind=aria
applications-page-bar = Application
# kind=label note="The back link to the board, with the application's stage: Pipeline is the place's short name"
applications-page-back = Pipeline / { $stage }
# kind=button
applications-page-back-board = Open the board
# kind=heading
applications-page-load-failed = Couldn't load this application
# kind=status note="Where the application stands among the cards of its column"
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
