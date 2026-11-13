"""Error codes, and what each one means to the process and to HTTP.

One table: a code names its exit category, the HTTP status the engine answers
it with, and whether an identical retry may succeed. The client maps a code
from the engine to its exit status through this table, never from the HTTP
status, so a transport answering 500 for a refusal cannot turn a policy
refusal into a retryable failure.

Standard library only: the client imports this module on every run.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The response contract this engine and client speak. A reply with another
#: major version is refused as incompatible.
CONTRACT_VERSION = "1.0"

#: Exit statuses by category.
EXIT_OK = 0
EXIT_INTERNAL = 1
EXIT_INVALID = 2
EXIT_UNAVAILABLE = 3
EXIT_REFUSED = 4
EXIT_NOT_FOUND = 5
EXIT_CONFLICT = 6
EXIT_INPUT_REQUIRED = 7
EXIT_DEADLINE = 8
EXIT_PARTIAL = 9
EXIT_INCOMPATIBLE = 10
EXIT_INTERRUPTED = 130


@dataclass(frozen=True)
class Outcome:
    exit_status: int
    http_status: int
    retryable: bool


#: Every error code either side may send. A code missing here is a defect:
#: `outcome()` reads it as an internal failure, and a test fails on any code
#: the engine or the client raises that this table does not name.
OUTCOMES: dict[str, Outcome] = {
    # 1: internal or unclassified.
    "internal_error": Outcome(EXIT_INTERNAL, 500, False),
    # 2: the request is wrong, or names something this client or engine lacks.
    "invalid_arguments": Outcome(EXIT_INVALID, 400, False),
    "invalid_input": Outcome(EXIT_INVALID, 422, False),
    "unknown_operation": Outcome(EXIT_INVALID, 404, False),
    "unsupported_operation": Outcome(EXIT_INVALID, 400, False),
    "context_required": Outcome(EXIT_INVALID, 400, False),
    "context_not_found": Outcome(EXIT_INVALID, 400, False),
    "context_invalid": Outcome(EXIT_INVALID, 400, False),
    # 3: no engine, or the connection to it failed.
    "engine_unavailable": Outcome(EXIT_UNAVAILABLE, 503, True),
    "engine_not_ready": Outcome(EXIT_UNAVAILABLE, 503, True),
    "transport_error": Outcome(EXIT_UNAVAILABLE, 502, True),
    "transport_unverified": Outcome(EXIT_UNAVAILABLE, 502, False),
    # The context is pinned to one workspace and another one answered.
    "workspace_mismatch": Outcome(EXIT_UNAVAILABLE, 409, False),
    # 4: the person's settings refuse this operation.
    "access_disabled": Outcome(EXIT_REFUSED, 403, False),
    "writes_disabled": Outcome(EXIT_REFUSED, 403, False),
    # 5: the resource does not exist.
    "not_found": Outcome(EXIT_NOT_FOUND, 404, False),
    # 6: the resource changed, or the key was used for another request.
    "revision_conflict": Outcome(EXIT_CONFLICT, 409, False),
    "idempotency_conflict": Outcome(EXIT_CONFLICT, 409, False),
    # 7: a person has to decide.
    "approval_required": Outcome(EXIT_INPUT_REQUIRED, 409, False),
    # 8: out of time or budget.
    "deadline_exceeded": Outcome(EXIT_DEADLINE, 504, True),
    "rate_limited": Outcome(EXIT_DEADLINE, 429, True),
    # 9: some items succeeded, or an external outcome is unknown.
    "partial_result": Outcome(EXIT_PARTIAL, 207, False),
    "operation_cancelled": Outcome(EXIT_PARTIAL, 409, False),
    # 10: the two sides do not speak the same contract.
    "contract_incompatible": Outcome(EXIT_INCOMPATIBLE, 502, False),
    # 130: the person interrupted this process.
    "interrupted": Outcome(EXIT_INTERRUPTED, 499, False),
}

_UNKNOWN = OUTCOMES["internal_error"]


def outcome(code: str) -> Outcome:
    """The outcome of `code`; an unknown code is an internal failure."""
    return OUTCOMES.get(code, _UNKNOWN)


def compatible(contract_version: object) -> bool:
    """Whether a reply's contract version shares this side's major version."""
    if not isinstance(contract_version, str):
        return False
    major, _, minor = contract_version.partition(".")
    return major == CONTRACT_VERSION.partition(".")[0] and minor.isdigit()
