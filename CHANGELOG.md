# Changelog

Notable changes to RoleBand, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

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
