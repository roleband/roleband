# 0001. Windows embedded database authentication

## Context

Windows clients reach embedded PostgreSQL through TCP. Trust login permits
other local accounts to use that database. File modes alone cannot protect
Windows credentials. The bundled PostgreSQL build has no TLS support.

## Decision

The Windows adapter owns initialization and startup. A protected inheritable
ACL grants the current account and SYSTEM access to each cluster and its
credential directory. Initialization pins UTF8, an explicit locale and SCRAM.
The default locale is en_US.UTF-8. The C locale fails accented case matching.

The password lives in a private libpq password file outside PGDATA. A private
transient file supplies initdb and is removed when initialization returns.
Connection URLs contain the password-file path. Credentials stay out of process
arguments. An initialization marker binds credentials to the cluster path and
PostgreSQL major. It is written last, before any server starts, so a password file
without a marker, beside a data folder no server has run, is a first initialization
that never finished and holds no history: its folder and credentials are renamed
aside, never deleted, and initialization starts again. Unrecognized clusters, a
cluster that has run without its marker, and a marker whose cluster is missing
require recovery or fresh storage.

A private interprocess lock serializes startup. Each start chooses a loopback
port and regenerates runtime settings. Before connecting, the adapter verifies
the pidfile against the bundled executable, account, process start time, data
directory and owning TCP listener. A stale or foreign endpoint is refused.

## Consequences

Existing trust-login Windows development clusters require an explicit recovery
path. They are preserved on refusal. Logical dumps can be restored into a fresh
authenticated cluster. POSIX keeps its socket lifecycle.

The bundled clients use narrow Windows arguments. Non-ASCII runtime and storage
paths use Windows short-path aliases. A volume without a representable alias
requires ASCII storage and runtime paths until the client build supports UTF8
arguments directly.

Process and listener checks establish ownership at the time of verification.
They do not provide a cryptographic server identity for a connection established
later. Complete Windows account isolation also requires authenticated HTTP and
control, stable process ownership and acceptance with two standard accounts.

## Alternatives considered

Trust login cannot separate accounts sharing a computer. Embedding a password in
the URL exposes it through client-tool arguments. TLS identity requires a different
database build or transport contract. C with UTF8 stores Unicode but does not meet
the accented case-matching contract.
