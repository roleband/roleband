# 0019: Update checks are on by default

## Context

The Mac app finds a new release only by asking GitHub's releases API. When automatic
checks waited for an explicit choice, a person who left setup's switch alone never
heard about a release unless they opened About and pressed Check now. Fixes then
reached only the people who went looking for them.

A check sends GitHub the network address and a generic User-Agent, nothing about the
person's radar ([SECURITY.md](../../SECURITY.md)). The app already reads many
employers' job boards every day, so one request a day to GitHub adds no new kind of
exposure.

## Decision

The Mac app checks for updates once a day unless the person turns automatic checks
off. Setup and About show the same switch, on until it is turned off.

- An install that never chose checks without recording a choice. Only turning the
  switch off or on records one, with the words shown and their language.
- A recorded choice to turn checks off, or a declined choice kept in older
  preferences, still prevents every passive request.
- Check now stays a one-off request that changes no choice.

## Consequences

- People hear about fixes without remembering to look; the in-panel offer appears
  after the next daily check.
- Tests that build an app model without their own update feed must give it an
  offline one, since a fresh install now checks by itself.
- Notices still need macOS permission, which only About asks for.
- The Windows app keeps the explicit choice of
  [0009](0009-windows-release-authorization.md) until it adopts this rule.
- Enforced by `launcher/macos/Tests/LauncherModelTests/UpdateTests.swift`;
  described in [architecture.md](../architecture.md) and [ui.md](../ui.md#native-launcher-updates).

## Alternatives considered

- **Keep checks off until chosen.** Most people never choose, so most installs would
  stay on the version they installed.
- **Write a daily choice for installs that never chose.** That would record a choice
  the person never made.
