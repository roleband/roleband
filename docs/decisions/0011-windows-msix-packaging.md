# 0011: RoleBand ships on Windows as a signed MSIX

## Context

The Windows app needs an installer that a standard account can use without developer
tools, keeps PostgreSQL history outside the replaceable program files, lets the app update
itself after owner authorization, and leaves an executable way back when an update fails.
MSIX replaces program files on its own schedule and never backs up or rolls back data kept
outside the package, so that choice is acceptable only if RoleBand's own records carry the
data side. The alternatives were Velopack, whose install hooks are too short for database
work and cannot veto a replacement, and a custom Inno or WiX updater.

## Decision

The Windows app is one MSIX per release: the WinUI host, the hash-locked Python runtime and
engine, the dashboard build and the PostgreSQL contrib modules, signed with the release
certificate ([decision 0012](0012-windows-distribution-and-signing.md)).

- Program files are the package's; every piece of history, credential and key lives in the
  account's LocalAppData, excluded from file-system virtualization
  ([decision 0004](0004-windows-native-engine-host.md)), so replacing or removing the
  package never touches it.
- Child processes keep the package's identity through the desktop-app process policy, so
  PostgreSQL and the engine run from the package's protected files.
- The app updates itself through Windows' package manager after its own authorization
  ([decision 0009](0009-windows-release-authorization.md)), with the replacement journaled
  and settled by the version that runs next ([decision 0010](0010-windows-update-journal.md)).
- A migration starts from a verified checkpoint
  ([decision 0008](0008-windows-pre-migration-checkpoints.md)), and the way back is the
  kept previous package, registered again with Windows' downgrade option, plus that
  checkpoint promoted under the previous runtime
  ([decision 0007](0007-windows-checkpoint-promotion.md)).
- An App Installer file, if used, may not check for updates on its own: offers and their
  consent stay with the app.

Development packages keep their separate trial identity, data namespace and trial key.

## Consequences

Windows owns file replacement, signature checks and Smart App Control; RoleBand owns
authorization, consent, data protection and recovery, and every entry point reads the same
journals before it opens the database. The first installed version is undone only once its
own release is kept, which the first update's download does. Acceptance still needs an
installed update and Undo with signed updater builds, uninstall and reinstall keeping
history, two standard accounts on one PC, and a clean machine with Smart App Control on;
`docs/testing.md` lists what each test covers. The tray panel and product UI build on this
package model.

## Alternatives considered

Velopack runs install hooks for 15 or 30 seconds and cannot refuse a replacement, too short
for a checkpoint and migration and unable to stop a version that cannot read the data. A
custom Inno or WiX updater would rebuild replacement, signature and rollback handling that
Windows already provides for MSIX, at a cost the plan only accepts if MSIX fails a concrete
requirement, which none of its trials did.
