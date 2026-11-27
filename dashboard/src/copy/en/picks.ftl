## Top picks

## The screen (features/opportunities/TopPicksScreen.tsx)
# kind=label
picks-loading = Loading your top picks…
# kind=heading
picks-load-failed = Couldn't load your top picks
# kind=sentence
picks-refresh-failed = Couldn't update your top picks. Showing the last result.
# kind=status note="A check made picks while the list was open; $count is how many new picks the list on screen lacks. The button Show the update follows it"
picks-fresh-more = { $count ->
    [one] { $count } new top pick since this list loaded.
   *[other] { $count } new top picks since this list loaded.
}
# kind=label note="The assistant that runs the checks, by its code: claude-code or codex"
picks-host = { $host ->
    [claude-code] Claude Code
    [codex] Codex
   *[other] Your assistant
}

## The empty list
# kind=heading note="Top picks is set up and no role has been picked"
picks-empty-title = Nothing has cleared your bar yet
# kind=empty note="Under the empty title; $count is how many roles the checks read in the last seven days"
picks-empty-read = { $count ->
    [one] { $count } { -role(num: "one") } was read this week. The next one that qualifies appears here.
   *[other] { $count } { -role(num: "other") } were read this week. The next one that qualifies appears here.
}
# kind=heading note="There are picks, and the filters hide every one"
picks-empty-filtered-title = No top picks match these filters
# kind=empty note="Under the title; $count is how many picks the filters hide; the button Reset all follows it"
picks-empty-filtered = { $count ->
    [one] { $count } top pick is hidden by the filters.
   *[other] { $count } top picks are hidden by the filters.
}
# kind=heading note="There are picks, and the search finds none of them"
picks-empty-search-title = No top picks match this search

## Notes above the list, while the checks need the person
# kind=sentence
picks-note-paused = Checks are paused. Nothing is read until they resume.
# kind=button
picks-resume = Resume checks
# kind=error
picks-resume-failed = Couldn't resume the checks. Try again.
# kind=sentence note="$host is the assistant's name; it asks for permission before each command, so a scheduled check cannot run"
picks-note-asks = { $host } asks before each command, so a check can't run unattended.
# kind=link note="Opens Settings, AI, where the assistant's connection is fixed"
picks-note-fix = How to fix it
# kind=sentence note="$host is the assistant's name"
picks-note-disconnected = { $host } is no longer connected.
# kind=link note="Opens Settings, AI, where an assistant is connected"
picks-note-connect = Connect it again

## Where the list ends
# kind=sentence note="$when is how long ago the last check finished (2 hours ago), $host the assistant's name"
picks-end-checked = Checked { $when } by { $host }.
# kind=sentence note="After the checked sentence while the checks are late: $count is how many roles wait to be read"
picks-end-waiting = { $count ->
    [one] { $count } { -role(num: "one") } is waiting.
   *[other] { $count } { -role(num: "other") } are waiting.
}
# kind=sentence note="After the checked sentence when that check ended early; $reason is why, in the assistant's own words, without a full stop"
picks-end-stopped = It stopped early: { $reason }. The rest is read at the next check.
# kind=sentence note="After the checked sentence when that check ended early and gave no reason"
picks-end-stopped-plain = It stopped before it finished. The rest is read at the next check.
# kind=sentence note="Last on the line, after any sentence before it; $passed is the link to the roles passed over"
picks-end-passed-only = { $passed }.
# kind=link note="Opens Passed over: the roles read in the last seven days and not picked"
picks-end-passed = { $count ->
    [one] { $count } { -role(num: "one") } passed over this week
   *[other] { $count } { -role(num: "other") } passed over this week
}
# kind=sentence note="Last on the line in a week the assistant passed over nothing; it stands where the link to Passed over stands in other weeks"
picks-end-passed-none = Nothing passed over this week.

## Showing Not for me: the picks the person removed (features/opportunities/TopPicksScreen.tsx)
# kind=sentence note="Under a removed pick, after the assistant's reasons: the reason the person gave, by its code"
picks-removed-said = { $reason ->
    [pay_too_low] You said the pay is too low.
    [wrong_level] You said the level is wrong.
    [wrong_role] You said it's not your work.
    [company] You said not this company.
    [wrong_place] You said it's the wrong place.
    [wrong_domain] You said it's the wrong world.
   *[other] You said it's something else.
}
# kind=sentence note="Under a removed pick: the person's own words, quoted"
picks-removed-words = In your words: “{ $words }”.
# kind=link note="Clears Not for me, so the role is a top pick and on the Radar again"
picks-removed-put-back = Put it back
# kind=aria note="The link's accessible name: its visible words, then the role it puts back"
picks-removed-put-back-name = Put it back: { $title }
# kind=heading note="Showing Not for me, and no pick is marked"
picks-removed-empty-title = No top picks marked “Not for me”
# kind=empty note="Under the title; the link Show all follows it and goes back to the picks"
picks-removed-empty = A top pick you mark Not for me waits here with your reason, in case you change your mind.

## Not for me on a pick: the question (features/opportunities/PickFeedbackDialog.tsx)
# kind=heading
picks-why-title = Why is this not for you?
# kind=label note="Under the question: the role's title, then its company"
picks-why-role = { $title } · { $company }
# kind=button note="A reason; pressing it removes the role and tells the assistant"
picks-why-pay = Pay too low
# kind=button note="A reason; pressing it removes the role and tells the assistant"
picks-why-level = Wrong level
# kind=button note="A reason; pressing it removes the role and tells the assistant"
picks-why-work = Not my work
# kind=button note="A reason; pressing it removes the role and tells the assistant"
picks-why-company = Not this company
# kind=button note="A reason; pressing it removes the role and tells the assistant"
picks-why-place = Wrong place
# kind=button note="A reason; pressing it removes the role and tells the assistant"
picks-why-other = Something else
# kind=sentence
picks-why-note = Pressing a reason removes the role from Top picks and from your Radar, and tells your assistant why.
# kind=link note="Removes the role without giving a reason"
picks-why-skip = Skip the reason
# kind=button note="Closes the question; the role stays a top pick"
picks-why-keep = Keep it

## Passed over (features/opportunities/PassedOverScreen.tsx)
# kind=heading note="The page's heading, read by assistive technology only"
picks-passed-heading = Passed over
# kind=label
picks-passed-loading = Loading passed-over roles…
# kind=heading
picks-passed-load-failed = Couldn't load what was passed over
# kind=status note="The page's first line; $count is how many roles the assistant read in the last seven days and did not pick"
picks-passed-summary = { $count ->
    [one] { $count } { -role(num: "one") } passed over this week
   *[other] { $count } { -role(num: "other") } passed over this week
}
# kind=link note="After the first line; opens Top picks"
picks-passed-back = Back to top picks
# kind=heading note="Near misses: roles that failed on one thing; $count is how many this week"
picks-passed-close = Came close ({ $count })
# kind=heading note="Roles the assistant read and passed, grouped by why; $count is how many"
picks-passed-read = Read and passed ({ $count })
# kind=heading note="Roles a hard rule ruled out before the assistant read them, by rule; $count is how many"
picks-passed-ruled = Ruled out by a hard rule before reading ({ $count })
# kind=link note="Under the first near misses; $count is how many there are"
picks-passed-show-all = Show all { $count }
# kind=label note="Why a role was passed, when the brief has no rule only reading can check"
picks-pass-hard-rule = Breaks a hard rule
# kind=label note="Why a role was passed; $rules are the person's rules only reading can check, joined with or"
picks-pass-hard-rule-named = Hard rule: { $rules }
# kind=label note="Why a role was passed"
picks-pass-off-direction = A different direction
# kind=label note="Why a role was passed"
picks-pass-below-level = Below your level
# kind=label note="Why a role was passed: the person would not plausibly get an interview"
picks-pass-out-of-reach = Out of reach
# kind=label note="Why a role was passed: not better than the person's current role"
picks-pass-not-better = Not a step up
# kind=label note="Why a role was passed: long-standing or reposted many times"
picks-pass-not-real = Not a live role
# kind=label note="Why a role was passed"
picks-pass-other = Other
# kind=heading note="Nothing was passed over in the last seven days and nothing was removed"
picks-passed-empty-title = Nothing passed over this week
# kind=empty note="Under the empty title"
picks-passed-empty = Roles the assistant reads and does not pick are listed here, with why.

## Onboarding: Top picks before setup (features/opportunities/TopPicksOnboarding.tsx)
# kind=heading
picks-onboard-headline = Your AI assistant
# kind=sentence
picks-onboard-line = A frontier AI model learns what you want, reads every new { -role(num: "one") }, and keeps the few worth a move.
# kind=status note="Under a large figure: how many new roles today. $count only chooses the plural; the figure is drawn above it"
picks-onboard-count = { $count ->
    [one] new { -role(num: "one") }, read
   *[other] new { -role(num: "other") }, every one read
}
# kind=status note="The first fact of an example reason, set apart in ink; the reason's sentence goes on in picks-onboard-reason-work"
picks-onboard-reason-work-lead = The work you asked for
# kind=sentence note="An example reason under an example top pick; $lead is picks-onboard-reason-work-lead"
picks-onboard-reason-work = { $lead }, at the level you set.
# kind=status note="The first fact of an example reason, set apart in ink; the reason's sentence goes on in picks-onboard-reason-more"
picks-onboard-reason-more-lead = More than you hold today
# kind=sentence note="An example reason under an example top pick; $lead is picks-onboard-reason-more-lead"
picks-onboard-reason-more = { $lead }, in pay or in scope.
# kind=status note="The first of two steps"
picks-onboard-step-say = Say one sentence to your assistant
# kind=status note="The second of two steps: the working Top picks screen"
picks-onboard-step-arrive = Picks arrive here
# kind=status note="Over the sentence the person copies and says in their assistant"
picks-onboard-say = Say this in your assistant
# kind=aria note="Names the marks of the assistants Top picks runs in"
picks-onboard-works-with = Works with Claude Code and Codex
# kind=sentence note="Said to the assistant, which runs the command in backticks: keep the command exactly as written, backticks included"
picks-onboard-sentence = Run `roleband connect --apply`, then set up my top picks.
# kind=status note="Said to an assistant that is already connected; lower case, as typed in a chat"
picks-onboard-sentence-connected = set up my top picks
# kind=status note="Live: no assistant has connected yet"
picks-onboard-waiting = Waiting for your assistant
# kind=sentence note="Live: an assistant has connected; $host is its name"
picks-onboard-connected = { $host } is connected. What it saves shows here.
# kind=link note="Shows the command to run in Terminal in place of the sentence"
picks-onboard-terminal = Or run the command in Terminal
# kind=sentence note="Under the steps: the time it takes, what the connection allows, and where the person's data goes"
picks-onboard-footnote = About ten minutes, on the plan you already have. It lets your assistant run roleband without asking. Your CV and the { -role(num: "other") } it reads go to your assistant's model.
# kind=status note="Before a choice of assistant, then the command to run in Terminal for it"
picks-onboard-in-terminal = In Terminal, for
# kind=aria note="Names the choice of assistant the Terminal command is for"
picks-onboard-terminal-host = Assistant
# kind=label note="Before the sentence to say in the assistant; $host is its name"
picks-onboard-in-host = In { $host }
# kind=link note="Goes back from the Terminal command to the one sentence"
picks-onboard-back = Back to one sentence
# kind=sentence note="Under the switch that lets assistant apps connect, shown while it is off"
picks-onboard-access = Lets your assistant read your { -role(num: "other") } and save picks.
# kind=heading note="The conversation in the assistant has saved its first answer"
picks-onboard-under-way = Setup is under way
# kind=sentence note="$host is the assistant's name"
picks-onboard-under-way-line = { $host } asks. What it saves shows here.
# kind=status note="A stage of the setup conversation, by its code; $host is the assistant's name"
picks-onboard-row = { $step ->
    [connect] { $host } is connected
    [background] Your background
    [situation] Where you stand
    [bar] What would make you move
    [rules] Hard rules
    [tradeoffs] What you would trade
    [targets] Companies you want, and ones to avoid
    [calibration] A first look at real { -role(num: "other") }
    [budget] How often you want to hear
    [confirm] What you are looking for, said back
    [trial] A first try on { -role(num: "other") } open today
   *[routine] Checks set to run each day
}
# kind=status note="Beside the stage the conversation is at, by its code"
picks-onboard-row-now = { $step ->
    [trial] Trying it now
    [routine] Being set up now
   *[other] Being asked now
}
# kind=status note="Beside a stage that needs roles; setup goes on past it until the first scan finds some"
picks-onboard-row-waits = Waits for the first scan
# kind=aria note="A stage whose answer is saved"
picks-onboard-row-saved = Saved
# kind=status note="Before the sentence that resumes setup in any conversation with the assistant"
picks-onboard-resume = Closed the chat? Any chat carries on:
