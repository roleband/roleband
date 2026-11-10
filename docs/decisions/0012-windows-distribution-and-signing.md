# 0012: Windows releases ship on GitHub, signed with RoleBand's own certificate

## Context

Windows installs and updates an MSIX only when its signature traces to a publisher the
machine trusts, and treats a package from a different publisher as a different app. The
Microsoft Store signs and updates its own copies with its own update system, which would
replace RoleBand's updater ([decision 0010](0010-windows-update-journal.md)). A commercial
or Microsoft-run certificate adds a third party to every release. The macOS app already
publishes to `roleband/roleband`, and both apps read that repository's latest release.

## Decision

- The first Windows channel is the GitHub release; the Microsoft Store follows only after
  one release has been built, published and updated through RoleBand's own updater.
- Each GitHub release carries both apps' files under one version. Each platform attaches
  its own files to the published release and signs them with its own release key; an app
  reads a release without its own files as no update yet.
- The package is signed with RoleBand's own certificate, with no certificate authority or
  signing service. Its subject, `CN=RoleBand, O=RoleBand, DC=roleband, DC=com`, is the
  package's publisher and stays the same for good; a new certificate keeps that subject.
- Signatures are not timestamped, since that needs an outside time server. The certificate
  is valid for 25 years and is replaced with the same subject well before it expires.
- A workflow builds, signs and attaches the Windows files when a release is published, or
  when run by hand for a published release's tag, which signs only from `main`. The
  certificate and the Windows release key are secrets of a protected environment that runs
  only after the owner approves; the spare release key never leaves offline storage.

## Consequences

No single machine has to be present for a Windows release, and the macOS keys stay where
they are. Someone who can run the protected environment can sign a Windows update, so the
spare key is the way back from a compromise ([decision 0009](0009-windows-release-authorization.md)).
A first install needs the certificate trusted on the machine, which takes an administrator
once; updates after that need nothing. Smart App Control may refuse a publisher Microsoft
does not know, so a clean machine with it on is tested before each first release.

## Alternatives considered

A commercial code-signing certificate or Microsoft's signing service would remove the trust
step but puts an outside party in every release and, for the signing service, needs a
company the service accepts. A separate Windows release repository would let Windows
release on its own schedule at the cost of two release pages and two versions of one app.
Signing on the owner's machine only, as for macOS, makes every release wait on that machine.
