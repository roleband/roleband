"""The Anthropic Messages format.

The `anthropic_*` fixtures in `tests/fixtures/model_tool_calls/` follow the
documented Messages response shape; the edge cases change one field each.
Every request goes to an `httpx.MockTransport`, and no test sends anything to
a cloud endpoint.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any

import httpx
import pytest

from tracker.cloud_llm.models import CloudLLMProfile
from tracker.intelligence.provider import ProviderOrigin
from tracker.intelligence.providers.cloud import CloudLLMProvider
from tracker.intelligence.router import Tier
from tracker.intelligence.tool_calls import (
    AssistantMessage,
    CallProblemKind,
    StopReason,
    ToolCall,
    ToolDefinition,
    ToolResult,
    ToolResults,
    ToolTransportError,
    UserMessage,
    transport_for_tier,
)
from tracker.intelligence.tool_calls.anthropic_format import read_turn, request_body
from tracker.intelligence.tool_calls.conversation import ToolRequest, parse_arguments

pytestmark = pytest.mark.usefixtures("no_escape")

FIXTURES = Path(__file__).parent / "fixtures" / "model_tool_calls"
CLOUD_KEY = "sk-ant-test-never-printed"
VOCABULARY = ToolDefinition(
    name="vocabulary_list",
    description="List the values a search filter accepts.",
    parameters={"type": "object", "properties": {"kind": {"type": "string"}}, "required": ["kind"]},
)
QUESTION = UserMessage("Which workplace types and level bands can I filter by?")


def _fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{name}.json").read_text())


def _request(tool_choice="auto") -> ToolRequest:
    return ToolRequest(conversation=(QUESTION,), tools=(VOCABULARY,), tool_choice=tool_choice)


def _tier() -> Tier:
    profile = CloudLLMProfile(
        id="anthropic01", name="Claude", provider="anthropic", base_url="https://api.anthropic.com/v1",
        model="claude-sonnet-5-5", enabled=True, api_key=CLOUD_KEY,
    )
    return Tier(provider=CloudLLMProvider(profile))


class Endpoint:
    def __init__(self, *answers: Any) -> None:
        self.answers = list(answers)
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        answer = self.answers.pop(0)
        return answer if isinstance(answer, httpx.Response) else httpx.Response(200, json=answer)

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handler))

    def body(self, index: int) -> dict[str, Any]:
        return json.loads(self.requests[index].content)


# --- reading responses -------------------------------------------------------


def test_parallel_tool_use_blocks_read_as_calls_beside_the_text():
    turn = read_turn(_fixture("anthropic_parallel_calls"), request=_request(), model="m", wall_time_ms=9)
    assert turn.stop_reason is StopReason.TOOL_USE and turn.raw_stop == "tool_use"
    assert turn.text == "I'll look up both filters."
    assert [(call.id, dict(call.arguments)) for call in turn.tool_calls] == [
        ("toolu_01A9cLq2vWnX8sYb3TfR6kPd", {"kind": "workplace_type"}),
        ("toolu_01B7dMr3wXoY9tZc4UgS7lQe", {"kind": "level_band"}),
    ]
    assert json.loads(turn.tool_calls[0].raw_arguments) == {"kind": "workplace_type"}
    # The whole prompt is counted, the cached part said apart.
    assert (turn.usage.input_tokens, turn.usage.cached_input_tokens, turn.usage.output_tokens) == (1436, 1024, 96)
    assert turn.model == "claude-sonnet-5-5"


@pytest.mark.parametrize(
    ("fixture", "stop", "text"),
    [
        ("anthropic_final_answer", StopReason.END, "You can filter by onsite, remote and hybrid."),
        ("anthropic_refusal", StopReason.REFUSAL, ""),
        ("anthropic_max_tokens", StopReason.MAX_TOKENS, "The workplace types are onsite, remo"),
    ],
)
def test_stop_reasons_are_normalized(fixture, stop, text):
    turn = read_turn(_fixture(fixture), request=_request(), model="m")
    assert turn.stop_reason is stop and turn.text == text and turn.tool_calls == ()


@pytest.mark.parametrize(
    ("raw_stop", "stop"),
    [("stop_sequence", StopReason.END), ("model_context_window_exceeded", StopReason.MAX_TOKENS),
     ("something_new", StopReason.END)],
)
def test_other_stop_words_map_onto_the_four(raw_stop, stop):
    body = _fixture("anthropic_final_answer")
    body["stop_reason"] = raw_stop
    turn = read_turn(body, request=_request(), model="m")
    assert turn.stop_reason is stop and turn.raw_stop == raw_stop


def test_input_that_is_not_an_object_and_an_unknown_tool_are_problems():
    body = _fixture("anthropic_parallel_calls")
    body["content"][1]["input"] = ["workplace_type"]
    body["content"][2]["name"] = "delete_everything"
    first, second = read_turn(body, request=_request(), model="m").tool_calls
    assert first.problem is not None and first.problem.kind is CallProblemKind.MALFORMED_ARGUMENTS
    assert second.problem is not None and second.problem.kind is CallProblemKind.UNKNOWN_TOOL


def test_text_where_a_call_was_required_is_flagged():
    turn = read_turn(_fixture("anthropic_final_answer"), request=_request(tool_choice="required"), model="m")
    assert turn.missing_tool_call and turn.text


def test_thinking_blocks_are_reasoning_not_answer():
    body = _fixture("anthropic_final_answer")
    body["content"].insert(0, {"type": "thinking", "thinking": "Three types.", "signature": "sig"})
    turn = read_turn(body, request=_request(), model="m")
    assert turn.reasoning == "Three types." and turn.text.startswith("You can filter")


@pytest.mark.parametrize("body", [{}, {"content": "text"}, [], None])
def test_a_body_that_is_no_message_is_a_validation_error(body):
    with pytest.raises(ToolTransportError) as caught:
        read_turn(body, request=_request(), model="m")
    assert caught.value.failure_class == "validation"


# --- the request body --------------------------------------------------------


def test_the_request_carries_the_conversation_in_the_format():
    good = ToolCall(id="toolu_1", name="vocabulary_list", arguments={"kind": "family"}, raw_arguments="{}")
    arguments, raw, problem = parse_arguments('{"kind":', name="vocabulary_list", offered=frozenset({"vocabulary_list"}))
    bad = ToolCall(id="toolu_2", name="vocabulary_list", arguments=arguments, raw_arguments=raw, problem=problem)
    request = ToolRequest(
        conversation=(
            QUESTION,
            AssistantMessage(text="Checking.", tool_calls=(good, bad)),
            ToolResults((ToolResult("toolu_1", '["data"]'), ToolResult.for_problem(bad))),
            UserMessage("And quickly, please."),
        ),
        tools=(VOCABULARY,),
        system="Answer from the tools.",
        tool_choice="required",
        parallel_tool_calls=False,
    )
    body = request_body(request, model="claude-sonnet-5-5")
    assert body["system"] == "Answer from the tools."
    assert body["max_tokens"] == 4096, "the format requires a ceiling"
    assert body["tools"] == [{"name": "vocabulary_list", "description": VOCABULARY.description,
                              "input_schema": dict(VOCABULARY.parameters)}]
    assert body["tool_choice"] == {"type": "any", "disable_parallel_tool_use": True}
    user, assistant, results = body["messages"]
    assert [message["role"] for message in body["messages"]] == ["user", "assistant", "user"]
    assert assistant["content"] == [
        {"type": "text", "text": "Checking."},
        {"type": "tool_use", "id": "toolu_1", "name": "vocabulary_list", "input": {"kind": "family"}},
        {"type": "tool_use", "id": "toolu_2", "name": "vocabulary_list", "input": {}},
    ]
    # The results and the person's next words share one user message, results first.
    assert [block["type"] for block in results["content"]] == ["tool_result", "tool_result", "text"]
    assert results["content"][0] == {"type": "tool_result", "tool_use_id": "toolu_1", "content": '["data"]'}
    assert results["content"][1]["is_error"] is True and '{"kind":' in results["content"][1]["content"]


@pytest.mark.parametrize(("choice", "sent"), [("auto", {"type": "auto"}), ("none", {"type": "none"})])
def test_tool_choice_is_translated(choice, sent):
    body = request_body(ToolRequest(conversation=(QUESTION,), tools=(VOCABULARY,), tool_choice=choice), model="m")
    assert body["tool_choice"] == sent


def test_a_conversation_from_a_local_model_crosses_over_with_ids_the_format_accepts():
    call = ToolCall(id="call.976660ba:0", name="vocabulary_list", arguments={"kind": "family"}, raw_arguments="{}")
    body = request_body(
        ToolRequest(conversation=(QUESTION, AssistantMessage(tool_calls=(call,)),
                                  ToolResults((ToolResult(call.id, "[]"),))), tools=(VOCABULARY,)),
        model="m",
    )
    used = body["messages"][1]["content"][0]["id"]
    answered = body["messages"][2]["content"][0]["tool_use_id"]
    assert used == answered and re.fullmatch(r"call_976660ba_0_[0-9a-f]{8}", used)


def test_ids_that_differ_only_in_refused_characters_stay_distinct():
    calls = tuple(ToolCall(id=call_id, name="vocabulary_list") for call_id in ("call.1", "call:1", "call_1"))
    body = request_body(
        ToolRequest(conversation=(QUESTION, AssistantMessage(tool_calls=calls),
                                  ToolResults(tuple(ToolResult(call.id, "[]") for call in calls))),
                    tools=(VOCABULARY,)),
        model="m",
    )
    used = [block["id"] for block in body["messages"][1]["content"]]
    answered = [block["tool_use_id"] for block in body["messages"][2]["content"]]
    assert used == answered and len(set(used)) == 3
    assert "call_1" in used, "an id the format already accepts is sent as it is"


def test_an_empty_assistant_message_is_left_out_rather_than_sent_empty():
    body = request_body(ToolRequest(conversation=(QUESTION, AssistantMessage(), UserMessage("hello?"))), model="m")
    assert body["messages"] == [{"role": "user", "content": [
        {"type": "text", "text": QUESTION.text}, {"type": "text", "text": "hello?"},
    ]}]


# --- the transport -----------------------------------------------------------


@pytest.mark.asyncio
async def test_a_cloud_round_trip_goes_to_the_profile_address_with_its_key():
    endpoint = Endpoint(_fixture("anthropic_parallel_calls"), _fixture("anthropic_final_answer"))
    async with endpoint.client() as client:
        transport = transport_for_tier(_tier(), http_client=client)
        assert transport.origin is ProviderOrigin.CLOUD and transport.wire == "anthropic"
        conversation: list = [QUESTION]
        first = await transport.complete(conversation, tools=[VOCABULARY], max_tokens=512)
        conversation += [first.message, ToolResults(tuple(ToolResult(call.id, "[]") for call in first.tool_calls))]
        second = await transport.complete(conversation, tools=[VOCABULARY])
    assert second.stop_reason is StopReason.END
    request = endpoint.requests[0]
    assert str(request.url) == "https://api.anthropic.com/v1/messages"
    assert request.headers["x-api-key"] == CLOUD_KEY and request.headers["anthropic-version"] == "2023-06-01"
    assert "authorization" not in request.headers
    assert endpoint.body(0)["max_tokens"] == 512
    answered = [block["tool_use_id"] for block in endpoint.body(1)["messages"][2]["content"]]
    assert answered == [call.id for call in first.tool_calls]
    assert CLOUD_KEY not in repr(transport)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "failure_class", "detail"),
    [
        (httpx.Response(400, json={"type": "error", "error": {"type": "invalid_request_error",
                                                             "message": "tools.0.name: invalid"}}),
         "http_error", "tools.0.name: invalid"),
        (httpx.Response(429, headers={"retry-after": "30"},
                        json={"type": "error", "error": {"type": "rate_limit_error", "message": "rate limited"}}),
         "rate_limited", "rate limited"),
        (httpx.Response(529, json={"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}}),
         "http_error", "Overloaded"),
    ],
)
async def test_failed_requests_are_typed(response, failure_class, detail):
    endpoint = Endpoint(response)
    async with endpoint.client() as client:
        with pytest.raises(ToolTransportError) as caught:
            await transport_for_tier(_tier(), http_client=client).complete([QUESTION], tools=[VOCABULARY])
    assert caught.value.failure_class == failure_class and detail in str(caught.value)
    assert CLOUD_KEY not in str(caught.value)


@pytest.mark.asyncio
async def test_a_slow_cloud_model_is_a_timeout_and_cancelling_stops_the_request():
    started, cancelled = asyncio.Event(), asyncio.Event()

    async def hanging(request: httpx.Request) -> httpx.Response:
        started.set()
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return httpx.Response(200, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(hanging)) as client:
        transport = transport_for_tier(_tier(), http_client=client)
        with pytest.raises(ToolTransportError) as caught:
            await transport.complete([QUESTION], timeout=0.05)
        assert caught.value.failure_class == "timeout"
        started.clear()
        cancelled.clear()
        task = asyncio.create_task(transport.complete([QUESTION]))
        await asyncio.wait_for(started.wait(), 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert cancelled.is_set()
