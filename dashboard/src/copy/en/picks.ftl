## Top picks

## The screen (features/opportunities/TopPicksScreen.tsx)
# kind=label
picks-loading = Loading your top picks…
# kind=heading
picks-load-failed = Couldn't load your top picks
# kind=heading note="Shown in place of the list until the person's assistant has set Top picks up"
picks-not-set-up = Top picks is not set up
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
# kind=sentence note="Last on the line: the roles read in the last seven days and not picked"
picks-end-passed = { $count ->
    [one] { $count } { -role(num: "one") } passed over this week.
   *[other] { $count } { -role(num: "other") } passed over this week.
}
