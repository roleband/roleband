# 0002. Windows supervised process ownership

## Context

Windows process groups do not provide POSIX descendant containment or signals.
Supervisor restarts must preserve job runs, and supervisor exit must end the API.
PID reuse requires kernel identity checks. Database processes must outlive a
cancelled scan.

## Decision

Each Windows trampoline enters an unnamed, account-private Job Object before
creating its command. The trampoline holds the sole non-inheritable handle with
kill-on-close enabled. Normal exit and forced termination both remove descendants.
Jobs survive supervisor exit. Services additionally watch a pinned supervisor
kernel handle and terminate their containment when it signals process exit.

Each run gets a hidden console. A disposable helper attaches to that console to
send CTRL_BREAK without changing the supervisor's console. Cooperative commands
can clean up during the grace period. Escalation terminates the verified kernel
object and closes its containment. Cancellation verifies account, start time and
run marker, with the state directory defining the recovery namespace.

Windows virtualenv redirectors introduce another PID. Launch the native
interpreter with its virtualenv launcher context so the owning process and the
recorded kernel PID agree. Windows status bits use a signed 32-bit representation
for the existing run column.

Timeouts use QueryUnbiasedInterruptTime. Keep-awake requests belong to the
trampoline thread. Cancellable processes can attach to an existing verified
database but cannot initialize or restart PostgreSQL themselves.

## Consequences

The engine host must start and recover PostgreSQL before dispatching database
work. A killed trampoline can leave no result file, so the supervisor also uses
the process state to settle a run. Physical sleep/resume acceptance remains a
separate hardware trial.

## Alternatives considered

Enumerating and killing a process tree can race new descendants and PID reuse.
Putting all jobs in a supervisor-owned kill-on-close object ends active jobs on
supervisor failure. TerminateProcess alone gives cooperative commands no cleanup
opportunity. Attaching the supervisor to a job console changes its own process
context, so the signal helper owns that temporary attachment.
