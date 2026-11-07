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

Trial packages trust a trial key and feed; production keys stay on the Mac.

## Consequences

A compromised certificate alone cannot push an update, and a correctly signed release for
another platform, package, publisher or feed is refused. Changing the release key needs a
release signed with the current one whose identity names the next. Release tooling for
publication and the update check itself are separate steps. `tests/test_windows_release.py`
and `launcher/windows/Tools/test_release.py` hold the contract.

## Alternatives considered

Trusting the MSIX certificate alone would make the certificate the release authority and
lose the owner's separate approval. A NuGet Ed25519 library in the native host would add a
dependency and a second verifier for what the bundled runtime already verifies.
