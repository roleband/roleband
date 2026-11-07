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
verified offer, and a verified offer is never replaced by an older listing.
`tracker/platform/windows_updates.py` implements it; `desktop.py update consent|check`
is how the native host uses it.

## Consequences

A compromised certificate alone cannot push an update, and a correctly signed release for
another platform, package, publisher or feed is refused. Changing the release key needs a
release signed with the current one whose identity names the next. Publication tooling,
downloading and applying a package are separate steps. `tests/test_windows_release.py`,
`tests/test_windows_updates.py` and `launcher/windows/Tools/test_release.py` hold the
contract.

## Alternatives considered

Trusting the MSIX certificate alone would make the certificate the release authority and
lose the owner's separate approval. A NuGet Ed25519 library in the native host would add a
dependency and a second verifier for what the bundled runtime already verifies.
