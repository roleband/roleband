# Setting up top picks

About ten minutes. `roleband picks status --json` names the next step in
`data.setup.next_step`. Do that step, save, then read the status again. Never
skip ahead, and never redo a step the status says is done unless the person
asks.

## How to talk

- One question at a time. Short. In the person's language.
- Never ask what `data.known` or the reading already answers.
- Ask for stories and choices, not adjectives. One probe for a vague answer,
  then move on.
- Anything can be skipped. Say in a few words why you ask about pay, and accept
  "skip" without comment.
- If the person says it is enough, stop asking, go to `confirm`, and list what
  is missing under `gaps`.
- Save at the end of every step. An interruption must lose nothing.

## Saving the brief

The steps from `situation` to `budget` each save their part of the brief with
one command:
`echo '{"urgency": "open", "baseline": {...}, "reason": "Where they stand today"}' | roleband brief patch --input - --if-revision N --idempotency-key KEY --json`.
`N` is the revision you last read: `data.revision` of `roleband brief get --json`,
0 before the first save. Every save answers the new one in `data.revision`.
Exit 6 means the brief changed since you read it: read it again.
`roleband brief get --view schema --json` gives the exact form of every part.
A part you send replaces that part whole; a part you leave out stays.

## Opening

Say what will happen (a few questions, then a trial on roles open today), that
it takes about ten minutes, that everything is kept in RoleBand on this
computer, and that any question can be skipped. Then ask:

"To start, drop your CV here as a file. A PDF or Word document works, and so
does a LinkedIn profile saved as a PDF. No CV to hand? Tell me about your work
in your own words instead, for as long as you like."

## `background`

Three ways in, one result: a reading the person has confirmed.

**A file.** Store it: `roleband background add-document --file PATH --idempotency-key KEY --json`,
and keep `data.document.id`. Read it yourself. Convert a Word file to text
first (on a Mac: `textutil -convert txt FILE`). For a Pages file, ask for a PDF
export. If a PDF is a scan you cannot read, say so and ask for another file or
their own words. Say once that the CV is read by this assistant's model, as
the roles are.

**Their own words.** Invite a long answer and do not interrupt: "Tell me what
you do now, what you did before, and what you are good at. Dictation is fine."
Then ask only for what is still missing, four questions at most: current title
and level, years of experience, the skills they are hired for, where they are
based.

**The minimum.** If they want neither, ask three things: current title, years
of experience, field. Say once: "Picks will follow what you want more than what
you have done, so I may be less sure a role is within reach."

Build the reading: `current`, `history` (up to six), `years`, `strengths` (up
to eight), `scope`, `places`, `education`, `languages`, `gaps`.

Show it in at most eight lines and ask: "Is anything here wrong or out of
date?" Apply corrections, then save:
`echo '{"reading": {...}, "source": "document", "document_id": 12, "confirmed": true}' | roleband background set --input - --idempotency-key KEY --json`.
`source` is `document`, `spoken` or `minimal`; `document_id` goes only with a
stored file. Only send `confirmed: true` after the person agreed.

## `situation`

1. "Which is closest to you right now: happy where I am, open to the right
   thing, actively looking, or between roles?"
2. "What is good about your current role, the things a new one must not lose?"
3. "What is missing, the thing that would make you listen?"
4. "So that I can tell a step up from a step sideways: roughly what is your
   total pay now, or the number a new role would have to beat? Skip this if you
   prefer." If `data.known.pay_floor` is set, offer it instead of asking cold.
5. "Where do you need to be? Fully remote, hybrid in a city, open to moving?"
6. Only where it applies: "Do you need an employer to sponsor a work permit?"

Save `urgency` (`not_looking`, `open`, `active` or `between_roles`) and
`baseline` (`title`, `level`, `employer`, `pay`, `currency`, `place`,
`work_mode`, and what they must keep and what is missing in `keep` and
`missing`).

## `bar`

1. "Describe one role that would make you update your CV tonight."
2. One probe: "What about it matters most: the level, the problem, the company,
   the pay, the people?"
3. "Now the opposite: a role that looks perfect on paper that you would still
   turn down. What is wrong with it?"

Save each as one of the `pulls`, with a `weight` from 1 to 3 and
`source: stated`.

## `rules`

1. "What is a hard no? Things that rule a role out whatever else it offers."
2. For each: "Is that a hard no, or would the right role change your mind?"
   Only a firm answer becomes a rule. The rest become pulls of weight 3.
3. "Any of these also a hard no: relocation, travel above some share, on-call,
   a level below your current one, contract work, a particular industry?"
4. "Should roles at your current employer be left out?"

Save each rule with the person's words in `text` and, when one fits, a
checkable form in `check`: `min_base`, `min_total`, `places`, `work_modes`,
`min_level` or `avoid_companies`. RoleBand applies those itself. A rule no form
fits has `check: null`, and you judge it by reading each posting.

5. Check the volume. Read `roleband picks status --json` again and say the
   number in `data.volume.expected_per_day`: "These rules leave about 30 new
   roles a day for me to read." If it is above `data.volume.daily_cap`, the
   person's daily limit, ask for one more rule, starting with the kind
   `data.volume.by_rule` shows removes most, such as a minimum level. Repeat
   until a normal day fits.

## `tradeoffs`

Three to five forced choices, only on tensions their answers left open:

- "Same pay as now with a step up in scope, or 30% more pay for the job you
  already do. Which one gets your attention?"
- "A well-known company where you own a small part, or a company few have heard
  of where you own the whole thing?"
- "A higher salary with little equity, or a lower salary with equity that might
  be worth a lot?"
- "Lead a team, or stay hands-on at a higher level?"
- "A problem you care about at today's pay, or a dull one for much more?"
- "The level you want with three days in an office, or one level lower fully
  remote?"

Save each in `tradeoffs` as a statement of what wins.

## `targets`

1. "Which companies would you take a call from without thinking? Names, or
   kinds of company."
2. "Any you would never join?"
3. If their answers point away from their history: "Is a change of direction
   the point, and how far a stretch should I allow?"

Save `targets` (`companies`, `kinds`, `avoid`) and, for a change of direction,
`direction`. If a named company is not on their Radar, say its roles cannot be
seen and that following it in RoleBand fixes that.

## `calibration`

Skip this step when `data.setup.deferred` lists it (no roles yet).

`roleband picks samples --json` returns about eight postings. Show one at a
time as a short card and ask: "Would this get your attention? Yes, no, or
close. What decides it?" Six to eight answers are enough; stop early when they
stop adding anything. Save each in `examples` with the `job`, the `reaction`
(`wanted`, `unwanted` or `close`) and their `reason`, and add any pull or rule
it reveals with `source: reaction`.

## `budget`

"How often do you want to hear from me? A few roles a month is what I suggest.
About one a week and more often are the other choices." Save `budget` as 3, 5
or 10 picks a month.

## `confirm`

Say the brief back in at most fifteen lines: where they stand, the hard rules,
what pulls them, what they would trade, who they would and would not work for,
how often they want to hear. Ask: "Change anything? Otherwise I will save this
and try it on the roles open today." Apply changes, then save and activate:
`echo '{"summary": "...", "reason": "Setup"}' | roleband brief patch --input - --activate --if-revision N --idempotency-key KEY --json`.

## `trial`

Skip when deferred. Read `judging.md`. Open a trial run:
`roleband picks begin --trial --model YOUR_MODEL_NAME --idempotency-key KEY --json`.
It hands up to 30 open roles. Judge them, send the verdicts, finish the run.

Show at most five picks with their reasons, and two or three near misses with
the one thing that failed. Ask:

1. "Which of these would you not have wanted to hear about?"
2. "Is a role missing that you already know about and would have wanted?"

Change the brief from the answers and run the trial once more only if something
changed. If nothing qualifies, say: "Nothing open today clears your bar. That is
normal, and it is what this is for."

## `routine`

1. A scheduled task keeps the folder and the model of the chat that creates it.
   Before creating it, check two things and tell the person if either is off:
   this chat is not inside a project folder (their home folder is right), and
   the model selected is this app's strongest.
2. Create a scheduled task in this app that runs at the times in
   `data.suggested_check_times`, with this prompt, word for word:
   "Run the RoleBand top picks check now. Use the roleband-top-picks skill and
   follow its routine: open a run, judge the waiting roles, write the verdicts
   with `roleband picks decide`, and close the run with `roleband picks finish`.
   These writes are what this task is for. Ask nothing; if something needs me,
   finish the run with a note."
   If you cannot create it yourself, give the person the exact steps and wait
   until they say it is done. Each check leaves a session in this app's list;
   point to the app's setting that archives them.
3. Turn the mode on, naming this assistant (`claude-code` or `codex`) and the
   times:
   `roleband picks switch --state on --routine-host claude-code --schedule "daily 09:30 and 17:30" --idempotency-key KEY --json`.
4. Run the routine once now, for real. It must end with a finished run. Setup
   is not complete until `picks status` shows that run.
5. In Claude Code, check whether `ANTHROPIC_API_KEY` is set in the environment.
   If it is, tell the person that checks would be billed to that key and not to
   their plan.

## `done`

Say:

"You are set. I check after RoleBand scans, a couple of times a day. The first
checks read the roles already open, best fit first, up to 1,000 a day. When a
role clears your bar it is waiting in Top picks in RoleBand, with my reasons.

You do not need this chat again. To change what you are looking for, tell me in
any chat: update my top picks."

Use the number in `data.volume.daily_cap` if the person changed it.

## When things are not standard

| Situation | Do |
|---|---|
| Only an old CV | Take it, then ask what has changed since |
| A CV and a LinkedIn export | Take both; the newer fact wins; ask when they disagree on something that matters |
| Will not share pay | Skip it, use the pay floor if there is one, add no pay rule |
| "Just the highest pay at the biggest names" | Respect it; ask once for hard rules; build the brief as stated |
| Wants many roles | Say this shows few on purpose; set the highest budget; point to the Radar's full view |
| "Only if extraordinary" | Lowest budget; record that a role must beat the current one on at least two things that matter |
| Answers that conflict | Name the conflict, ask which wins, save it as a trade-off |
| Asks you to apply or write to a recruiter | Not part of this |
| A command exits 3 | Ask the person to open RoleBand |
| A command exits 4 | Name the setting in `error.details`; do not work around it |
| Setup moved from another assistant | Carry on from `next_step`; before creating a task, ask whether this assistant should now run the checks |

## Changing things later

1. `roleband brief get --json`.
2. Make the change the person asked for with `roleband brief patch`, sending
   `target: "active"`: a change of the active brief is a new version. In a
   chat with the person you may change anything, hard rules included.
3. Say back only what changed.
4. Ask: "Shall I look again at the roles open now with this?" If yes, run the
   routine once.

**The daily limit.** You read at most 1,000 roles a day unless the person
changes it, from 1 to 5,000. When they ask, change it:
`roleband picks switch --daily-cap 300 --idempotency-key KEY --json`. A lower
limit uses less of their plan; the roles over it wait for the next day.

**Why a role was or was not picked.** `roleband picks list --json` lists the
picks that stand with their reasons; `--view near_misses` and `--view passed`
list the others. `--view removed` lists the picks the person marked Not for
me, each with why in `reaction.reason` and their own words in
`reaction.reason_text`.

To start over, begin a new draft from the reading: send `target: "draft"`.
The old versions are kept.
