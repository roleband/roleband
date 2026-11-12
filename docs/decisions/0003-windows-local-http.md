# 0003. Windows retained state and local HTTP authentication

## Context

Loopback ports are shared by Windows accounts. A checkout hash identifies code,
not an account or a running engine. A listener replacing a stopped engine must
not receive a reusable credential. Reusing a browser origin also lets a foreign
listener poison cached page code for a later engine.

## Decision

Windows retained state comes from the LocalAppData known folder, under RoleBand.
An absolute ROLEBAND_STATE_DIR overrides it for isolated development. Database,
cache, plugin and Fernet-key overrides remain explicit. Native ACLs protect
credentials, preparation state and discovery before sensitive files are created.

Packaged Windows HTTP always authenticates. Source development can enable the
same boundary with ROLEBAND_LOCAL_AUTH=1. Other source and Mac entry points retain
their existing access contract.

Each HTTP process holds an account-private discovery lock and generates a new
256-bit control key. The desktop supervisor gives each engine a random 128-bit
hostname under .localhost and an empty set of browser keys in the account-private
launcher/engine-session.json, which its API processes adopt and which ends with the
engine; any other HTTP process generates its own hostname. Its exclusive
socket binds only 127.0.0.1. Windows startup refuses authenticated mode outside
the exclusive-socket entry point. Because an engine's hostname outlives its API
processes, the supervisor binds that socket once and holds it for the engine's
life, handing each API process a duplicate (`socket.share`) through a one-time
file in the account-private launcher directory, once the process has asked for it
there under its own process ID and is one of the processes the supervisor started. The port is never free while
the tabs' origin is the engine's, so no other account's listener can answer at
that origin between API processes and read a tab's stored browser key. Discovery records the actual origin and control key in
launcher/http-engine.json. Native clients check its ownership and ACLs, connect
directly to 127.0.0.1 without DNS, proxies or redirects, and send the recorded Host.
The browser uses the engine's hostname, isolating its cache and tab storage
from earlier engines even when the port is reused. Localhost subdomains follow
[RFC 6761](https://www.rfc-editor.org/rfc/rfc6761.html#section-6.3). Browser support
still requires real acceptance on the supported Windows browser configuration.

Requests use HMAC-SHA256 with a request domain separator, key identifier, integer
Unix timestamp, random 128-bit nonce, method, exact origin, raw path and query,
and the SHA256 digest of the UTF8 body, joined by newlines. Signatures expire
after 45 seconds and accepted nonces cannot be reused. Replay memory is bounded
and refuses work at capacity. Replay memory and ticket lifetimes run on the
monotonic clock, and accepted nonces are kept for two signature
windows plus 45 seconds, so a backward wall-clock step of up to 45 seconds in all,
the size of an ordinary time correction, keeps every key and still refuses a used
signature. A larger step publishes a new control key in discovery, ends browser
sessions and clears replay memory, so no signature from before the step verifies;
native and engine clients read discovery before every request and continue without
a restart. Responses authenticate the request's
Authorization value, response status and complete response-body digest under a
separate domain separator. The transport bounds requests and responses to 16 MiB.

All API reads, writes, health and documentation require authentication. HTTP
upgrades are refused. Host and Origin must match the exact discovered origin,
including its port. The existing host, unsafe-origin, simple-content-type and
dashboard CSP protections remain in force. Public dashboard files expose no
account data.

Authenticated native control issues a browser-only ticket valid once for 60
seconds. The ticket travels in the URL fragment and is removed before app startup
requests or diagnostics. Its exchange returns a separate tab credential. That key
stays in memory/sessionStorage and signs requests; it is never sent as a bearer
or cookie. Browser credentials last as long as the engine and cannot issue another
handoff. The engine keeps 32; opening another ends the oldest. An API process
records a browser key before returning it and adopts the recorded keys when it
starts, so an API restart keeps open tabs; it refuses an adopted key's signatures
stamped in or before the second it started, since it has no memory of the nonces its
predecessor accepted. That refusal is a 401 without a proof, like any refusal, so a
tab signs a request refused that way once more, in a later second than the refusal,
when its clock reaches one within two seconds. Any other reply without a proof, a
second one, or an invalid response proof holds the browser connection closed until a
fresh app handoff. An engine restart or a large clock step requires
reopening through the app.

The schema-free preparation responder uses the same control authentication and
discovery. On Windows it has its own ephemeral port, avoiding an exclusive-socket
rebind during TCP TIME_WAIT. Discovery rotates when the full API becomes ready.

## Consequences

The Windows host must follow private discovery and authenticated health, not a
fixed browser URL or a public installation hash. It must open the browser through
the ticket request. A loopback listener can deny service but cannot learn a
reusable key from signed control traffic. Compromise of the same Windows account
or browser scripts is outside this boundary. This is not a network-facing login
system, and the API remains unsuitable for network exposure.

Real two-standard-account acceptance, packaged state retention and browser
lifecycle acceptance remain separate release requirements.
