"""`doctor` and `context.export`: what an assistant reads to diagnose the
engine, and one opportunity's context as a packet it can keep.

`doctor` is the engine's own status (`GET /api/status`, which the dashboard's
badge and the watchdog read) as a list of checks, and the settings this
engine runs with that differ from their defaults. Every string in it passes
`redact` first: a value under a secret's name, a credential in a URL, a
token-shaped run of characters and a path outside the workspace never leave
the engine. It names what is set, never what the secret is.

`context.export` reads one opportunity's posting text, pay evidence and
company facts, and the person's pursuit of it, in one snapshot. A category the
person does not share is left out (`policy.shared`): their pursuit, or the
estimates and their sources under market statistics, and the manifest's
`left_out` names it. The packet is canonical JSON (sorted keys,
no spaces, UTF-8) and is answered as that text, so its bytes are kept: the
same inputs give the same bytes, and `manifest.packet_sha256` proves it. A
value that moves without the posting changing (the time it was last seen, an
estimate's run time, the listing's age in days) is in the manifest's source
timestamps, not the packet. A packet longer than the tool tier's budget comes
in parts: `continue_with` reads the next from its first character and names
the packet's hash, so a part of a packet that changed since is refused, and
the parts joined are the packet. A company fact's observation time is in the
manifest too, beside the fact's value and source in the packet.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Collection, Iterable, Mapping
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal, get_args

from pydantic import BaseModel, Field, SecretStr, model_validator
from pydantic.config import JsonDict
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.agents.config import AgentAccessConfig
from tracker.agents.operations.descriptor import (
    DataClass,
    EngineEffects,
    OperationDescriptor,
    Shape,
    ToolTier,
)
from tracker.agents.operations.envelope import NextAction, OperationError
from tracker.agents.operations.opportunities import (
    DETAIL_BUDGET_BYTES,
    OpportunityGetInput,
    opportunity,
)
from tracker.agents.operations.outcomes import CONTRACT_VERSION
from tracker.agents.operations.policy import shared
from tracker.agents.operations.search import PAGE_BUDGET_BYTES
from tracker.config import Settings
from tracker.db.models import CompanyProfile, Favorite, Job, Pursuit
from tracker.health import REFRESHED_STATUSES
from tracker.plugins.registry import COMPANY_FACTS, reader_providers
from tracker.profiles import store as profile_store

_CODE: JsonDict = {"x-text": "code"}
_IDENTIFIER: JsonDict = {"x-text": "identifier"}
_CONTENT: JsonDict = {"x-text": "content"}
_DIAGNOSTIC: JsonDict = {"x-text": "diagnostic"}
_EVERY_TIER: tuple[ToolTier, ...] = ("small", "standard", "full")

# --- redaction --------------------------------------------------------------- #

SECRET = "[redacted]"
OUTSIDE = "[path outside the workspace]"

#: A setting or key whose value is a credential by its name alone.
_SECRET_NAME = re.compile(r"(key|secret|token|passw|credential|cookie|auth|proxy_url|database_url)", re.IGNORECASE)
#: Credentials by their shape, wherever they stand in a string.
_SECRET_SHAPES = (
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{20,}"),
    re.compile(r"xox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"(?:AKIA|ASIA)[0-9A-Z]{16}"),
    re.compile(r"phc_[A-Za-z0-9]{20,}"),
    re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    # Any long run of letters and digits mixed: a key in an unknown format.
    re.compile(r"(?<![A-Za-z0-9])(?=[A-Za-z0-9_+=-]*[0-9])(?=[A-Za-z0-9_+=-]*[A-Za-z])[A-Za-z0-9_+=-]{32,}"),
)
#: `scheme://user:password@` in a URL. It stops at `?` and `#`, so an `@` in a
#: query value cannot swallow the parameter's name and hide it from `_SECRET_QUERY`.
_USERINFO = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)[^/\s@?#]+@")
#: A query or fragment parameter that carries a credential (`#access_token=`
#: is how an implicit sign-in returns one).
_SECRET_QUERY = re.compile(
    r"(?i)([?&#](?:key|api_key|apikey|token|access_token|secret|sig|signature|password|auth)=)[^&#\s]+"
)
#: An absolute path, a home-relative one, a Windows drive path or a UNC share
#: (`\\server\share`), not inside a URL.
_PATH = re.compile(r"(?<![\w:/.\\-])(?:~/|/|[A-Za-z]:[\\/]|\\\\)[^\s\"'<>|,;]+")
#: A setting whose whole value is a path: read as one, spaces included.
_WHOLE_PATH = re.compile(r"(?:~/|/|[A-Za-z]:[\\/]|\\\\)")


class Redactor:
    """Redacts strings; a path inside `workspace` is kept relative to it."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace.expanduser().resolve()
        self.count = 0

    def text(self, value: str) -> str:
        out = _USERINFO.sub(self._sub(lambda m: f"{m.group(1)}{SECRET}@"), value)
        out = _SECRET_QUERY.sub(self._sub(lambda m: f"{m.group(1)}{SECRET}"), out)
        # Paths first: a long path is not a key, and a key inside a path goes with it.
        out = _PATH.sub(self._sub(lambda m: self._path(m.group(0))), out)
        for shape in _SECRET_SHAPES:
            out = shape.sub(self._sub(lambda _m: SECRET), out)
        return out

    def value(self, name: str, value: Any) -> Any:
        """One setting's value as the doctor may show it."""
        if value is None or value == "":
            return value
        if isinstance(value, SecretStr) or (isinstance(value, str) and _SECRET_NAME.search(name)):
            self.count += 1
            return SECRET
        if isinstance(value, bool | int | float):
            return value
        if isinstance(value, Path) or (isinstance(value, str) and _WHOLE_PATH.match(value)):
            shown = self._path(str(value))
            if shown != str(value):
                self.count += 1
            return shown
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, Mapping):
            return [
                f"{self.text(str(key))}={self.value(f'{name}.{key}', item)}"
                for key, item in sorted(value.items(), key=lambda kv: str(kv[0]))
            ]
        if isinstance(value, Iterable):
            items = [self.value(name, item) for item in value]
            return sorted(str(item) for item in items) if isinstance(value, set | frozenset) else [
                str(item) for item in items
            ]
        return self.text(str(value))

    def _path(self, found: str) -> str:
        path = Path(found).expanduser()
        # A path this platform does not read as absolute (a drive or a share
        # elsewhere) cannot be inside the workspace; resolving it would join it
        # to the working directory.
        if not path.is_absolute():
            return OUTSIDE
        try:
            relative = path.resolve().relative_to(self.workspace)
        except (ValueError, OSError, RuntimeError):
            return OUTSIDE
        return "workspace" if str(relative) == "." else f"workspace/{relative.as_posix()}"

    def _sub(self, replace: Any) -> Any:
        def counted(match: re.Match[str]) -> str:
            replaced = replace(match)
            if replaced != match.group(0):
                self.count += 1
            return replaced
        return counted


# --- doctor ------------------------------------------------------------------ #

CheckState = Literal["ok", "attention", "failing"]
SettingValue = bool | int | float | str | list[str] | None


class DoctorCheck(Shape):
    #: What is checked, as a stable code.
    check: str = Field(json_schema_extra=_CODE)
    state: CheckState = Field(json_schema_extra=_CODE)
    #: English for logs, with the figures the check read.
    summary: str = Field(json_schema_extra=_DIAGNOSTIC)


class DoctorSetting(Shape):
    #: A setting this engine runs with that differs from its default.
    name: str = Field(json_schema_extra=_CODE)
    #: Its value, redacted: a secret reads `[redacted]`, a path outside the
    #: workspace `[path outside the workspace]`.
    value: SettingValue = Field(json_schema_extra=_DIAGNOSTIC)


class DoctorInput(Shape):
    tier: ToolTier = Field(default="small", description="The caller's tool tier, which bounds the report.")


class DoctorReport(Shape):
    engine_version: str = Field(json_schema_extra=_IDENTIFIER)
    contract_version: str = Field(json_schema_extra=_IDENTIFIER)
    install: Literal["app", "source"] = Field(json_schema_extra=_CODE)
    #: Failing checks first, then those that need attention, then the rest.
    checks: list[DoctorCheck]
    #: By name. Cut to the tier's budget when `continue_with` is not empty.
    settings: list[DoctorSetting]
    #: How many values were redacted.
    redacted: int = Field(ge=0)
    #: Settings too long for the full tier, by name: each value in `settings`
    #: is its start, ending with a marker that gives the whole value's length.
    #: Shortened after redaction, so a secret is never part of what is kept.
    settings_shortened: list[str] = Field(default_factory=list, json_schema_extra=_CODE)
    #: Settings with no room in the full tier even shortened, by name, left out of `settings`.
    settings_left_out: list[str] = Field(default_factory=list, json_schema_extra=_CODE)
    continue_with: list[NextAction] = Field(default_factory=list)


DOCTOR = OperationDescriptor(
    id="doctor",
    summary="Diagnose the engine: its checks and the settings it runs with, secrets and outside paths redacted.",
    input=DoctorInput,
    result=DoctorReport,
    access="read",
    idempotency="read",
    engine_effects=EngineEffects(),
    tool_tiers=_EVERY_TIER,
    # Its checks report how the postings are collected; it holds no person's data.
    data_classes=("public_posting",),
    examples=({},),
)

#: How each check reads its state; a status field missing reads `ok`.
_STATE_ORDER: dict[CheckState, int] = {"failing": 0, "attention": 1, "ok": 2}


def _checks(status: Mapping[str, Any], access: AgentAccessConfig) -> list[DoctorCheck]:
    checks: list[tuple[str, CheckState, str]] = []
    checks.append(("database", "ok" if status.get("db") == "ok" else "failing", f"database {status.get('db')}"))
    supervisor = status.get("supervisor") or {}
    state = supervisor.get("state")
    checks.append((
        "supervisor",
        "ok" if state == "running" else "attention" if state == "maintenance" else "failing",
        f"supervisor {state}" + (f" ({supervisor['reason']})" if supervisor.get("reason") else ""),
    ))
    age = status.get("last_success_age_hours")
    checks.append((
        "freshness",
        "attention" if status.get("stale") else "ok",
        f"oldest read {age if age is not None else 'never'} h ago, stale after {status.get('freshness_max_hours')} h",
    ))
    last = status.get("last_run_status")
    checks.append((
        "last_run",
        "ok" if last in (None, "running", *REFRESHED_STATUSES) else "attention",
        f"last run {last or 'none'}, {status.get('last_run_new') or 0} new of {status.get('last_run_seen') or 0} seen",
    ))
    stuck = status.get("stuck_running") or 0
    checks.append(("stuck_runs", "failing" if stuck else "ok", f"{stuck} runs without a heartbeat"))
    stale = list(status.get("derivations_stale") or [])
    checks.append((
        "derivations", "attention" if stale else "ok", f"behind: {', '.join(stale)}" if stale else "every pass current",
    ))
    coverage = status.get("bindings_attention") or {}
    checks.append((
        "coverage",
        "failing" if coverage.get("outage") else "attention" if coverage.get("flagged") else "ok",
        f"{coverage.get('flagged', 0)} of {coverage.get('followed', 0)} followed companies flagged: "
        f"{coverage.get('stale', 0)} not read in full lately, {coverage.get('empty', 0)} empty",
    ))
    stopped = sorted(job["job"] for job in status.get("jobs") or [] if job.get("state") == "stopped")
    checks.append((
        "jobs", "attention" if stopped else "ok", f"stopped: {', '.join(stopped)}" if stopped else "no job stopped",
    ))
    preparation = status.get("preparation")
    if preparation:
        failed = [part for part in ("database", "model", "service") if preparation.get(part) == "failed"]
        checks.append((
            "preparation", "failing" if failed else "ok",
            f"failed: {', '.join(failed)}" if failed else "database, model and service prepared",
        ))
    switch = status.get("matching_switch") or "none"
    checks.append((
        "matching_model", "attention" if switch != "none" else "ok",
        f"matching model {switch}" if switch != "none" else "matching model settled",
    ))
    withheld = [name for name in get_args(DataClass) if not shared(access, name)]
    checks.append((
        "agent_access", "ok",
        f"reads {'on' if access.enabled else 'off'}, changes {'on' if access.allow_writes else 'off'}, "
        + (f"not shared: {', '.join(withheld)}" if withheld else "every category shared"),
    ))
    ordered = sorted(checks, key=lambda item: _STATE_ORDER[item[1]])
    return [DoctorCheck(check=check, state=state, summary=summary) for check, state, summary in ordered]


def _settings(settings: BaseModel, redactor: Redactor) -> list[DoctorSetting]:
    out = []
    for name, field in sorted(type(settings).model_fields.items()):
        value = getattr(settings, name)
        try:
            default = field.get_default(call_default_factory=True)
        except Exception:  # noqa: BLE001 - a default that cannot be built is reported as differing
            default = object()
        if value == default:
            continue
        out.append(DoctorSetting(name=name, value=redactor.value(name, value)))
    return out


#: Ends a text value the full tier holds only the start of.
_SHORTENED_TEXT = "… [shortened from {count} characters]"
#: The last item of a list value the full tier holds only the first items of.
_SHORTENED_LIST = "[shortened from {count} items]"


def _longest(count: int, fits: Callable[[int], bool]) -> int:
    """The largest `n` up to `count` that `fits`, which holds for every
    smaller one too; 0 when none does."""
    low, high = 0, count
    while low < high:
        middle = (low + high + 1) // 2
        if fits(middle):
            low = middle
        else:
            high = middle - 1
    return low


def _shorten(entry: DoctorSetting, cap: int) -> DoctorSetting:
    """`entry` with a text or list value cut to at most `cap` bytes of JSON,
    its marker included; any other value, or one within `cap`, is kept whole.
    A marker longer than `cap` is kept alone."""
    value = entry.value
    if _size(value) <= cap:
        return entry
    if isinstance(value, str):
        text_marker = _SHORTENED_TEXT.format(count=len(value))
        kept = _longest(len(value), lambda n: _size(value[:n] + text_marker) <= cap)
        return entry.model_copy(update={"value": value[:kept] + text_marker})
    if isinstance(value, list):
        list_marker = _SHORTENED_LIST.format(count=len(value))
        kept = _longest(len(value), lambda n: _size([*value[:n], list_marker]) <= cap)
        return entry.model_copy(update={"value": [*value[:kept], list_marker]})
    return entry


def _fit_full(entries: list[DoctorSetting], room: int) -> tuple[list[DoctorSetting], list[str], list[str]]:
    """The settings the full tier holds, the names of those it holds
    shortened, and the names of those it cannot hold at all.

    Every value is held whole up to one length, the longest that lets the
    whole list fit, and longer ones are cut to it: a short setting is never
    cut to make room for a long one. Only when the markers alone do not fit
    are settings left out by name.
    """

    def fitted(cap: int) -> tuple[list[DoctorSetting], list[str], int]:
        kept = [_shorten(entry, cap) for entry in entries]
        names = [entry.name for entry, held in zip(entries, kept, strict=True) if held is not entry]
        used = sum(_size(held.model_dump(mode="json")) + 1 for held in kept)
        return kept, names, used + sum(_size(name) + 1 for name in names)

    # Raising the length grows the list only while the same values are cut:
    # at a value's own size it is whole again, and its marker and name go.
    # So the longest length that fits is found between those sizes: the
    # largest size that fits starts the stretch that is then halved.
    sizes = sorted({_size(entry.value) for entry in entries})
    if not sizes or fitted(sizes[-1])[2] <= room:
        return entries, [], []
    start, end = 0, sizes[0] - 1
    for lower, upper in reversed(list(zip(sizes, sizes[1:], strict=False))):
        if fitted(lower)[2] <= room:
            start, end = lower, upper - 1
            break
    best = start + _longest(end - start, lambda extra: fitted(start + extra)[2] <= room)
    kept, shortened, used = fitted(best)
    if used <= room:
        return kept, shortened, []
    held, left_out = _leave_out(kept, room - sum(_size(name) + 1 for name in shortened))
    return held, [name for name in shortened if name not in left_out], left_out


def _leave_out(entries: list[DoctorSetting], room: int) -> tuple[list[DoctorSetting], list[str]]:
    """The settings `room` holds, and the names of those it cannot.

    A name left out takes room too, so the fit is redone with the names
    reserved until no further setting is cut. Each pass cuts at least one more,
    so it ends.
    """
    left_out: set[str] = set()
    while True:
        used = sum(_size(name) + 1 for name in left_out)
        kept: list[DoctorSetting] = []
        cut = False
        for entry in entries:
            if entry.name in left_out:
                continue
            size = _size(entry.model_dump(mode="json")) + 1
            if used + size > room:
                left_out.add(entry.name)
                used += _size(entry.name) + 1
                cut = True
                continue
            kept.append(entry)
            used += size
        if not cut:
            return kept, [entry.name for entry in entries if entry.name in left_out]


def doctor_report(
    status: Mapping[str, Any],
    *,
    settings: Settings,
    access: AgentAccessConfig,
    engine_version: str,
    workspace: Path,
    tier: ToolTier,
) -> DoctorReport:
    """The report from the status the dashboard reads and the running settings."""
    redactor = Redactor(workspace)
    checks = [
        check.model_copy(update={"summary": redactor.text(check.summary)})
        for check in _checks(status, access)
    ]
    entries = _settings(settings, redactor)
    report = DoctorReport(
        engine_version=engine_version, contract_version=CONTRACT_VERSION,
        install=status.get("install", "source"), checks=checks, settings=[], redacted=0,
    )
    room = PAGE_BUDGET_BYTES[tier] - _size(report.model_dump(mode="json"))
    if tier != "full":
        used = 0
        for entry in entries:
            size = _size(entry.model_dump(mode="json")) + 1
            if used + size > room:
                report.continue_with = [NextAction(operation=DOCTOR.id, arguments={"tier": "full"})]
                break
            report.settings.append(entry)
            used += size
    else:
        report.settings, report.settings_shortened, report.settings_left_out = _fit_full(entries, room)
    report.redacted = redactor.count
    return report


# --- context export ---------------------------------------------------------- #

ComponentName = Literal["posting", "pay", "company", "pursuit"]
#: The packet's own format; a change to what it holds is a new format.
PACKET_FORMAT: Literal[1] = 1


class ContextExportInput(Shape):
    opportunity_id: int = Field(ge=1, description="The opportunity's id, as search returns it.")
    tier: ToolTier = Field(default="small", description="The caller's tool tier, which bounds one part of the packet.")
    packet_from: int | None = Field(
        default=None, ge=0,
        description="Read the packet from this character on, as continue_with gives it; the parts joined are the packet.",
    )
    packet_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$", json_schema_extra=_IDENTIFIER,
        description=(
            "The manifest's packet_sha256 of the parts read so far, as continue_with gives it. "
            "A packet that changed since is refused, so parts of two packets are never joined."
        ),
    )

    @model_validator(mode="after")
    def _later_part_names_its_packet(self) -> ContextExportInput:
        if self.packet_from and self.packet_sha256 is None:
            raise ValueError("packet_from past the start needs the packet_sha256 continue_with gives")
        return self


class PacketComponent(Shape):
    name: ComponentName = Field(json_schema_extra=_CODE)
    #: SHA-256 of the component's canonical JSON, as it stands in the packet.
    sha256: str = Field(json_schema_extra=_IDENTIFIER)
    #: When each source of the component was read; these move without the content moving.
    source_timestamps: dict[str, datetime | date | None]
    #: The posting's own fingerprint of its title and text.
    fingerprint: str | None = Field(json_schema_extra=_IDENTIFIER)


class ExportManifest(Shape):
    format: Literal[1]
    opportunity_id: int
    #: SHA-256 of the packet's UTF-8 bytes.
    packet_sha256: str = Field(json_schema_extra=_IDENTIFIER)
    packet_bytes: int = Field(ge=0)
    packet_chars: int = Field(ge=0)
    components: list[PacketComponent]
    #: Categories left out because the person does not share them with assistants.
    left_out: list[DataClass] = Field(json_schema_extra=_CODE)


class ContextExport(Shape):
    manifest: ExportManifest
    #: The character of the packet this part starts at.
    packet_offset: int = Field(ge=0)
    #: The packet's text from `packet_offset`: canonical JSON, whole when
    #: `continue_with` is empty and the offset is 0.
    packet: str = Field(json_schema_extra=_CONTENT)
    continue_with: list[NextAction] = Field(default_factory=list)


CONTEXT_EXPORT = OperationDescriptor(
    id="context.export",
    summary="Export one opportunity's posting text, pay evidence, company facts and pursuit as a hashed packet.",
    input=ContextExportInput,
    result=ContextExport,
    access="read",
    idempotency="read",
    engine_effects=EngineEffects(),
    tool_tiers=_EVERY_TIER,
    data_classes=("public_posting", "market_statistic", "private_pursuit"),
    # The CLI's `--output` writes the whole packet to a file.
    client_effects=("file_write",),
    examples=({"opportunity_id": 4821},),
)

OPERATIONS: tuple[OperationDescriptor, ...] = (DOCTOR, CONTEXT_EXPORT)

#: The posting fields that are the posting's content; the rest of the view is
#: pay, the pursuit, or a value that moves with the clock.
_POSTING_FIELDS = (
    "id", "company", "title", "url", "locations", "workplace_type", "level_band", "family", "track", "status",
    "first_seen", "listed_since", "listed_basis",
)
_PAY_FIELDS = ("estimate_component", "estimated_total_comp", "estimated_base", "employer_stated_pay")
_COMPANY_FIELDS = ("is_public", "ticker", "headcount", "hq_city", "website", "equity_vehicle", "vesting_schedule")


def canonical(value: Any) -> str:
    """The one spelling of `value` the packet and its hashes use."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def sha256(text_: str) -> str:
    return hashlib.sha256(text_.encode("utf-8")).hexdigest()


async def begin_snapshot(session: AsyncSession) -> None:
    """Make the session's next transaction one snapshot: every component is
    read as of the same moment. The session holds no transaction when called."""
    if session.in_transaction():
        raise RuntimeError("a snapshot read starts its own transaction")
    await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))


async def context_packet(
    session: AsyncSession, opportunity_id: int, *, withheld: Collection[DataClass] = ()
) -> tuple[str, ExportManifest]:
    """The packet's canonical text and its manifest, without the `withheld`
    categories (`opportunities.get` leaves them out of the facts it reads)."""
    view = (await opportunity(
        session, OpportunityGetInput(opportunity_id=opportunity_id, view="evidence"), withheld=withheld,
    )).root
    facts = view.model_dump(mode="json")
    sources = facts["evidence"].get("estimate_sources")
    job = await session.get(Job, opportunity_id)
    assert job is not None  # `opportunity` found it in this same snapshot
    dates = facts["evidence"]["dates"]
    posting = {
        **{name: facts[name] for name in _POSTING_FIELDS},
        "department": job.department,
        "team": job.team,
        "description": job.description_text,
        "description_sections": job.description_sections or [],
        "employer_published_at": dates["employer_published_at"],
        "employer_first_published_at": dates["employer_first_published_at"],
        "closed_at": dates["closed_at"],
    }
    pay = {name: facts[name] for name in _PAY_FIELDS if name in facts}
    if sources is not None:
        pay["estimate_sources"] = [{"source": source["source"], "answers": source["answers"]} for source in sources]
    company = await _company(session, job.company)
    company_read_at = company.pop("profile_updated_at") if company is not None else None
    # When a source last confirmed a fact moves without the fact moving.
    company_observed = company.pop("observed_at") if company is not None else {}
    components: dict[ComponentName, Any] = {"posting": posting, "pay": pay, "company": company}
    stamps: dict[ComponentName, dict[str, Any]] = {
        "posting": {"last_seen": dates["last_seen"], "description_fetched_at": dates["description_fetched_at"]},
        "pay": {"stated_pay_read_at": job.structured_at} if sources is None else {
            "stated_pay_read_at": job.structured_at,
            "estimate_as_of": job.comp_as_of,
            **{f"estimated_at:{source['source']}": source["estimated_at"] for source in sources},
        },
        "company": {
            "profile_updated_at": company_read_at,
            **{f"observed_at:{name}": at for name, at in company_observed.items()},
        },
    }
    left_out: list[DataClass] = [category for category in CONTEXT_EXPORT.data_classes if category in withheld]
    if "pursuit" in facts:
        pursuit = await session.scalar(select(Pursuit).where(Pursuit.job_id == opportunity_id))
        saved = await session.scalar(select(Favorite.created_at).where(Favorite.job_id == opportunity_id))
        components["pursuit"] = {"saved": saved is not None, "pursuit": facts["pursuit"]}
        stamps["pursuit"] = {
            "saved_at": saved, "pursuit_updated_at": pursuit.updated_at if pursuit is not None else None,
        }
    packet = canonical({"format": PACKET_FORMAT, "opportunity_id": opportunity_id, "components": components})
    manifest = ExportManifest(
        format=PACKET_FORMAT,
        opportunity_id=opportunity_id,
        packet_sha256=sha256(packet),
        packet_bytes=len(packet.encode("utf-8")),
        packet_chars=len(packet),
        components=[
            PacketComponent(
                name=name,
                sha256=sha256(canonical(value)),
                source_timestamps=stamps.get(name, {}),
                fingerprint=job.content_hash if name == "posting" else None,
            )
            for name, value in components.items()
        ],
        left_out=left_out,
    )
    return packet, manifest


async def _company(session: AsyncSession, slug: str) -> dict[str, Any] | None:
    """The company's identity facts as its profile answers them: each value
    with the source that stated it and when; the plugin selected for company
    facts answers the fields it owns."""
    profile = await session.get(CompanyProfile, slug)
    if profile is None:
        return None
    providers = await reader_providers(session)
    plugin = providers.source_for(COMPANY_FACTS)
    plugin_values = (await profile_store.plugin_fields(session, providers, [slug])).get(slug, {}) if plugin else {}
    fields: dict[str, Any] = {}
    observed: dict[str, datetime | None] = {}
    for name in _COMPANY_FIELDS:
        if plugin and name in profile_store.PLUGIN_FIELDS:
            resolved = plugin_values.get(name) or {}
            fields[name] = {"value": resolved.get("value"), "source": resolved.get("source"), "answered_by": plugin}
            observed[name] = _stamp(resolved.get("observed_at"))
        else:
            meta = (profile.field_meta or {}).get(name) or {}
            fields[name] = {"value": getattr(profile, name), "source": meta.get("source"), "answered_by": None}
            observed[name] = _stamp(meta.get("observed_at"))
    return {
        "slug": profile.slug,
        "display_name": profile.display_name,
        "fields": fields,
        "comp_notes": profile.comp_notes,
        "profile_updated_at": profile.profile_updated_at,
        "observed_at": observed,
    }


def _stamp(value: Any) -> datetime | None:
    """A field's observation time; one this cannot read is left unstated."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def packet_part(
    packet: str, manifest: ExportManifest, *, opportunity_id: int, tier: ToolTier, start: int
) -> ContextExport:
    """The part of `packet` from `start` that fits the tier's budget, with the
    call that reads the next one. A part holds at least one character."""
    start = min(start, len(packet))
    shell = ContextExport(manifest=manifest, packet_offset=start, packet="", continue_with=[
        _next_part(manifest, opportunity_id=opportunity_id, tier=tier, start=len(packet))
    ])
    room = DETAIL_BUDGET_BYTES[tier] - _size(shell.model_dump(mode="json"))
    end, used = start, 0
    while end < len(packet):
        # A character's size inside a JSON string, escapes included.
        size = len(json.dumps(packet[end], ensure_ascii=False).encode("utf-8")) - 2
        if end > start and used + size > room:
            break
        used += size
        end += 1
    rest = [] if end >= len(packet) else [_next_part(manifest, opportunity_id=opportunity_id, tier=tier, start=end)]
    return ContextExport(manifest=manifest, packet_offset=start, packet=packet[start:end], continue_with=rest)


def _next_part(manifest: ExportManifest, *, opportunity_id: int, tier: ToolTier, start: int) -> NextAction:
    return NextAction(operation=CONTEXT_EXPORT.id, arguments={
        "opportunity_id": opportunity_id, "tier": tier, "packet_from": start,
        "packet_sha256": manifest.packet_sha256,
    })


def same_packet(manifest: ExportManifest, params: ContextExportInput) -> None:
    """Refuse a continuation whose earlier parts came from another packet:
    the posting, its pay, its company or the pursuit changed in between."""
    if params.packet_sha256 is not None and params.packet_sha256 != manifest.packet_sha256:
        raise OperationError(
            "revision_conflict",
            "The packet changed after its earlier parts were read. Read it again from the start.",
            details={"expected_packet_sha256": params.packet_sha256, "current_packet_sha256": manifest.packet_sha256},
            next_actions=[NextAction(operation=CONTEXT_EXPORT.id, arguments={
                "opportunity_id": params.opportunity_id, "tier": params.tier,
            })],
        )


def _size(value: object) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8"))
