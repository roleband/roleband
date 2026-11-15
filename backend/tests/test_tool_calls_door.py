"""A tool-calling transport exists only for a tier the routing ladder admitted.

The cloud case runs on saved state: a cloud profile with a key, and the egress
switch as Settings stores it. With the switch off the ladder blocks the cloud
tier and no transport can be made from it, so no request is ever built; with
it on, the same profile is reached.
"""

from __future__ import annotations

import json

import httpx
import pytest

from tracker.cloud_llm.models import CloudLLMProfile, CloudLLMProfileInput
from tracker.intelligence.policy import RouteReason
from tracker.intelligence.provider import AvailabilityState, NullProvider, ProviderOrigin
from tracker.intelligence.providers.cloud import CloudLLMProvider
from tracker.intelligence.router import Tier
from tracker.intelligence.tool_calls import (
    TierNotAdmitted,
    ToolDefinition,
    UserMessage,
    transport_for_tier,
)
from tracker.intelligence_runtime import cloud_profiles
from tracker.intelligence_runtime.routing import build_tiers
from tracker.settings_store import set_ai_egress_enabled

pytestmark = pytest.mark.usefixtures("no_escape")

TOOL = ToolDefinition("vocabulary_list", "List values.", {"type": "object", "properties": {}})
ANSWER = {
    "content": [{"type": "text", "text": "Done."}],
    "stop_reason": "end_turn",
    "model": "claude-sonnet-5-5",
    "usage": {"input_tokens": 10, "output_tokens": 2},
}


class Endpoint:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(200, json=ANSWER)

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handler))


def _cloud(**overrides) -> CloudLLMProfile:
    values = dict(id="cloudprofile1", name="Claude", provider="anthropic", base_url="https://api.anthropic.com/v1",
                  model="claude-sonnet-5-5", enabled=True, api_key="sk-ant-test")
    values.update(overrides)
    return CloudLLMProfile(**values)


async def _cloud_tiers(session) -> list[Tier]:
    return [tier for tier in await build_tiers(session, task_type=None)
            if tier.provider.origin is ProviderOrigin.CLOUD]


@pytest.mark.asyncio
async def test_a_cloud_call_is_impossible_while_the_egress_switch_is_off(db_session):
    await cloud_profiles.create_profile(db_session, CloudLLMProfileInput(
        name="Claude", provider="anthropic", base_url="https://api.anthropic.com/v1",
        model="claude-sonnet-5-5", enabled=True, api_key="sk-ant-test",
    ))
    await db_session.commit()
    endpoint = Endpoint()

    [blocked] = await _cloud_tiers(db_session)
    assert blocked.blocked_reason is not None, "the switch is off by default"
    async with endpoint.client() as client:
        with pytest.raises(TierNotAdmitted):
            transport_for_tier(blocked, http_client=client)
    assert endpoint.requests == []

    # Control: the same saved profile, the switch on, is reached.
    await set_ai_egress_enabled(db_session, True)
    await db_session.commit()
    [admitted] = await _cloud_tiers(db_session)
    async with endpoint.client() as client:
        turn = await transport_for_tier(admitted, http_client=client).complete([UserMessage("hi")], tools=[TOOL])
    assert turn.text == "Done."
    assert [str(request.url) for request in endpoint.requests] == ["https://api.anthropic.com/v1/messages"]
    assert json.loads(endpoint.requests[0].content)["model"] == "claude-sonnet-5-5"

    # And off again is off again.
    await set_ai_egress_enabled(db_session, False)
    await db_session.commit()
    [blocked_again] = await _cloud_tiers(db_session)
    with pytest.raises(TierNotAdmitted):
        transport_for_tier(blocked_again)
    assert len(endpoint.requests) == 1


def test_a_blocked_tier_is_refused_whatever_it_carries():
    with pytest.raises(TierNotAdmitted, match="egress"):
        transport_for_tier(Tier(provider=CloudLLMProvider(_cloud()), blocked_reason=RouteReason.EGRESS_BLOCKED))


@pytest.mark.parametrize(
    ("profile", "reason"),
    [(_cloud(enabled=False), "turned off"), (_cloud(api_key=None), "no API key")],
)
def test_a_cloud_profile_that_cannot_run_is_refused(profile, reason):
    with pytest.raises(TierNotAdmitted, match=reason):
        transport_for_tier(Tier(provider=CloudLLMProvider(profile)))


def test_a_tier_with_no_model_behind_it_has_no_transport():
    with pytest.raises(TierNotAdmitted, match="no tool-calling transport"):
        transport_for_tier(Tier(provider=NullProvider(AvailabilityState.NOT_CONFIGURED, "nothing")))
