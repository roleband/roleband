"""One tool-calling request to a model, and the only way to get a transport.

`transport_for_tier` takes a rung of the routing ladder that
`intelligence_runtime.routing.build_tiers` assembled and refuses one it
blocked, so a cloud model is reached through the egress switch or not at all.
No caller passes an address or a key: both come from the saved profile the
tier carries.

A request runs under one deadline for the whole exchange, beside httpx's own
per-operation timeouts. Cancelling the task that awaits `complete` cancels the
HTTP request with it.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Literal

import httpx

from tracker.intelligence.provider import ProviderOrigin
from tracker.intelligence.providers.cloud import CloudLLMProvider
from tracker.intelligence.providers.local import LocalLLMProvider
from tracker.intelligence.router import Tier
from tracker.intelligence.tool_calls import anthropic_format, openai_format
from tracker.intelligence.tool_calls.conversation import (
    Message,
    ToolChoice,
    ToolDefinition,
    ToolRequest,
    ToolTransportError,
    Turn,
    check_conversation,
)
from tracker.platform.http import make_client

Wire = Literal["openai", "anthropic"]

#: Seconds a cloud request may take when the caller names no deadline.
CLOUD_TIMEOUT_SECONDS = 120.0


class TierNotAdmitted(RuntimeError):
    """The tier may not be called: the ladder blocked it, or it has no
    tool-calling transport."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class _Endpoint:
    url: str
    #: Carries the key; kept out of every repr.
    headers: Mapping[str, str] = field(repr=False)
    model: str
    wire: Wire
    origin: ProviderOrigin
    timeout: float
    max_tokens_field: str = "max_tokens"
    extra: Mapping[str, Any] = field(default_factory=dict)


class ToolTransport:
    """Tool-calling requests to the model of one admitted tier."""

    def __init__(self, endpoint: _Endpoint, *, http_client: httpx.AsyncClient | None = None) -> None:
        self._endpoint = endpoint
        self._client = http_client

    def __repr__(self) -> str:
        return f"ToolTransport(wire={self.wire!r}, model={self.model!r}, origin={self.origin.value!r})"

    @property
    def wire(self) -> Wire:
        return self._endpoint.wire

    @property
    def model(self) -> str:
        return self._endpoint.model

    @property
    def origin(self) -> ProviderOrigin:
        return self._endpoint.origin

    def request_body(self, request: ToolRequest) -> dict[str, Any]:
        endpoint = self._endpoint
        if endpoint.wire == "anthropic":
            return anthropic_format.request_body(request, model=endpoint.model)
        return openai_format.request_body(
            request, model=endpoint.model, max_tokens_field=endpoint.max_tokens_field, extra=endpoint.extra
        )

    async def complete(
        self,
        conversation: Sequence[Message],
        *,
        tools: Sequence[ToolDefinition] = (),
        system: str | None = None,
        tool_choice: ToolChoice = "auto",
        parallel_tool_calls: bool = True,
        max_tokens: int | None = None,
        timeout: float | None = None,
    ) -> Turn:
        """One model turn: final text, or the tool calls it asks for.

        Raises `ToolTransportError` when no turn came back, and `ValueError`
        for a conversation no format can send. What the model wrote never
        raises: see `ToolCall.problem` and `Turn.missing_tool_call`.
        """
        check_conversation(conversation, tools)
        request = ToolRequest(
            conversation=tuple(conversation),
            tools=tuple(tools),
            system=system,
            tool_choice=tool_choice,
            parallel_tool_calls=parallel_tool_calls,
            max_tokens=max_tokens,
        )
        endpoint = self._endpoint
        deadline = endpoint.timeout if timeout is None else timeout
        body = self.request_body(request)
        client = self._client or make_client(timeout=deadline)
        owned = self._client is None
        started = perf_counter()
        try:
            async with asyncio.timeout(deadline):
                response = await client.post(endpoint.url, headers=dict(endpoint.headers), json=body)
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise ToolTransportError(
                f"The model did not answer within {deadline:g}s.", failure_class="timeout", status_code=504
            ) from exc
        except httpx.HTTPError as exc:
            raise ToolTransportError(
                f"Could not reach the model: {type(exc).__name__}", failure_class="connection"
            ) from exc
        finally:
            if owned:
                await client.aclose()
        wall_time_ms = round((perf_counter() - started) * 1000)
        _raise_for_status(response)
        try:
            data = response.json()
        except ValueError as exc:
            raise ToolTransportError("The model's response was not JSON.", failure_class="validation") from exc
        reader = anthropic_format.read_turn if endpoint.wire == "anthropic" else openai_format.read_turn
        return reader(data, request=request, model=endpoint.model, wall_time_ms=wall_time_ms)


def _raise_for_status(response: httpx.Response) -> None:
    if response.is_success:
        return
    detail = f"HTTP {response.status_code}"
    try:
        body = response.json()
    except ValueError:
        body = None
    error = body.get("error") if isinstance(body, dict) else None
    message = error.get("message") if isinstance(error, dict) else error
    if not isinstance(message, str) and isinstance(body, dict):
        message = body.get("detail") if isinstance(body.get("detail"), str) else None
    if isinstance(message, str) and message.strip():
        detail = f"{detail}: {message.strip()[:300]}"
    retry_after: float | None = None
    try:
        retry_after = float(response.headers.get("retry-after", ""))
    except ValueError:
        pass
    raise ToolTransportError(
        f"The model refused the request ({detail}).",
        failure_class="rate_limited" if response.status_code == 429 else "http_error",
        status_code=response.status_code,
        retry_after=retry_after,
    )


def transport_for_tier(
    tier: Tier,
    *,
    thinking: bool | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> ToolTransport:
    """The transport for one rung of the ladder `build_tiers` assembled.

    A tier the ladder blocked (a cloud tier while the egress switch is off) is
    refused here, before any request exists. `thinking` overrides a local
    profile's thinking setting for this transport; cloud tiers ignore it.
    `http_client` lets a caller share one connection pool; it carries no
    address and no key.
    """
    if tier.blocked_reason is not None:
        raise TierNotAdmitted(tier.blocked_reason)
    provider = tier.provider
    if isinstance(provider, LocalLLMProvider):
        local = provider.profile
        headers = {"Content-Type": "application/json"}
        if local.api_key:
            headers["Authorization"] = f"Bearer {local.api_key}"
        endpoint = _Endpoint(
            url=f"{local.base_url}/chat/completions",
            headers=headers,
            model=local.model,
            wire="openai",
            origin=ProviderOrigin.THIS_MAC,
            timeout=local.parameters.timeout_seconds,
            extra=local.parameters.chat_payload(thinking=thinking),
        )
    elif isinstance(provider, CloudLLMProvider):
        cloud = provider.profile
        if not cloud.enabled:
            raise TierNotAdmitted("this cloud profile is turned off")
        if not cloud.api_key:
            raise TierNotAdmitted("no API key is saved for this cloud profile")
        if cloud.provider == "anthropic":
            endpoint = _Endpoint(
                url=f"{cloud.base_url}/messages",
                headers={
                    "x-api-key": cloud.api_key,
                    "anthropic-version": anthropic_format.API_VERSION,
                    "content-type": "application/json",
                },
                model=cloud.model,
                wire="anthropic",
                origin=ProviderOrigin.CLOUD,
                timeout=CLOUD_TIMEOUT_SECONDS,
            )
        else:
            endpoint = _Endpoint(
                url=f"{cloud.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {cloud.api_key}", "Content-Type": "application/json"},
                model=cloud.model,
                wire="openai",
                origin=ProviderOrigin.CLOUD,
                timeout=CLOUD_TIMEOUT_SECONDS,
                # OpenAI's own API names the ceiling differently from servers
                # that copied its earlier format.
                max_tokens_field="max_completion_tokens" if cloud.provider == "openai" else "max_tokens",
            )
    else:
        raise TierNotAdmitted(f"the {getattr(provider, 'name', 'unknown')} tier has no tool-calling transport")
    return ToolTransport(endpoint, http_client=http_client)
