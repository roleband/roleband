# 0022: The important mark is its own signed file

## Context

A release may fix something people need, and its update window should then come back
sooner than the three days after Later that [0021](0021-update-window-replaces-notifications.md)
gives every release. The mark that says so has to be signed, since the release listing is
not, and it has to be readable by new apps without stopping older ones from updating.

Release metadata cannot carry it. Installed apps accept metadata only in format 2 or 3 with
exactly the fields they know, so a new field or format makes every installed app refuse
the release as invalid, and those people could not update to the release meant to fix them.

## Decision

The mark is a separate release file, `RoleBand-<version>-macOS-arm64.important`: a 64-byte
Ed25519 signature by the release key over `roleband-important v<version>` and a newline.

- `Tools/release.py important` signs it and attaches it to a published, non-prerelease
  release that already has its four files, once. It can be added after the release ships.
- An app reads the file only when the listing names it, and counts the mark only when a
  release key it holds signed that version. Anything else is no mark, and the next check
  reads it again.
- A marked release's window comes back a day after each Later, with no limit on Laters,
  and says the update is recommended. It never installs on its own, and About's switch
  still turns the window off.
- The Windows app follows the same rules with its own file,
  `RoleBand-<version>-Windows-x64.important`, signed by the Windows release key over the
  same bytes; `launcher/windows/Tools/release.py important` attaches it. The two apps hold
  different keys, so each platform's mark counts only for its own app, and a release can be
  important on one and not the other. Settings' Update window switch turns it off.

## Consequences

- Apps that predate the mark see one more file in the listing and ignore it, so they keep
  updating.
- The signed bytes name the version, so a mark cannot be moved to another release, and
  they cannot be mistaken for the metadata signature, whose bytes open with a checksum.
- A mark cannot be withdrawn from people who already read it, as a release cannot.
- Enforced by `anImportantMarkIsTheToolsSignatureOnThisVersionAlone`,
  `anImportantMarkCountsOnlyWhenItsSignatureHolds`, the important tests in
  `UpdateTests.swift`, `UpdateWindowTests.swift` and `PanelTests.swift`, and the important
  tests in `Tools/test_release.py`; on Windows by the mark tests in
  `backend/tests/test_windows_updates.py`, `ImportantMarkTests` in
  `launcher/windows/Tools/test_release.py`, and the important tests in `UpdateWindowTests.cs`
  and `AboutTests.cs`.

## Alternatives considered

- **A field in the signed metadata.** Every installed app would refuse the release.
- **A line in the release notes.** The notes are not signed, so anyone who could edit the
  release could make every window come back daily.
