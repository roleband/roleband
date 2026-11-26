## ai: moved as it was found (wording=as-is)

## features/intelligence/AimLine.tsx
# kind=label wording=as-is
ai-aim-line-your-aim-in-one-sentence = Your aim, in one sentence
# kind=sentence
ai-aim-line-roles-closest-to-it-come = Roles closest to it come first in Best fit. It never hides a role.
# kind=error
ai-aim-line-couldn-t-save-your-aim = Couldn't save your aim. Try again.
# kind=button wording=as-is
ai-aim-line-cancel = Cancel
# kind=button wording=as-is
ai-aim-line-save = Save
# kind=status
ai-aim-line-open-roles-ranked-by-how = { $total ->
    [one] { $total } open role, ranked by how well it fits
   *[other] { $total } open roles, ranked by how well they fit
}
# kind=status
ai-aim-line-open-roles-ranked-by-what = { $total ->
    [one] { $total } open role, ranked by what you save and mark Not for me
   *[other] { $total } open roles, ranked by what you save and mark Not for me
}
# kind=sentence
ai-aim-line-open-roles-sorted-by-date = { $total ->
    [one] { $total } open role, sorted by date. Your aim { $q } ranks it once ranking is ready.
   *[other] { $total } open roles, sorted by date. Your aim { $q } ranks them once ranking is ready.
}
# kind=status
ai-aim-line-open-roles-sorted-by-date-2 = { $total ->
    [one] { $total } open role, sorted by date
   *[other] { $total } open roles, sorted by date
}
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
ai-assistants-card-assistant-apps = Assistant apps
# kind=label wording=as-is
ai-assistants-card-allow-assistant-apps-to-connect = Allow assistant apps to connect
# kind=sentence wording=as-is
ai-assistants-card-run-this-once-in-a = Run this once in a terminal, then restart the app.
# kind=sentence
ai-assistants-card-let-the-app-run-commands = Let the app run commands, then ask it to run this.
# kind=button wording=as-is
ai-assistants-card-done = Done
# kind=label wording=as-is
ai-assistants-card-anthropic = Anthropic
# kind=label wording=as-is
ai-assistants-card-openai = OpenAI
# kind=status note="The Other app tile's second line, under its name; the other tiles show a company name here"
ai-assistants-card-any-app-that-can-run-commands = Any app that can run commands
# kind=aria
ai-assistants-card-assistant-apps-2 = Assistant apps
# kind=label wording=as-is
ai-assistants-card-allow-assistant-apps-to-connect-2 = Allow assistant apps to connect first
# kind=status note="The note beside the Allow assistant apps to connect switch: on (yes) or off (no). The switch shows which"
ai-assistants-card-off-nothing-leaves-this-computer = { $choice ->
    [yes] shared only with the apps you connect
   *[no] nothing leaves this computer
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
ai-egress-title = Allow AI providers?
# kind=consent
ai-egress-detail = Only the AI providers you turn on are used, each with your own API key. That includes ones you add or turn on later. Turning this off stops them all.
# kind=heading
ai-egress-destinations = Saved providers
# kind=sentence
ai-egress-empty = No AI providers added.
# kind=button
ai-egress-allow = Allow
# kind=heading wording=as-is
ai-capabilities-card-extended-capabilities = Extended capabilities
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
ai-capabilities-card-send-postings-to-online-services = Allow AI providers
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
    [yes] Starts your local AI server
   *[no] Save a connection first
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
# kind=status note="After None added, before any AI provider exists: whether an AI provider could be contacted (yes: Allow AI providers is on)"
ai-capabilities-card-nothing-is-sent = { $choice ->
    [yes] allowed once you add a provider
   *[no] nothing leaves this computer
}
# kind=status note="The Allow AI providers row's sub-line, by the switch's state"
ai-capabilities-card-off-nothing-is-sent = { $choice ->
    [yes] on · only providers you turn on are used
   *[no] off · nothing leaves this computer
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
# kind=tooltip note="Hover text on an AI provider row that can't run: its own switch is off (yes), or Allow AI providers is off (no)"
ai-capabilities-card-allow-sending-postings-to-online = { $choice ->
    [yes] Turn { $name } on to use it
   *[no] Allow AI providers first
}
# kind=status note="An AI provider row's state, the last part of a line of facts joined by dots"
ai-capabilities-card-blocked-online-services-are-switched = { $choice ->
    [v1] allowed
    [v2] off
   *[v3] blocked · AI providers are off
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
# kind=sentence
ai-cloud-dialog-a-direct-api-connection-billed = Uses your own API key, billed apart from any ChatGPT or Claude plan.
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
ai-intelligence-section-preparing-matching-mb = preparing ranking
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
ai-local-model-dialog-a-model-server-you-run = Used only to compare two postings. Nothing leaves this computer.
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
# kind=label wording=as-is
ai-matching-model-switching-to-the = Switching to the { $nAME_LOWER }
# kind=label wording=as-is
ai-matching-model-of-roles-updated = { $done } of { $total } roles updated
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
# kind=status
ai-matching-model-roles-ranked = { $choice ->
    [yes] { $corpus_total ->
        [one] { $value } of { $corpus_total } role updated
       *[other] { $value } of { $corpus_total } roles updated
    }
   *[no] { $corpus_embedded ->
        [one] { $corpus_embedded } role ranked
       *[other] { $corpus_embedded } roles ranked
    }
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
# kind=label
ai-assistants-card-app-claude-code = Claude Code
# kind=label wording=as-is
ai-assistants-card-app-codex-app = Codex app
# kind=label wording=as-is
ai-assistants-card-app-other-app = Other app
# kind=sentence note="Under the Allow assistant apps to connect switch while it is off: what a connected app may read and do"
ai-assistants-card-what-apps-do = They read your roles, compensation, notes, offer and profile, and keep your progress up to date.
# kind=sentence note="Under the Allow assistant apps to connect switch, in both states"
ai-assistants-card-up-to-the-app = What an app does with what it reads is up to that app and the model it uses.
# kind=sentence note="The card's last line while the switch is off and nothing is held back from assistant apps"
ai-assistants-card-everything-shared = Everything is shared once this is on.
# kind=status note="The card's last line: the kinds of data the person keeps from assistant apps. $list is their names, joined as a list"
ai-assistants-card-not-shared = Not shared: { $list }.
# kind=status note="The card's last line: the kinds of data kept to models on this computer, which a connected app gets as not shared. $list is their names, joined as a list"
ai-assistants-card-local-only = Models on this computer only: { $list }.
# kind=status note="The card's last line: the kinds of change assistant apps may not make. $list is their names, joined as a list"
ai-assistants-card-changes-off = Changes off: { $list }.
# kind=status note="The card's last line when assistant apps may make no change at all"
ai-assistants-card-read-only = Apps only read.
# kind=button note="Opens the dialog where the person chooses, per kind of data and kind of change, what assistant apps get"
ai-assistants-card-customize = Customize
# kind=link note="Opens the screen listing each read, change and refusal by assistant apps"
ai-assistants-card-activity = Activity
# kind=button note="An app tile's action while the app is not connected, or its settings no longer let it run commands without asking"
ai-assistants-card-connect = Connect
# kind=button note="An app tile's action while the instructions installed for the app are older than this version's"
ai-assistants-card-update = Update
# kind=heading note="The dialog with the command that connects Claude Code"
ai-assistants-card-connect-claude-code = Connect Claude Code
# kind=heading note="The dialog with the command that connects the Codex app"
ai-assistants-card-connect-the-codex-app = Connect the Codex app
# kind=heading note="The dialog with the first command any other app runs"
ai-assistants-card-connect-another-app = Connect another app
# kind=status note="An app tile's second line: the company that makes it, then what the app's own settings say. $age is already worded, such as 5m ago or just now. Without a state, the company alone"
ai-assistants-card-app-state = { $state ->
    [connected] { $service } · connected
    [used] { $service } · used { $age }
    [outdated] { $service } · update available
    [rule-missing] { $service } · asks before each command
    [read-only] { $service } · blocked by read-only mode
   *[none] { $service }
}
# kind=status note="The Other app tile's second line once any other app has run a command. $age is already worded, such as 5m ago or just now"
ai-assistants-card-other-used = Used { $age }
# kind=aria note="The check on the icon of an app that is connected or has run a command"
ai-assistants-card-connected = Connected
# kind=aria note="An app tile's Activity button: the Activity screen, showing only this app's entries"
ai-assistants-card-app-activity = { $app } activity

## features/intelligence/AgentAccessDialog.tsx
# kind=heading
ai-access-dialog-title = Customize what apps get
# kind=heading note="Above the grid of kinds of data, each read by any model, by models on this computer only, or by none"
ai-access-dialog-data = Data apps read
# kind=heading note="Above the grid of kinds of change, each on or off"
ai-access-dialog-changes = What apps change
# kind=label note="A column of the data grid: any model the app uses may read it"
ai-access-dialog-any-model = Any model
# kind=label note="A column of the data grid: only models on this computer may read it"
ai-access-dialog-local-only = Local only
# kind=tooltip
ai-access-dialog-local-only-tip = Models on this computer only. A connected app gets it as not shared.
# kind=label note="A column of the data grid: no model may read it"
ai-access-dialog-not-shared = Not shared
# kind=label note="A column of the changes grid"
ai-access-dialog-on = On
# kind=label note="A column of the changes grid"
ai-access-dialog-off = Off
# kind=label note="A kind of data: the roles and their postings"
ai-access-dialog-postings = Postings
# kind=label note="A kind of data: pay estimates and market figures"
ai-access-dialog-market-statistics = Market statistics
# kind=label note="A kind of data: the roles the person saved and how far each has got, with their notes"
ai-access-dialog-progress-and-notes = Progress and notes
# kind=label note="A kind of data: the offer the person entered"
ai-access-dialog-offer = Offer
# kind=label note="A kind of data: the person's profile and aim"
ai-access-dialog-profile = Profile
# kind=label note="A kind of change: saving roles and moving them along, with notes and next steps"
ai-access-dialog-tracking-progress = Tracking progress
# kind=label note="A kind of change: notes an assistant keeps about what it found"
ai-access-dialog-keeping-findings = Keeping findings
# kind=label note="A kind of change: what the radar looks for"
ai-access-dialog-tuning-the-radar = Tuning the radar
# kind=label note="A kind of change: which companies are followed and how their postings are collected"
ai-access-dialog-controlling-collection = Controlling collection
# kind=aria note="One choice in a grid: $row is a kind of data or change, $column the choice"
ai-access-dialog-cell = { $row }: { $column }
# kind=button note="Puts every kind of data back to any model and every kind of change back on"
ai-access-dialog-share-everything = Share everything again

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
ai-availability-egress-not-permitted = AI providers are off. Turn them on in Settings › AI.
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

# kind=status note="The Apple Intelligence row's line while its switch is off; the switch shows that it is off"
ai-capabilities-card-apple-experimental = experimental

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

## features/intelligence/TopPicksCard.tsx
# kind=status note="The Top picks card's status line, beside its title. It starts with whether the checks are on, as the Assistant apps card's line does. $host is the assistant's name (Claude Code, Codex); $when is how long ago, already worded (2 hours ago). checked: the last check finished; first: no check has finished yet; late: roles are waiting and no check has finished for a day and a half; stopped: the last check ended before it finished; disconnected: the assistant is no longer connected; asks: it asks before each command, so a check can't run unattended; read-only: its read-only mode blocks the checks; paused-checked and paused: the checks are off"
ai-top-picks-card-status = { $state ->
    [checked] on · { $host } checked { $when }
    [first] on · { $host } hasn't checked yet
    [late] on · { $host } last checked { $when }
    [stopped] on · { $host } stopped early { $when }
    [disconnected] on · { $host } is no longer connected
    [asks] on · { $host } asks before each command
    [read-only] on · { $host } is blocked by read-only mode
    [paused-checked] off · { $host } last checked { $when }
   *[paused] off · checks paused
}
# kind=heading note="The Top picks card's switch and its name: on, the person's assistant reads the new roles of each scan and keeps the few worth a move"
ai-top-picks-card-check = Check each scan for top picks
# kind=sentence note="Under the switch, in both states"
ai-top-picks-card-check-note = Off stops the checks and the alerts, and keeps what you are looking for.
# kind=error
ai-top-picks-card-pause-failed = Couldn't pause the checks. Try again.
# kind=heading note="Above what the person told their assistant they look for, in the assistant's words"
ai-top-picks-card-brief = What you are looking for
# kind=sentence note="In place of what the person is looking for while their assistant has saved no summary of it"
ai-top-picks-card-brief-none = Your assistant hasn't written it down yet.
# kind=label note="A sentence the person copies and says to their assistant to change what it looks for; lower case, as typed in a chat"
ai-top-picks-card-sentence = update my top picks
# kind=heading
ai-top-picks-card-limit = Roles read a day, at most
# kind=sentence note="Under the daily limit: reading uses the person's plan with their AI provider"
ai-top-picks-card-limit-note = Bounds how much of your plan a day of reading can use. Your assistant can change it too.
# kind=error next=none note="Under the daily limit while its field holds something it can't take; the message is itself the instruction. $max is the most it can be"
ai-top-picks-card-limit-range = Type a whole number from 1 to { $max }.
# kind=error
ai-top-picks-card-limit-failed = Couldn't save the daily limit. Try again.
# kind=heading
ai-top-picks-card-remove-title = Remove your CV and preferences
# kind=sentence
ai-top-picks-card-remove-note = Removes the CV, what was read from it, what you are looking for and the reasons on past picks. Roles you saved stay saved.
# kind=button
ai-top-picks-card-remove = Remove
# kind=heading note="The confirmation's title"
ai-top-picks-card-remove-confirm-title = Remove your CV and preferences?
# kind=sentence note="The confirmation's text, under its title"
ai-top-picks-card-remove-confirm = This can't be undone. The checks stop until you set Top picks up again.
# kind=error
ai-top-picks-card-remove-failed = Couldn't remove them. Try again.
# kind=toast note="Once Remove has deleted them; the card is gone from the screen"
ai-top-picks-card-removed = Your CV and preferences are removed.
