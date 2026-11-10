"""Static collection policy vocabulary; no database or transport dependencies.

`collection_access` is the ONE decision point for whether a request may be
made (`docs/sources.md`, "How a request is decided"). It answers two
questions and keeps them apart:

* **Operator deny** — `Settings.sync_policy_denied_providers`, a provider-level
  hard stop that no user action lifts.
* **Walled and not consented** — a source whose register row records a wall (`source_review.Wall`) is collected
  for a company only when the user followed that company through a consent
  dialog. The user is asked once: a consent stands when the register later
  records a changed robots file, a different wall or a stronger tier, because
  the question for the user is the same.
  Consent is COMPANY-level, so it is checked only when the caller names the
  company; a provider-level question (the scheduler's provider table, a bare
  transport) is answered by the operator deny alone. Every execution path that
  collects names its company and passes the consent it loaded.

It also releases the **fetch tier**: a walled,
consented company is fetched with its register row's `fetch_tier`; every other
answer carries `FetchTier.IDENTIFIED`. A provider-level question never gets a
tier above identified, because consent is per company.

A third answer is not a refusal: **direction**. A company on a user-directed
source is read only at its user's direction (`direction_wait`): never followed
without the user's agreement, and scanned on a timer only when that agreement
chose regular scans. It is the ONE rule every reader of "is this scanned without
the person asking" calls: the scheduler (`schedule_status.waits_for_user`), the
status and Coverage reports (`scanned_automatically`), scope promotion, role
discovery and the directory sweep.

No database access here: the caller reads the stored consent fingerprint (and
`scan_on_schedule`) off the company's row and passes it in, which keeps this
module importable by transports, recipes and scripts alike.
"""

from __future__ import annotations

from dataclasses import dataclass

from tracker.config import Settings, get_settings
from tracker.source_review import (
    FetchTier,
    SourceReview,
    declared_adapter,
    directed_source,
    is_wall_consent,
    source_wall,
    user_directed_source,
)

__all__ = [
    "ON_REQUEST",
    "USER_DIRECTED",
    "CollectionAccess",
    "CollectionPolicyDenied",
    "FetchTier",
    "collection_access",
    "company_directed_source",
    "direction_wait",
    "is_wall_consent",
    "needs_agreement",
    "scanned_automatically",
]

#: `direction_wait`'s answers. `user_directed`: a company on a user-directed
#: source with no agreement (followed before the dialog asked, or not followed
#: at all); `on_request`: agreed, and the agreement chose to be read only when
#: the user asks.
USER_DIRECTED = "user_directed"
ON_REQUEST = "on_request"


class CollectionPolicyDenied(PermissionError):
    """Local denial, never evidence of source failure or disappearance."""

    def __init__(self, access: CollectionAccess):
        self.access = access
        super().__init__(access.reason)


@dataclass(frozen=True)
class CollectionAccess:
    provider_key: str
    reason: str | None = None
    #: The refusal is a wall awaiting the user's consent, not an operator deny.
    #: Reported apart so a screen can offer the consent rather than a dead end.
    walled: bool = False
    #: The fetch tier this request may use. `IDENTIFIED` unless
    #: the company is walled AND consented, when it is the register row's own
    #: tier. Released here and nowhere else, so no path can escalate on its own.
    tier: FetchTier = FetchTier.IDENTIFIED

    @property
    def denied(self) -> bool:
        """For gates that report or refuse rather than execute (scheduler, ops)."""
        return self.reason is not None

    def require(self) -> None:
        if self.reason is not None:
            raise CollectionPolicyDenied(self)


def collection_access(
    provider_key: str,
    *,
    company: str | None = None,
    settings: Settings | None = None,
    consent: str | None = None,
) -> CollectionAccess:
    """May RoleBand collect this provider (for this company)?

    Known company identity survives alternate execution (notably recipes): a
    recipe for a named company (a built-in, a catalog row or a connector
    family's company, `source_review.declared_adapter`) cannot shed its
    declared provider's deny or wall. `consent` is the fingerprint stored when
    the user consented (`TrackedCompany.consent_fingerprint`). Any stored
    WALL consent unlocks the wall (`is_wall_consent`): the fingerprint records
    what was agreed and is never compared with the register's current one. An
    agreement to a user-directed source showed no wall and unlocks none.
    """
    settings = settings if settings is not None else get_settings()
    declared_provider = declared_adapter(company, provider_key)
    for candidate in (provider_key, declared_provider):
        if candidate in settings.sync_policy_denied_providers:
            return CollectionAccess(candidate, f"provider {candidate!r} denied by collection policy")
    if company is not None:
        walled = source_wall(provider_key, company=company)
        if walled is not None and not is_wall_consent(consent):
            return CollectionAccess(
                walled.provider,
                f"{company!r} is walled ({walled.wall}) and the user has not consented to collecting it",
                walled=True,
            )
        if walled is not None:
            return CollectionAccess(provider_key, tier=walled.fetch_tier)
    return CollectionAccess(provider_key)


def company_directed_source(provider_key: str, company: str | None = None) -> SourceReview | None:
    """The register row of the user-directed source a company is collected
    through, or None. Resolved with the company, as every gate here is."""
    return directed_source(provider_key, company=company)


def direction_wait(
    provider_key: str,
    company: str | None,
    consent: str | None,
    scan_on_schedule: bool = False,
) -> str | None:
    """Why automatic work leaves this company to its user, or None if it may
    read it unasked.

    None for every company not on a user-directed source. On one, the user's
    agreement (any stored consent: a walled-and-directed company's agreement
    is its wall consent) and its choice decide: `USER_DIRECTED` without an
    agreement, `ON_REQUEST` when the agreement chose to be read only when the
    user asks, None when it chose regular scans.
    """
    if not user_directed_source(provider_key, company=company):
        return None
    if not consent:
        return USER_DIRECTED
    if not scan_on_schedule:
        return ON_REQUEST
    return None


def needs_agreement(provider_key: str, company: str | None, consent: str | None) -> bool:
    """A company on a user-directed source its user never agreed to. Work the
    user did not start for this very company (role discovery over every
    followed company, the directory sweep) leaves it unread."""
    return direction_wait(provider_key, company, consent) == USER_DIRECTED


def scanned_automatically(
    provider_key: str,
    company: str,
    consent: str | None,
    *,
    scan_on_schedule: bool = False,
    settings: Settings | None = None,
) -> bool:
    """Whether RoleBand scans this followed company without the user asking.

    Operator policy and walls without the user's consent prevent collection.
    A user-directed company is scanned unasked only when its agreement chose
    regular scans (`direction_wait`). Coverage therefore rings only for allowed
    companies scanned automatically.
    """
    access = collection_access(provider_key, company=company, settings=settings, consent=consent)
    return not access.denied and direction_wait(provider_key, company, consent, scan_on_schedule) is None
