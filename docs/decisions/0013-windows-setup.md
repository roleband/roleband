# 0013: A first Windows install is one Setup program, approved by an administrator

## Context

Windows installs an MSIX only when the machine trusts its signer, and RoleBand signs with its
own certificate ([decision 0012](0012-windows-distribution-and-signing.md)). A first install
therefore took two steps the person had to know: add `RoleBand.cer` to Local Machine > Trusted
People through the certificate wizard, then open the package. The package cannot do the first
step itself: Windows checks the signer before any of its code runs.

## Decision

- Each Windows release carries `RoleBand-Setup-<version>.exe`, a native x64 program that needs
  no .NET on the machine, signed like the package. It installs the package of its own version
  from the feed it was built for, then opens RoleBand.
- Setup runs as the person who started it, the one RoleBand is installed for. It stops, saying
  why, on Windows before Windows 11 (build 22000), when it was started with administrator rights
  as another account, and where a policy allows only Store apps.
- Installing RoleBand needs an administrator's approval, every time. Setup starts a second copy
  of itself through Windows' administrator prompt, which only adds the certificate compiled
  into Setup to Local Machine > Trusted People; it never reads a certificate from a file or an
  argument. A refused prompt installs nothing.
- Setup trusts the package only after checking it: its size and SHA-256 against the release's
  metadata, its manifest's name, publisher and version against what Setup was built for, and
  Windows' own verification of its signature, whose signer must be the certificate Setup
  carries. The package is installed for the person, without administrator rights.
- In-app updates are unchanged: same signer, the update's signed manifest, no prompt.

## Consequences

A first install is one download and one approval. Windows still warns about a program from a
publisher it does not know (SmartScreen's Run anyway), Smart App Control can refuse Setup
outright, and Windows in S mode runs only Store programs: the download page says so, and the
Microsoft Store channel is the way past all three. Uninstalling RoleBand cannot run its code,
so the certificate stays trusted until it is removed:
`Get-ChildItem Cert:\LocalMachine\TrustedPeople | Where-Object Subject -eq 'CN=RoleBand, O=RoleBand, DC=roleband, DC=com' | Remove-Item`,
as an administrator.

## Alternatives considered

- **The package inside Setup**: a 350 MB program per release, and no smaller than downloading
  the package it carries.
- **A PowerShell script**: blocked by the default execution policy, and harder to read than a
  signed program.
- **An App Installer file**: it installs a package but cannot trust its signer.
- **Trusting for the person only (Current User)**: it would let anyone trust RoleBand without
  an administrator, which installing it requires.
