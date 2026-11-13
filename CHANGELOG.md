# Changelog

Notable changes to RoleBand, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.1]

Pay opens on what employers post, a newer database runs underneath, and the
posting reads as one page.

- **Pay opens on posted base salary.** The Pay tab leads with the typical posted
  base salary for one level in one country, then lists every company hiring at
  that level with its posted range first. More postings show the pay they state:
  a range with a repeated currency code, a zone number or a period in words, an
  unmarked US or Canadian range (read as base), and a single stated figure. A
  stated base shows even when the posting names no level. Estimated stock follows
  each level's share and each company's stated rule, so early-career roles no
  longer read more stock than senior ones.
- **The posting reads as one page.** A wider window gives it more room, and the
  pay card says what it knows. How a company builds an offer is on its company
  profile, which says who stated each fact.
- **A newer database.** The built-in database moves to Postgres 16.15 and
  pgvector 0.8.7, with their fixes. Your data stays where it is, and the update
  keeps a backup it returns to if anything fails.
- **Insights stays quick as your history grows.** Overview, Pace and Hiring read
  only the postings their period can reach.
- **Places read right.** "Remote in Germany" and "Berlin or Remote" no longer
  read as US states, and NYC, SF, EU and DE resolve. A company searched one place
  at a time no longer closes postings in a place you stopped tracking.
- **Companies waiting for consent are one question.** Settings asks once for all
  of them, with a step to pick which to unfollow.
- **The Mac app finds its way past a busy port.** It names the program using its
  port and offers a free one. When another program holds its database, it starts
  by itself once that program lets go. The tray's scan card fits its words in
  every language.
- **Windows behaves like a Windows app.** Engine alerts arrive as Windows
  notifications, the app quits when Windows asks, open tabs keep working through
  an engine restart, and the tray icon, sign-out and Setup end cleanly.
- **Safer by default.** The engine answers only this computer.

## [0.2.0]

Windows joins the Mac, Insights counts every role once, and the top bar follows
the wider market's first scan.

- **Now on Windows 11.** Download `RoleBand-Setup-0.2.0.exe` from this release.
  Setup asks an administrator once to trust the app's own certificate, then
  installs the app for you; updates after that install through the app. Smart
  App Control blocks it while it is on.
- **Insights counts every role once.** A role listed in several places counts
  once on every tab, in skills and in the daily history, and opened and came
  down count the same roles. The period switch offers only periods the
  history covers, so a week of scans no longer says "last 30 days". Overview's
  tile for a period's openings reads Opened; New stays the last two days. Pay
  over time is hidden until there is enough history to compare.
- **The top bar follows the wider market's first scan.** While the first pass
  over the directory runs, the scan badge reads "Wider market" and how far it
  has come, with the counts in its tooltip. Companies waiting for a full scan
  are the amber dot.
- **The posting's side column reads as one ledger.** Every row is a label and
  plain words on one line. The Pipeline section shows Stage, In this stage,
  Interview, Next step and Due, and a step past its date reads as overdue.
- **Follow dialogs say less.** The consent is said once, and Keep scanning is a
  plain switch row.
- **Safer by default.** A saved model key is sent only to the server it was
  saved for. Every dashboard file carries the app's content policy, and the API
  documentation pages are gone. The bundled Python moves to 3.12.16, with its
  security fixes.

## [0.1.3]

Your offer on the Stock tab, Workday companies scanned in one press, a
plainer Insights, and clearer words everywhere.

- **Your offer, year by year.** On the Stock tab, enter a job offer one
  question at a time and see what each of its four years pays, at today's
  price and after a move. A question the company already answers is skipped.
  The offer stays on this computer.
- **The Stock tab reads each role the way its page does.** Base is the posted
  range where a posting states one, bonus follows the posting or the company's
  own rule, and stock is a measured grant or a marked estimate. Public and
  private companies, and companies where each person picks their own cash and
  stock mix, sit in separate tables, with one search under the chart.
- **Insights keeps only what answers a question.** Trends, the Cluster map and
  Overlap are gone, with the longest-open, reposted and updated lists and the
  tiles that repeated a figure shown elsewhere. A company on Hiring opens its
  roles on the Board.
- **Following a Workday company scans it.** The follow dialog asks whether to
  keep scanning it on the schedule, and one press follows and scans.
- **A posting shows where your application stands**, in a Pipeline section with
  its stage, the days in that stage, a booked interview and the next step. On
  the board, the star becomes the stage button.
- **Picking a time** on the schedule opens a list of half hours, each saying
  when the scan starts.
- **A retirement benefit reads as the plan the employer names**: a 401(k), an
  RRSP, or a retirement plan.
- **A full scan reads every company to the end of its list**, however large.
- **Clearer words on every screen**, in English, Spanish and Chinese: one
  vocabulary throughout, errors that end with a next step, and health
  notifications that say what happened and what happens next.

## [0.1.2]

A pipeline for the roles you pursue, and fixes.

- **Roles you pursue get a Pipeline.** Saved becomes Pipeline, with three
  views: Considering lists the roles you starred but have not started, the
  Board shows every role you pursue in the column of its stage, and Up next
  shows what is due, by day. Each application has its own page with its stage,
  a next step, notes, comments and interview rounds. An application can now end
  as accepted, declined or role closed, and the Pipeline keeps its own
  comparison, apart from the Radar's.
- **A level we cannot place gets no pay estimate.** When a posting's title names
  no level on the company's ladder, its pay shows the range the posting states,
  marked "level not mapped" or "level not stated", and no estimate for a
  guessed level. Every role is estimated again once, after the update.
- **First-run setup is easier to go back through.** Back from its first step
  asks the sharing question again, on the answer you gave. Adjust on the
  Summary brings Continue back to the Summary. The minimum base field reads the
  amount back as you type it. Setup is drawn larger on a large window, and the
  World step's lists drop their pick count.
- **Fields are clearer.** A focused field shows one ring on its own edge, and
  any field holding a value it cannot take shows a red edge.
- **Pay splits explain themselves to a keyboard and a tap**, on a role's pay
  card and in the Insights stock table. The split bar's estimate stripes are
  quieter in both themes, and the bar still shows in high-contrast modes.
- **The Fit ranking chart** keeps roles that score below zero inside its frame.
- Updated dependencies, including the Mac app's built-in runtime.

## [0.1.1]

Fixes and polish.

- **Tune the radar asks about sharing first**, even when pressed before the
  sharing state has loaded. If that state cannot be read, setup opens.
- **Your own model's switch** looks like the other off switches. Turning it on
  opens its setup, and it stays off until a connection is saved.
- **Counts are grouped the same way**: every figure in the Followed companies
  and Companies toolbars uses your region's number format.
- **The listing history panel stays on screen** on a phone, even after its
  events load.
- **An empty price chart's key** link and button respond to clicks.
- **Focus stays where you are typing** when a setup step appears, and closing a
  cover returns focus to its row in Safari as well.
- **Messages point to the right place**: three of them now name Decided and
  Settings › AI.
- **Pay text is read in time proportional to its length**, so a page full of
  spaces can no longer stall a scan, and only a SmartRecruiters address counts as
  a SmartRecruiters board.
- **Pay figures are computed faster.**
- Updated dependencies, including the Mac app's built-in runtime.

## [0.1.0]

First public release.

- **Follow companies, see every open role that fits you.** RoleBand reads each
  employer's own careers page, on a schedule or when you start a scan, and
  lists the open roles on the Radar, ranked by the level, craft, places and
  minimum base you set in Profile.
- **Every posting is read the same way**: its level on the company's own
  ladder, role family, places and workplace, and any pay it states, kept with
  the sentence it came from.
- **Pay for every role.** An estimate of base, equity and total pay per posting,
  and a company profile with its level ladder, pay by level and benefits, all
  from datasets that ship with RoleBand.
- **A posting's whole life.** When it appeared, how long it has stayed open,
  reposts and closures. A posting is closed only when a complete read of its
  board no longer lists it.
- **Runs on your computer.** No account and no RoleBand server. On macOS it can
  run in the background, and it picks up an update after a `git pull`.
- **Languages:** English, Spanish and Simplified Chinese.
- **Plugins are a preview.** None ships in this release, and Settings shows them
  as coming soon. The plugin SDK (1.0.0) and template are there for authors; their
  interface may still change.
