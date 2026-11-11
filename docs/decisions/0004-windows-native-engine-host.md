# 0004. Windows native engine host

## Context

A Windows desktop host must own the Python engine without depending on a source
checkout, shell scripts or a separately installed database. Closing the app must
stop its service and jobs cleanly. Engine failure needs bounded recovery without
finding and killing processes by name.

## Decision

Use C# with WinUI 3 and .NET 10. Keep lifecycle and authenticated transport in a
separate library so real engine tests exercise the window's implementation. The
dashboard remains in the browser. Native wording comes from the shared catalog.

The host takes an exclusive private desktop lease. It starts isolated native
Python with explicit state paths and a minimal environment. The engine publishes
its PID, creation time, resource root and random launch marker. A live predecessor
is refused; the host never terminates a process it did not start. A parent-only
standard-input pipe carries stop requests. EOF also stops the engine.
Runtime process records expire with their kernel identity. A dead predecessor's
resource path can belong to a previous package version in the same retained state.
A live predecessor or a record naming foreign retained state blocks startup.

The engine holds a private lease and initializes PostgreSQL outside cancellable
Job Objects. Migration and synthetic fixture work run as contained child services
with bounded awake-time deadlines. A normal desktop stop cancels and settles jobs
while holding the supervisor lock, ends the API, disposes connections and stops
the verified database. Ordinary source supervision retains job-survival behavior.

The native client verifies private discovery and response-body proofs. Health
must identify the expected product, version and origin. Request deadlines cover
headers and the complete bounded body. Recovery uses awake time, retries at most
three times within ten minutes and preserves an engine that cannot confirm a
clean stop.

Development packages have a separate MSIX identity and a trial marker. They use
synthetic fixtures, disable network jobs and usage sharing, and retain state in a
separate LocalAppData trial namespace. The packaging command produces unsigned
artifacts. Signing, trust establishment and deployment acceptance are separate.
Both hosts resolve LocalAppData through the native known-folder API with package
redirection disabled. The MSIX folder exclusion also prevents filesystem write
virtualization. A package cache cannot own retained history. Missing or invalid
trial metadata is refused before selecting writable state.

MSIX activation relaunches the host once with the [desktop-app process policy](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-updateprocthreadattribute)
that preserves package context throughout its descendants. PostgreSQL starts
restricted-token children; losing package context prevents them from executing
files protected by WindowsApps' conditional ACLs. The host keeps that context
instead of changing installation permissions or copying executable files into
writable state. Unpackaged launches do not relaunch.

## Consequences

Windows runtime wheels are hash-locked. Bundles carry an isolated Python runtime
and offline SDK wheels. MSIX deployment, data retention, two-account isolation and
recovery after package replacement still require their own acceptance trials.
An unpackaged startup test does not establish those properties.

## Alternatives considered

Rust adds a second implementation without resolving a measured C# limitation.
Mac shell scripts require a foreign shell and process model. Process-tree
enumeration cannot establish ownership across PID reuse. A general HTTP shutdown
endpoint widens the control surface when the parent already owns a private pipe.
