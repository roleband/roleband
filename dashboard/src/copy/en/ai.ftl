## ai: moved as it was found (wording=as-is)

## features/intelligence/AimLine.tsx
# kind=label wording=as-is
ai-aim-line-your-aim-in-one-sentence = Your aim, in one sentence
# kind=sentence
ai-aim-line-roles-closest-to-it-come = Roles closest to it come first when Radar is sorted by Best fit. It never hides a role. Leave it empty to rank by what you save and mark Not for me.
# kind=error
ai-aim-line-couldn-t-save-your-aim = Couldn't save your aim. Try again.
# kind=button wording=as-is
ai-aim-line-cancel = Cancel
# kind=button wording=as-is
ai-aim-line-save = Save
# kind=status
ai-aim-line-open-roles-ranked-by-how = { $total } open roles, ranked by how well they fit
# kind=status
ai-aim-line-open-roles-ranked-by-what = { $total } open roles, ranked by what you save and mark Not for me
# kind=sentence
ai-aim-line-open-roles-sorted-by-date = { $total } open roles, sorted by date. Your aim { $q } ranks them once ranking is ready.
# kind=label wording=as-is
ai-aim-line-open-roles-sorted-by-date-2 = { $total } open roles, sorted by date
# kind=aria wording=as-is
ai-aim-line-your-aim = Your aim
# kind=tooltip note="The aim field's placeholder: an aim anyone could write, at any level"
ai-aim-line-example = Product design at a climate tech company, remote in Europe
# kind=label wording=as-is
ai-aim-line-add-your-aim = { $choice ->
    [yes] Edit your aim
   *[no] Add your aim
}

## features/intelligence/AssistantsCard.tsx
# kind=heading
ai-assistants-card-mcp-server = Assistant apps (MCP)
# kind=label wording=as-is
ai-assistants-card-allowed-read-only = { $choice ->
    [yes] Allowed · reads and updates
   *[no] Allowed · read only
}
# kind=label wording=as-is
ai-assistants-card-not-allowed-nothing-is-shared = Not allowed · nothing is shared
# kind=heading wording=as-is
ai-assistants-card-what-will-be-shared = What will be shared
# kind=heading wording=as-is
ai-assistants-card-what-will-not-be-shared = What will not be shared
# kind=button wording=as-is
ai-assistants-card-set-up = Set up
# kind=label wording=as-is
ai-assistants-card-allow-assistant-apps-to-connect = Allow assistant apps to connect
# kind=label wording=as-is
ai-assistants-card-allow-assistant-apps-to-update = Allow assistant apps to update your progress
# kind=status note="What a connected assistant app may change when updates are allowed; every change is recorded"
ai-assistants-card-stage-notes-next-action-audited = stage · notes · next step · recipe drafts · audited
# kind=sentence
ai-assistants-card-it-can-then-read-what = It can then read what this card lists, and nothing more.
# kind=sentence wording=as-is
ai-assistants-card-run-this-once-in-a = Run this once in a terminal, then restart the app.
# kind=sentence
ai-assistants-card-most-apps-that-speak-mcp = Most MCP apps accept this. Add it to their MCP settings, then restart the app.
# kind=sentence wording=as-is
ai-assistants-card-add-this-to-the-app = Add this to the app's settings, then restart the app.
# kind=button wording=as-is
ai-assistants-card-done = Done
# kind=label wording=as-is
ai-assistants-card-anthropic = Anthropic
# kind=label wording=as-is
ai-assistants-card-set-up-the-claude-app = Set up the Claude app
# kind=label wording=as-is
ai-assistants-card-openai = OpenAI
# kind=label wording=as-is
ai-assistants-card-set-up-the-codex-app = Set up the Codex app
# kind=status note="The Other app tile's second line, under its name; the other tiles show a company name here"
ai-assistants-card-any-client-that-speaks-mcp = Any app that speaks MCP
# kind=label wording=as-is
ai-assistants-card-set-up-another-mcp-app = Set up another MCP app
# kind=aria
ai-assistants-card-mcp-server-2 = Assistant apps
# kind=label wording=as-is
ai-assistants-card-not-allowed-to-connect = { $choice ->
    [yes] · ready to set up
   *[no] · not allowed to connect
}
# kind=label wording=as-is
ai-assistants-card-allow-assistant-apps-to-connect-2 = Allow assistant apps to connect first
# kind=status note="The note beside the Allow assistant apps to connect switch, by its state"
ai-assistants-card-off-nothing-leaves-this-computer = { $choice ->
    [yes] on · shared only with the apps you connect
   *[no] off · nothing leaves this computer
}
# kind=error
ai-assistants-card-clipboard-access-was-blocked-select = Couldn't copy. Select the text and copy it yourself.
# kind=label wording=as-is
ai-assistants-card-copy = { $choice ->
    [yes] Copied
   *[no] Copy
}

## features/intelligence/CapabilitiesCard.tsx
# kind=heading
ai-egress-title = Allow sending to AI providers?
# kind=consent
ai-egress-detail = Text from { -posting(num: "other") } is sent only to the AI providers you turn on, including providers you add or turn on later.
# kind=heading
ai-egress-destinations = Saved providers
# kind=sentence
ai-egress-empty = No AI providers added. Nothing is sent until one is added and turned on.
# kind=button
ai-egress-allow = Allow
# kind=heading wording=as-is
ai-capabilities-card-extended-capabilities = Extended capabilities
# kind=status note="How many AI capabilities are on. $on is that count, in bold; $capCount how many there are. $choice: yes when every one that is on runs on this computer"
ai-capabilities-card-of-on = { $choice ->
    [yes] { $on } of { $capCount } on · all on this computer
   *[no] { $on } of { $capCount } on
}
# kind=label wording=as-is
ai-capabilities-card-your-own-model = Your own model
# kind=status
ai-capabilities-card-finds-duplicate-job-posts-only = { $value } · finds duplicate postings, only when you ask
# kind=label wording=as-is
ai-capabilities-card-apple-intelligence = Apple Intelligence
# kind=status
ai-capabilities-card-experimental-we-are-still-testing = { $value } · experimental
# kind=status note="The built-in model's state when it can run, the first part of a line of facts joined by dots"
ai-capabilities-card-ready = ready
# kind=label
ai-capabilities-card-online-model-services = AI providers
# kind=label
ai-capabilities-card-none-connected = None added ·
# kind=button wording=as-is
ai-capabilities-card-add = Add
# kind=label
ai-capabilities-card-send-postings-to-online-services = Send postings
# kind=label wording=as-is
ai-capabilities-card-the-example-says = the example says
# kind=label wording=as-is
ai-capabilities-card-it-found = it found
# kind=status note="The pay a model read from a sample posting. $band is the amount or range; $basis what it covers (base: base salary, total: all pay, unclear: not stated); $period the time it is for (year, month, hour, unclear: not stated)"
ai-capabilities-card-found-pay = { $band } · { $basis ->
    [base] base salary
    [total] total compensation
   *[unclear] base or total not stated
} · { $period ->
    [year] per year
    [month] per month
    [hour] per hour
   *[unclear] period not stated
}
# kind=label wording=as-is
ai-capabilities-card-quote-from-the-posting = quote from the posting
# kind=label wording=as-is
ai-capabilities-card-reason = reason
# kind=label wording=as-is
ai-capabilities-card-no-connection-saved = no connection saved
# kind=label wording=as-is
ai-capabilities-card-running-model-not-loaded = running, model not loaded
# kind=label wording=as-is
ai-capabilities-card-not-installed = not installed
# kind=label wording=as-is
ai-capabilities-card-server-stopped = server stopped
# kind=aria wording=as-is
ai-capabilities-card-extended-capabilities-2 = Extended capabilities
# kind=label wording=as-is
ai-capabilities-card-use-your-own-model = Use your own model
# kind=tooltip note="Hover text on the Start button while your own model is switched off: a connection is saved (yes) or not (no)"
ai-capabilities-card-save-a-connection-first-then = { $choice ->
    [yes] Turn this on to start your local AI server
   *[no] Save a connection first, then turn this on
}
# kind=label wording=as-is
ai-capabilities-card-start = { $choice ->
    [v1] Working…
    [v2] Stop
   *[v3] Start
}
# kind=aria wording=as-is
ai-capabilities-card-configure-your-own-model = Configure your own model
# kind=aria
ai-capabilities-card-enable-apple-intelligence = Turn on Apple Intelligence
# kind=aria wording=as-is
ai-capabilities-card-test-apple-intelligence = Test Apple Intelligence
# kind=label wording=as-is
ai-capabilities-card-turn-apple-intelligence-on-to = Turn Apple Intelligence on to test it
# kind=label wording=as-is
ai-capabilities-card-test = { $choice ->
    [yes] Testing…
   *[no] Test
}
# kind=status note="After None added, before any AI provider exists: whether postings could be sent (yes: Send postings is on)"
ai-capabilities-card-nothing-is-sent = { $choice ->
    [yes] allowed once you add a provider
   *[no] nothing is sent
}
# kind=status note="The Send postings row's sub-line, by the switch's state"
ai-capabilities-card-off-nothing-is-sent = { $choice ->
    [yes] on · added providers receive postings
   *[no] off · nothing is sent
}
# kind=status
ai-capabilities-card-no-pay-range-found = { $choice ->
    [v1] Test failed
    [v2] The answer did not match the posting
    [v3] It works
    [v4] Found a posted range
   *[v5] No posted range found
}
# kind=label
ai-capabilities-card-on-device = on this computer
# kind=tooltip note="Hover text on an AI provider row that can't run: its own switch is off (yes), or Send postings is off (no)"
ai-capabilities-card-allow-sending-postings-to-online = { $choice ->
    [yes] Turn { $name } on to use it
   *[no] Turn on Send postings first
}
# kind=status note="An AI provider row's state, the last part of a line of facts joined by dots"
ai-capabilities-card-blocked-online-services-are-switched = { $choice ->
    [v1] in use
    [v2] off
   *[v3] blocked · sending is off
}
# kind=toast wording=as-is
ai-capabilities-card-connection-ready-ms = connection ready · { $latency_ms } ms
# kind=label wording=as-is
ai-capabilities-card-use = Use { $name }
# kind=label wording=as-is
ai-capabilities-card-no-key = { $choice ->
    [yes] key saved
   *[no] no key
}
# kind=label wording=as-is
ai-capabilities-card-test-2 = Test { $name }
# kind=label wording=as-is
ai-capabilities-card-configure = Configure { $name }

## features/intelligence/CloudDialog.tsx
# kind=sentence note="$b is the Send postings switch's name, in bold"
ai-cloud-dialog-a-direct-api-connection-billed = Uses your own API key, billed separately from any ChatGPT or Claude plan. Postings are sent only when { $b } is on.
# kind=label wording=as-is
ai-cloud-dialog-name = Name
# kind=label wording=as-is
ai-cloud-dialog-provider = Provider
# kind=label wording=as-is
ai-cloud-dialog-server-address-https = Server address (HTTPS)
# kind=label wording=as-is
ai-cloud-dialog-model-id = Model ID
# kind=label wording=as-is
ai-cloud-dialog-api-key = API key
# kind=label
ai-cloud-dialog-enable-this-connection = Turn on this provider
# kind=label
ai-cloud-dialog-could-not-save = Couldn't save
# kind=label
ai-cloud-dialog-could-not-delete = Couldn't delete
# kind=label
ai-cloud-dialog-add-an-online-model-service = { $choice ->
    [yes] Configure { $name }
   *[no] Add an AI provider
}
# kind=label wording=as-is
ai-cloud-dialog-openai-api = OpenAI API
# kind=label wording=as-is
ai-cloud-dialog-anthropic-api = Anthropic API
# kind=label wording=as-is
ai-cloud-dialog-other-openai-compatible = Other OpenAI-compatible
# kind=tooltip note="The API key field's placeholder: a key is saved (yes) or not (no)"
ai-cloud-dialog-required-to-test = { $choice ->
    [yes] Leave blank to keep the saved key
   *[no] Required to test
}
# kind=label
ai-cloud-dialog-delete = { $choice ->
    [yes] Yes, delete { $name }
   *[no] Delete
}
# kind=label
ai-cloud-dialog-delete-2 = { $choice ->
    [yes] Yes, delete
   *[no] Delete
}
# kind=label wording=as-is
ai-cloud-dialog-save = { $choice ->
    [yes] Saving…
   *[no] Save
}

## features/intelligence/FitField.tsx
# kind=sentence
ai-fit-field-fit-of-open-roles-rising = Fit of { $total } open roles, rising from weak to strong; { $join }. Select a grade to preview its roles.
# kind=label
ai-fit-field-roles = { $label }: { $count } roles

## features/intelligence/IntelligenceSection.tsx
# kind=label
ai-intelligence-section-the-board-keeps-working-meanwhile = Radar keeps working meanwhile
# kind=label
ai-intelligence-section-preparing-matching-mb = preparing ranking: { $b }/{ $total_bytes } MB
# kind=status note="Roles that joined the ranking today. $n is that count, in bold"
ai-intelligence-section-new-roles-added-today = { $count ->
    [one] { $n } new role added today
   *[other] { $n } new roles added today
}
# kind=label wording=as-is
ai-intelligence-section-no-new-roles-today = no new roles today
# kind=heading wording=as-is
ai-intelligence-section-fit-ranking = Fit ranking
# kind=heading wording=as-is
ai-intelligence-section-preview = Preview
# kind=status note="Over a sample of one fit band's roles. $label is the band's name; $n how many roles the band holds"
ai-intelligence-section-the-strongest-of-roles = { $count ->
    [one] the strongest of { $label } · { $n } role
   *[other] the strongest of { $label } · { $n } roles
}
# kind=status
ai-intelligence-section-your-best-matches = your best fits
# kind=label wording=as-is
ai-intelligence-section-loading = loading…
# kind=heading
ai-intelligence-section-matches-load-failed = Couldn't load your best fits
# kind=heading
ai-intelligence-section-band-load-failed = Couldn't load the roles in this grade
# kind=status note="Shown when the selected fit grade holds no roles. $value is the grade's name"
ai-intelligence-section-nothing-lands-in-right-now = no roles in { $value } right now
# kind=label wording=as-is
ai-intelligence-section-more = +{ $max } more ·
# kind=link
ai-intelligence-section-open-the-board = open Radar
# kind=aria
ai-intelligence-section-intelligence = AI
# kind=aria wording=as-is
ai-intelligence-section-fit-ranking-2 = Fit ranking
# kind=status note="After the best fits, when every one of them is at one company. $length is how many there are, $top the company"
ai-intelligence-section-all-are-at-right-now = { $length ->
    [one] (it is at { $top } right now)
   *[other] (all { $length } are at { $top } right now)
}
# kind=label
ai-intelligence-section-this-band = this grade

## features/intelligence/LocalModelDialog.tsx
# kind=heading wording=as-is
ai-local-model-dialog-your-own-model = Your own model
# kind=sentence
ai-local-model-dialog-a-model-server-you-run = A model on your local AI server. Used only when you compare two postings. Nothing leaves this computer.
# kind=label wording=as-is
ai-local-model-dialog-server-type = Server type
# kind=label wording=as-is
ai-local-model-dialog-server-address = Server address
# kind=label
ai-local-model-dialog-generation-and-reasoning-parameters = Model settings
# kind=label wording=as-is
ai-local-model-dialog-max-tokens = Max tokens
# kind=label wording=as-is
ai-local-model-dialog-temperature = Temperature
# kind=label wording=as-is
ai-local-model-dialog-top-p = Top p
# kind=label wording=as-is
ai-local-model-dialog-timeout-s = Timeout (s)
# kind=label wording=as-is
ai-local-model-dialog-thinking-budget = Thinking budget
# kind=label
ai-local-model-dialog-enable-model-thinking = Think before answering
# kind=label wording=as-is
ai-local-model-dialog-ms = { $wall_time_ms } ms
# kind=label
ai-local-model-dialog-could-not-switch-connection = Couldn't switch connection
# kind=heading
ai-local-model-dialog-could-not-reach-the-model = Couldn't reach your local AI server
# kind=label wording=as-is
ai-local-model-dialog-configure-your-own-model = Configure your own model
# kind=aria wording=as-is
ai-local-model-dialog-saved-connections = Saved connections
# kind=label
ai-local-model-dialog-omlx-managed = oMLX, started from here
# kind=tooltip note="The key field's placeholder: yes while editing a saved connection"
ai-local-model-dialog-optional = { $choice ->
    [yes] Leave blank to keep the saved key
   *[no] Optional
}
# kind=label wording=as-is
ai-local-model-dialog-connection-incomplete = { $choice ->
    [yes] Connection succeeded
   *[no] Connection incomplete
}
# kind=label wording=as-is
ai-local-model-dialog-test-connection = { $choice ->
    [yes] Testing…
   *[no] Test connection
}

## features/intelligence/MatchingModel.tsx
# kind=label
ai-matching-model-local-ai-model = Ranking model
# kind=label wording=as-is
ai-matching-model-downloading-of-mb = · downloading, { $round } of { $round2 } MB
# kind=sentence wording=as-is
ai-matching-model-roles-are-listed-newest-first = Roles are listed newest first until this finishes.
# kind=label wording=as-is
ai-matching-model-switching-to-the = Switching to the { $nAME_LOWER }
# kind=label wording=as-is
ai-matching-model-of-roles-updated = { $done } of { $total } roles updated
# kind=sentence wording=as-is
ai-matching-model-you-can-keep-working-meanwhile = You can keep working meanwhile.
# kind=label wording=as-is
ai-matching-model-not-downloaded = · not downloaded
# kind=sentence
ai-matching-model-the-could-not-be-downloaded = The { $value } couldn't be downloaded.
# kind=sentence note="The same failure before any model was chosen"
ai-matching-model-could-not-be-downloaded = The ranking model couldn't be downloaded.
# kind=sentence wording=as-is
ai-matching-model-check-your-internet-connection-and = Check your internet connection and try again.
# kind=button wording=as-is
ai-matching-model-use-the = Use the { $nAME_LOWER }
# kind=label wording=as-is
ai-matching-model-current = · Current
# kind=button wording=as-is
ai-matching-model-choose-automatically = Choose automatically
# kind=button wording=as-is
ai-matching-model-switch-to-the = Switch to the { $nAME_LOWER }
# kind=sentence wording=as-is
ai-matching-model-the-switch-to-the-is = The switch to the { $nAME_LOWER } is paused.
# kind=sentence wording=as-is
ai-matching-model-the-rest-finishes-tonight-on = The rest finishes tonight on its own.
# kind=button
ai-matching-model-finish-now = { $choice ->
    [yes] Finish now, { $estimate }
   *[no] Finish now
}
# kind=button wording=as-is
ai-matching-model-go-back-to-the = Go back to the { $nAME_LOWER }
# kind=sentence
ai-matching-model-the-small-model-is-built = The small model is built for { $b } of RAM. This computer's RAM is unknown, so either model works.
# kind=label wording=as-is
ai-matching-model-gb = { $ramThresholdGb } GB
# kind=sentence
ai-matching-model-it-is-the-right-fit = It's built for this computer's { $b } of RAM.
# kind=label wording=as-is same-as=ai-matching-model-gb
ai-matching-model-gb-2 = { $ramGb } GB
# kind=label wording=as-is
ai-matching-model-roles-re-ranked = { $corpusTotal } roles re-ranked
# kind=label wording=as-is
ai-matching-model-roles = { $corpusTotal } roles
# kind=label wording=as-is
ai-matching-model-re-ranked = re-ranked
# kind=label wording=as-is
ai-matching-model-keep-working-while-it-runs = Keep working while it runs
# kind=sentence
ai-matching-model-stop-anytime-restart-anytime-nothing = Stop anytime, restart anytime. Nothing is lost.
# kind=label wording=as-is
ai-matching-model-keep-the-computer-awake-until = Keep the computer awake until it finishes
# kind=button wording=as-is
ai-matching-model-start-the-switch = Start the switch
# kind=label wording=as-is
ai-matching-model-big-model = Big model
# kind=label wording=as-is
ai-matching-model-small-model = Small model
# kind=label wording=as-is
ai-matching-model-big-model-2 = big model
# kind=label wording=as-is
ai-matching-model-small-model-2 = small model
# kind=label wording=as-is
ai-matching-model-under-a-minute = under a minute
# kind=label wording=as-is
ai-matching-model-about-min = about { $minutes } min
# kind=label wording=as-is
ai-matching-model-about-hr = about { $round } hr
# kind=label same-as=ai-matching-model-local-ai-model
ai-matching-model-matching-model = Ranking model
# kind=aria wording=as-is
ai-matching-model-download-progress = Download progress
# kind=label wording=as-is
ai-matching-model-stop-and-go-back-to = { $choice ->
    [yes] Stopping…
   *[no] Stop and go back to the { $nAME_LOWER }
}
# kind=aria wording=as-is
ai-matching-model-switching-progress = Switching progress
# kind=label wording=as-is
ai-matching-model-text = { $choice ->
    [yes] { " " }· { $left } left
   *[no] { "" }
}
# kind=label wording=as-is same-as=ai-matching-model-stop-and-go-back-to
ai-matching-model-stop-and-go-back-to-2 = { $choice ->
    [yes] Stopping…
   *[no] Stop and go back to the { $value }
}
# kind=label wording=as-is
ai-matching-model-other-model = other model
# kind=label wording=as-is
ai-matching-model-roles-ranked = { $choice ->
    [yes] { $value } of { $corpus_total } roles updated
   *[no] { $corpus_embedded } roles ranked
}
# kind=sentence wording=as-is
ai-matching-model-the-big-model-produces-better = The big model produces better results.
# kind=sentence wording=as-is
ai-matching-model-switch-only-if-you-want = Switch only if you want to free RAM.
# kind=label wording=as-is
ai-matching-model-small-model-is-built-for = Small model is built for
# kind=label
ai-matching-model-your-computer-has = This computer has
# kind=label
ai-matching-model-local-ai-model-switch = Ranking model switch

## features/intelligence/OriginBadge.tsx
# kind=label
ai-origin-badge-cloud-connected = { $choice ->
    [yes] On this computer
   *[no] Leaves this computer
}

## features/intelligence/AssistantsCard.tsx (by hand)
# kind=label wording=as-is
ai-assistants-card-shares-role-titles-companies-locations-and-link = Role titles, companies, locations and links
# kind=status
ai-assistants-card-shares-pay-level-and-how-long-the-role-has-been = Compensation, level, and how long the role has been open
# kind=label wording=as-is
ai-assistants-card-shares-the-full-posting-when-they-open-one = The full posting, when they open one
# kind=status
ai-assistants-card-shares-your-progress-on-roles-stage-priority-no = Your progress on roles: stage, priority, notes, next step
# kind=status note="Something a connected assistant app can make RoleBand do: open a public web page from the user's computer and show it to the app"
ai-assistants-card-shares-public-pages-it-asks-roleband-to-open = Public web pages it asks to open from this computer
# kind=label
ai-assistants-card-never-your-profile-and-intent-statement = Your profile and aim
# kind=label wording=as-is
ai-assistants-card-never-your-own-salary-or-contacts = Your own salary or contacts
# kind=label wording=as-is
ai-assistants-card-never-anything-from-your-other-apps = Anything from your other apps
# kind=label wording=as-is
ai-assistants-card-app-claude-app = Claude app
# kind=label wording=as-is
ai-assistants-card-app-codex-app = Codex app
# kind=label wording=as-is
ai-assistants-card-app-other-app = Other app

## default connection names (by hand)
# kind=label same-as=ai-capabilities-card-your-own-model
ai-local-model-dialog-default-name = Your own model

## features/intelligence/CapabilitiesCard.tsx
# kind=label wording=as-is same-as=ai-local-model-dialog-ms
ai-capabilities-card-ms = { $latency_ms } ms

## The AI screen's server words, said here from the codes the API sends:
## a provider's availability by state (backend/tracker/intelligence/provider.py),
## where a test ran by origin, and the test outcomes (intelligence_runtime/selftest.py,
## local_llm/client.py).
# kind=sentence
ai-availability-available = Ready.
# kind=sentence
ai-availability-disabled-by-flag = Turned off.
# kind=sentence
ai-availability-sdk-absent = Apple Intelligence needs macOS 26 or later on Apple silicon.
# kind=sentence
ai-availability-apple-intelligence-disabled = Apple Intelligence is off. Turn it on in System Settings.
# kind=sentence
ai-availability-device-ineligible = This computer doesn't support Apple Intelligence.
# kind=sentence
ai-availability-model-not-ready = Not ready yet. May still be downloading.
# kind=sentence
ai-availability-not-configured = No model is set up. Add one in Settings › AI.
# kind=sentence
ai-availability-server-unreachable = Your local AI server didn't respond. Start it, then test again.
# kind=sentence
ai-availability-egress-not-permitted = Sending postings to AI providers is off. Turn it on in Settings › AI.
# kind=label wording=as-is
ai-origin-none = No model ran
# kind=status
ai-origin-on-device = On this computer: Apple Intelligence
# kind=status
ai-origin-this-mac = On this computer: your own model
# kind=status
ai-origin-cloud = Sent to an AI provider
# kind=sentence
ai-self-test-prefiltered = No compensation found in the text, so no model call was made. That's normal for most postings.
# kind=sentence
ai-self-test-model-failed = The model didn't give a usable answer ({ $failure }).
# kind=sentence note="Max tokens is the field's label in the same dialog"
ai-local-test-max-tokens = The answer was cut off at Max tokens. Raise it and test again.
# kind=sentence
ai-local-test-succeeded = Connected. The model answered.
# kind=error
ai-local-server-action-failed = { $action ->
    [start] Couldn't start your local AI server. Start it yourself, then test the connection.
   *[stop] Couldn't stop your local AI server. Stop it yourself.
}

## The local server's state when it answers.
# kind=label wording=as-is
ai-capabilities-card-running = running

# kind=status note="The Apple Intelligence row's state when its setting turns it off, the first part of a line of facts joined by dots"
ai-capabilities-card-apple-off = off

# kind=status note="The Apple Intelligence row's state when Apple Intelligence is off in macOS, the first part of a line of facts joined by dots"
ai-capabilities-card-apple-off-in-system-settings = off in System Settings

# kind=status note="The Apple Intelligence row's state while the model is not ready yet, the first part of a line of facts joined by dots"
ai-capabilities-card-apple-downloading = downloading

# kind=status note="The Apple Intelligence row's state when this computer can't run it yet, the first part of a line of facts joined by dots"
ai-capabilities-card-apple-needs-macos = needs macOS 26 or later on Apple silicon

# kind=status note="The Apple Intelligence row's state when this computer can't run Apple Intelligence at all, the first part of a line of facts joined by dots"
ai-capabilities-card-apple-not-supported = not supported on this computer

# kind=status note="Beside the local AI server's switch when a start ran past its time limit and the server may still come up"
ai-local-server-start-pending = Your local AI server is still starting. Check again in a minute.
