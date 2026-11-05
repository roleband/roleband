# Changelog

Notable changes to RoleBand, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.2]

A pipeline for the roles you pursue, and fixes.

- **Roles you pursue get a Pipeline.** Saved becomes Pipeline, with three
  views: Considering lists the roles you starred but have not started, the
  Board shows every role you pursue in the column of its stage, and Up next
  shows what is due, by day. Each application has its own page with its stage,
  a next step, notes, comments and interview rounds. An application can now end
  as accepted, declined or role closed, and the Pipeline keeps its own
  comparison, apart from the Radar's.
- **A level we cannot place gets no pay estimate.** A posting whose title names
  no level on the company's ladder used to show the pay of a guessed level. It
  now shows the range the posting states, marked "level not mapped" or "level
  not stated". Existing roles are estimated again once, after the update.
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
