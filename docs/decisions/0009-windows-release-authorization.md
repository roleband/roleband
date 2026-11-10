# 0009: Windows updates are authorized by the owner's Ed25519 key

## Context

An MSIX signature proves which certificate signed a package; it does not say the owner
released it for this installation, on this feed, as a newer version. Windows will register
any validly signed higher package version, and the app updates itself, so it needs its own
authorization check before it downloads or applies anything. .NET 10 has no standalone
Ed25519, while the engine's bundled, hash-locked Python runtime already ships `cryptography`.

## Decision

A Windows release is four files, as on the Mac: `RoleBand-<version>-Windows-x64.msix`, its
`.sha256`, its `.json` metadata and a 64-byte `.sig`, an Ed25519 signature over the checksum
bytes followed by the metadata bytes. The metadata is its own schema (format 1): stable
version, four-part package version whose first three parts are that version, package name,
publisher, architecture, minimum Windows build, source commit and tag, feed, package file
name, SHA-256, size and the hash of the release key.

An installed package carries the identity it trusts: one feed, one release public key, its
package name and publisher. It accepts an offer only when the signature verifies with that
key, the metadata has exactly that shape and names that identity, the checksum file names
the same digest and package, and the version is newer than the installed one. The
downloaded package must match the signed digest and size before it is applied. Verification
runs in `tracker/platform/windows_release.py`; `launcher/windows/Tools/release.py` writes
and checks release folders.

Trial packages trust a trial key and feed; production keys stay on the Mac. A build
without an identity never asks a feed.

Checking follows the Mac's contract. Nothing is requested before an explicit choice,
recorded with the words shown and their language. Automatic checks stay off until enabled
and run at most once a day, failed attempts included; a manual check authorizes one
request. A 403 or 429 delays every check by at least a minute, or until the quota resets.
The listing must be the feed's published, stable latest release; it is read without
redirects, credentials or cookies and bounded to 256 KiB. Its three small release files
are fetched from the feed's download path, following at most five redirects and only to
`release-assets.githubusercontent.com` or the same path. A failed check keeps the last
verified offer, and a verified offer is never replaced by an older listing. A check counts for
the version that made it, so after an update or an Undo no earlier "up to date" stands. A version
this installation updated to and undid is not offered again; the next newer release is.
`tracker/platform/windows_updates.py` implements it; `desktop.py update consent|check`
is how the native host uses it.

`desktop.py update download` fetches the kept offer's package under the same redirect
rules into `packages/`, resuming an interrupted download where it stopped and refusing a
resume at another offset or a body past the signed size. The file is kept only once it
matches the signed digest and size, with its signed release files beside it, so it can be
verified again before it is registered, including as the version to return to after a
failed update (`tracker/platform/windows_packages.py`). The two newest verified packages, the
running version's and the one an unfinished update returns to are kept; older ones are
releases that can be downloaded again. While the update journal cannot be read, none is removed.
Windows keeps no copy of an installed package, so before the first update's package the
download keeps the running version's own published release, verified the same way; if that
fails, the update is not downloaded. A kept package that no longer matches its signed digest
is downloaded again rather than refused for ever.

Before fetching anything, the download checks for free space: each package it still needs,
counted at the update's size until its own is known, Windows' copy of the update while it
installs, and a margin. Without it the answer is `space` with the bytes needed, and nothing is
fetched. A failure names its kind: `space` for a full disk, `offline` for a connection that
ended (the partial file stays and the next attempt resumes it), `check` for a package that is
not the signed release, and `download` otherwise. While it runs, the command writes the bytes
received and the total as JSON lines on stderr; its answer stays the one JSON object on
stdout. Cancel ends the command and every process it started, and keeps the partial file.

## Consequences

A compromised certificate alone cannot push an update, and a correctly signed release for
another platform, package, publisher or feed is refused. Changing the release key needs a
release signed with the current one whose identity names the next. An identity may also name a
spare key, kept offline: a release it signs is accepted too, so a lost or leaked release key is
replaced by a release whose package names new keys. Publication tooling,
downloading and applying a package are separate steps. `tests/test_windows_release.py`,
`tests/test_windows_updates.py` and `launcher/windows/Tools/test_release.py` hold the
contract.

## Alternatives considered

Trusting the MSIX certificate alone would make the certificate the release authority and
lose the owner's separate approval. A NuGet Ed25519 library in the native host would add a
dependency and a second verifier for what the bundled runtime already verifies.
