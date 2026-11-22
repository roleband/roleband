# 0021: An update window replaces desktop notifications

## Context

The Mac app told a person about a new release in two places: the panel's banner, which
they see only when they open the panel, and a desktop notification. The notification
needed macOS permission, which setup never asked for and only About's notices switch
did, so most installs never got one. Focus modes silence notifications, and Notification
Center gathers them where they are easy to miss.

## Decision

When an automatic check finds a release, the app opens a small window of its own in the
middle of the screen, with Later and Update. It never takes focus or the keyboard.

- Later hides that version's window for three days. After the third Later only the
  menu-bar badge carries the offer; a newer version starts again.
- Check now never opens the window; its answer stays in About.
- About's notices switch becomes the window's switch and keeps its stored value.
- The app no longer posts desktop notifications or asks macOS for their permission.
  This replaces the notices bullet of [0019](0019-update-checks-on-by-default.md).
- The Windows app opens the same window by the same rules. It never told anyone of an
  update outside its flyout and Settings, so there the window replaces nothing: a switch
  in Settings turns it off, it starts on, and What's new opens the release's page.

## Consequences

- An install that checks for updates shows a new release without asking anything of
  macOS, and the person can update from the window without opening the panel.
- A person who ignores the window three times keeps only the badge for that version.
- A source checkout has no installer, so it gets no window; its banner and badge stay.
- Enforced by `launcher/macos/Tests/LauncherModelTests/UpdateWindowTests.swift`, the
  update-window tests in `PanelTests.swift` and
  `launcher/windows/RoleBand.EngineHost.Tests/UpdateWindowTests.cs`; described in [ui.md](../ui.md#native-launcher-updates)
  and [architecture.md](../architecture.md).

## Alternatives considered

- **Keep the notification beside the window.** It says the same thing twice and still
  needs a permission prompt, and the badge already marks an offer the person set aside.
- **Ask Later again every day.** With daily checks that nags; a job radar is rarely
  urgent; a release that is would need a mark of its own.
