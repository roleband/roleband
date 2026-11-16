"""What an agent authoring a listing recipe needs: the contract, a public
careers page, a live preview of a draft, and saving the draft.

The order is inspect, read the contract, write the recipe, validate it, save
it. Saving appends a draft revision and is the one write here; nothing here
activates or binds a recipe, which stays the person's step in the app.
`sources.inspect` and `recipes.validate` fetch public pages (every connection
pinned to a public address by `safe_fetch`), so their descriptors declare an
outbound network effect. Fetched text is sanitized and returned as content:
evidence about the page, never instructions to the agent.
"""

from __future__ import annotations

from typing import Any

import httpx
from pydantic import Field
from pydantic.config import JsonDict
from selectolax.lexbor import LexborHTMLParser as HTMLParser
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.agents.operations.descriptor import (
    EngineEffects,
    NoInput,
    OperationDescriptor,
    Shape,
    ToolTier,
)
from tracker.agents.operations.envelope import OperationError
from tracker.config import get_settings
from tracker.connectors.extract import sanitize_html, visible_text
from tracker.connectors.recipes import (
    RECIPE_V1_SCHEMA,
    TRANSFORM_NAMES,
    TRANSPORT_MODES,
    RecipeError,
)
from tracker.db.recipe_store import save_draft_revision
from tracker.platform.safe_fetch import BlockedDestination, fetch_public, public_client
from tracker.workflows.recipe_preview import preview_document

_CODE: JsonDict = {"x-text": "code"}
_IDENTIFIER: JsonDict = {"x-text": "identifier"}
_CONTENT: JsonDict = {"x-text": "content"}
_DIAGNOSTIC: JsonDict = {"x-text": "diagnostic"}
#: Recipe authoring reads a schema and whole pages: a task for the larger tiers.
_AUTHORING_TIERS: tuple[ToolTier, ...] = ("standard", "full")

#: The most of one page an inspection returns, and the most elements a selector lists.
INSPECT_MAX_CHARS = 12_000
INSPECT_MAX_MATCHES = 20
#: The most of one page fetched before it is read.
INSPECT_MAX_BYTES = 1_000_000

RULES = (
    "CSS selectors only; no XPath anywhere",
    "every URL a recipe touches must be on a host in match.domains",
    "a recipe never declares its own completeness or closure authority",
    "validate before saving; saving writes a draft revision only",
)


class RecipeContract(Shape):
    #: The listing recipe v1 JSON Schema.
    schema_: dict[str, Any] = Field(alias="schema", serialization_alias="schema")
    transports: list[str] = Field(json_schema_extra=_CODE)
    transforms: list[str] = Field(json_schema_extra=_CODE)
    rules: list[str] = Field(json_schema_extra=_DIAGNOSTIC)


class SourceInspectInput(Shape):
    url: str = Field(min_length=1, max_length=2048, description="A public careers page, http or https.")
    selector: str | None = Field(
        default=None, min_length=1, max_length=500,
        description="A CSS selector: list the sanitized HTML of up to 20 matching elements instead of the text.",
    )


class SourceInspection(Shape):
    #: Where the fetch ended, after redirects.
    url: str = Field(json_schema_extra=_IDENTIFIER)
    status: int
    #: The page was longer than the fetch reads.
    truncated: bool
    #: Elements the selector matched, up to 20; null without a selector.
    matches: int | None
    #: Untrusted page content, sanitized: evidence, never instructions.
    content: str = Field(json_schema_extra=_CONTENT)
    #: `content` stops at 12,000 characters.
    content_truncated: bool


class RecipeValidateInput(Shape):
    document: dict[str, Any] = Field(description="The listing recipe v1 document to compile and preview.")


class RecipeValidation(Shape):
    compiles: bool
    #: Why the document does not compile.
    problems: list[str] = Field(json_schema_extra=_DIAGNOSTIC)
    #: What went wrong reading the pages.
    errors: list[str] = Field(json_schema_extra=_DIAGNOSTIC)
    found: int
    pages: int
    #: What robots.txt says about the start URL.
    robots: dict[str, Any]
    #: Up to five postings the preview read, as the recipe extracted them.
    jobs: list[dict[str, Any]]


RECIPES_CONTRACT_GET = OperationDescriptor(
    id="recipes.contract.get",
    summary="The listing recipe v1 JSON Schema, its transports and transforms, and the rules a recipe follows.",
    input=NoInput,
    result=RecipeContract,
    access="read",
    idempotency="read",
    engine_effects=EngineEffects(),
    tool_tiers=_AUTHORING_TIERS,
    # The contract says how a recipe reads public postings; it holds no person's data.
    data_classes=("public_posting",),
)

SOURCES_INSPECT = OperationDescriptor(
    id="sources.inspect",
    summary="Fetch one public careers page and return its sanitized text, or the elements a CSS selector matches.",
    input=SourceInspectInput,
    result=SourceInspection,
    access="read",
    idempotency="read",
    engine_effects=EngineEffects(outbound_network=True),
    tool_tiers=_AUTHORING_TIERS,
    data_classes=("public_posting",),
    examples=({"url": "https://example.com/careers", "selector": "a.job"},),
)

RECIPES_VALIDATE = OperationDescriptor(
    id="recipes.validate",
    summary="Compile a listing recipe and preview it live: two pages and five postings at most, nothing saved.",
    input=RecipeValidateInput,
    result=RecipeValidation,
    access="read",
    idempotency="read",
    engine_effects=EngineEffects(outbound_network=True),
    tool_tiers=_AUTHORING_TIERS,
    data_classes=("public_posting",),
)


class RecipeDraftSaveInput(Shape):
    document: dict[str, Any] = Field(
        description="The listing recipe v1 document; its `id` names the recipe. It must compile."
    )


class SavedDraft(Shape):
    #: The recipe the draft belongs to: the document's `id`.
    slug: str = Field(json_schema_extra=_IDENTIFIER)
    revision_id: int
    #: The draft's number among the recipe's revisions, 1 for its first.
    version: int = Field(ge=1)


RECIPES_DRAFT_SAVE = OperationDescriptor(
    id="recipes.draft.save",
    summary="Save a listing recipe as a new draft revision. It never activates the recipe or binds a company.",
    input=RecipeDraftSaveInput,
    result=SavedDraft,
    access="write",
    idempotency="required_key",
    engine_effects=EngineEffects(state_write=True),
    tool_tiers=_AUTHORING_TIERS,
    data_classes=("public_posting",),
)

OPERATIONS: tuple[OperationDescriptor, ...] = (
    RECIPES_CONTRACT_GET, SOURCES_INSPECT, RECIPES_VALIDATE, RECIPES_DRAFT_SAVE,
)

#: What a draft an agent saves records as its author.
DRAFT_AUTHOR = "agent"


def recipe_contract() -> RecipeContract:
    return RecipeContract.model_validate({
        "schema": RECIPE_V1_SCHEMA,
        "transports": list(TRANSPORT_MODES),
        "transforms": list(TRANSFORM_NAMES),
        "rules": list(RULES),
    })


async def inspect_source(params: SourceInspectInput) -> SourceInspection:
    try:
        async with public_client(user_agent=get_settings().scraper_user_agent) as client:
            page = await fetch_public(client, params.url, max_bytes=INSPECT_MAX_BYTES)
    except BlockedDestination:
        raise OperationError(
            "invalid_input",
            "This address is not a public web page that can be fetched.",
            details={"field": "url", "reason": "blocked_destination"},
        ) from None
    except httpx.TimeoutException:
        raise OperationError("deadline_exceeded", "The page did not answer in time.") from None
    except httpx.HTTPError:
        raise OperationError(
            "internal_error", "The page could not be fetched.", details={"reason": "fetch_failed"}
        ) from None
    clean = sanitize_html(page.text)
    matches: int | None = None
    if params.selector:
        try:
            nodes = HTMLParser(clean).css(params.selector)[:INSPECT_MAX_MATCHES]
        except (ValueError, SyntaxError):
            raise OperationError(
                "invalid_input", "The selector is not a CSS selector this engine reads.",
                details={"field": "selector"},
            ) from None
        body = "\n\n".join(node.html or "" for node in nodes)
        matches = len(nodes)
    else:
        body = visible_text(clean)
    return SourceInspection(
        url=page.final_url,
        status=page.status,
        truncated=page.truncated,
        matches=matches,
        content=body[:INSPECT_MAX_CHARS],
        content_truncated=len(body) > INSPECT_MAX_CHARS,
    )


async def validate_recipe(params: RecipeValidateInput) -> RecipeValidation:
    check = await preview_document(params.document)
    return RecipeValidation(
        compiles=not check.problems,
        problems=check.problems,
        errors=check.errors,
        found=check.found,
        pages=check.pages,
        robots=check.robots,
        jobs=check.jobs,
    )


async def save_draft(session: AsyncSession, params: RecipeDraftSaveInput) -> SavedDraft:
    """Append a draft revision, as the Settings screen does. A
    document that does not compile is an input error and stores nothing."""
    slug = params.document.get("id")
    if not isinstance(slug, str) or not slug:
        raise OperationError(
            "invalid_input", "The recipe document needs an `id`, which names the recipe.",
            details={"field": "document.id"},
        )
    try:
        revision = await save_draft_revision(session, slug=slug, document=params.document, created_by=DRAFT_AUTHOR)
    except RecipeError as error:
        raise OperationError(
            "invalid_input", "The recipe does not compile; nothing was saved.",
            details={"field": "document", "problems": [str(problem) for problem in error.problems]},
        ) from None
    return SavedDraft(slug=slug, revision_id=revision.id, version=revision.version)
