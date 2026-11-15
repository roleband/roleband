"""The OpenAI-compatible chat completions format, against recorded responses.

The `omlx_*` fixtures in `tests/fixtures/model_tool_calls/` are response bodies
recorded from a local oMLX server running a Qwen 3.5 9B model, offered the real
`vocabulary_list` tool (`scripts/smoke_model_tools.py --record`). The edge
cases are those bodies with one field changed, as a small model or another
server produces them. Every request goes to an `httpx.MockTransport`.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from tracker.cloud_llm.models import CloudLLMProfile
from tracker.intelligence.providers.cloud import CloudLLMProvider
from tracker.intelligence.providers.local import LocalLLMProvider
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
from tracker.intelligence.tool_calls import transport as transport_module
from tracker.intelligence.tool_calls.conversation import ToolRequest, parse_arguments
from tracker.intelligence.tool_calls.openai_format import read_turn, request_body
from tracker.local_llm.models import LocalLLMParameters, LocalLLMProfile

pytestmark = pytest.mark.usefixtures("no_escape")

FIXTURES = Path(__file__).parent / "fixtures" / "model_tool_calls"
LOCAL_KEY = "local-key-never-printed"
VOCABULARY = ToolDefinition(
    name="vocabulary_list",
    description="List the values a search filter accepts.",
    parameters={"type": "object", "properties": {"kind": {"type": "string"}}, "required": ["kind"]},
)
SEARCH = ToolDefinition(
    name="opportunities_search",
    description="Search open roles.",
    parameters={"type": "object", "properties": {"query": {"type": "string"}}},
)
QUESTION = UserMessage("Which workplace types can I filter job searches by?")


def _fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{name}.json").read_text())


def _message(body: dict[str, Any]) -> dict[str, Any]:
    return body["choices"][0]["message"]


def _request(tools=(VOCABULARY,), tool_choice="auto") -> ToolRequest:
    return ToolRequest(conversation=(QUESTION,), tools=tools, tool_choice=tool_choice)


def _local_tier(**parameters: Any) -> Tier:
    profile = LocalLLMProfile(
        id="localprofile1", name="Local", model="Qwen3.5-9B-MLX-4bit", api_key=LOCAL_KEY,
        parameters=LocalLLMParameters(**parameters),
    )
    return Tier(provider=LocalLLMProvider(profile))


class Endpoint:
    """A model server that answers each request with the next queued body."""

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


# --- reading recorded responses ---------------------------------------------


def test_a_recorded_tool_call_reads_as_one_call():
    turn = read_turn(_fixture("omlx_one_call"), request=_request(), model="m", wall_time_ms=15)
    assert turn.stop_reason is StopReason.TOOL_USE and turn.raw_stop == "tool_calls"
    [call] = turn.tool_calls
    assert (call.id, call.name, dict(call.arguments), call.problem) == (
        "call_976660ba", "vocabulary_list", {"kind": "workplace_type"}, None
    )
    assert call.raw_arguments == '{"kind": "workplace_type"}'
    assert turn.text == ""
    assert (turn.usage.input_tokens, turn.usage.output_tokens, turn.usage.cached_input_tokens) == (525, 28, 0)
    assert turn.usage.wall_time_ms == 15 and turn.model == "Qwen3.5-9B-MLX-4bit"


def test_a_recorded_final_answer_reads_as_text():
    turn = read_turn(_fixture("omlx_final_answer"), request=_request(), model="m")
    assert turn.stop_reason is StopReason.END and turn.tool_calls == ()
    assert "onsite" in turn.text and "hybrid" in turn.text
    assert (turn.usage.input_tokens, turn.usage.output_tokens) == (622, 52)


def test_recorded_parallel_calls_keep_their_order_and_ids():
    turn = read_turn(_fixture("omlx_parallel_calls"), request=_request((VOCABULARY, SEARCH)), model="m")
    assert turn.stop_reason is StopReason.TOOL_USE
    assert [dict(call.arguments) for call in turn.tool_calls] == [{"kind": "workplace_type"}, {"kind": "level_band"}]
    assert len({call.id for call in turn.tool_calls}) == 2


def test_recorded_thinking_is_kept_apart_from_the_answer():
    turn = read_turn(_fixture("omlx_thinking_calls"), request=_request(), model="m")
    assert turn.reasoning and "workplace types" in turn.reasoning
    assert turn.text == "" and len(turn.tool_calls) == 2
    assert turn.usage.cached_input_tokens == 1674


# --- what a small model or another server gets wrong ------------------------


def test_malformed_argument_json_is_a_call_with_a_problem():
    body = _fixture("omlx_one_call")
    _message(body)["tool_calls"][0]["function"]["arguments"] = '{"kind": "workplace_type"'
    turn = read_turn(body, request=_request(), model="m")
    assert turn.stop_reason is StopReason.TOOL_USE
    [call] = turn.tool_calls
    assert call.problem is not None and call.problem.kind is CallProblemKind.MALFORMED_ARGUMENTS
    assert call.arguments == {} and call.raw_arguments == '{"kind": "workplace_type"'
    assert ToolResult.for_problem(call).is_error


def test_a_call_to_a_tool_never_offered_is_a_problem():
    body = _fixture("omlx_one_call")
    _message(body)["tool_calls"][0]["function"]["name"] = "run_shell"
    [call] = read_turn(body, request=_request(), model="m").tool_calls
    assert call.problem is not None and call.problem.kind is CallProblemKind.UNKNOWN_TOOL


def test_calls_without_ids_or_with_a_repeated_id_get_distinct_ids():
    body = _fixture("omlx_parallel_calls")
    calls = _message(body)["tool_calls"]
    del calls[0]["id"]
    body2 = _fixture("omlx_parallel_calls")
    calls2 = _message(body2)["tool_calls"]
    calls2[1]["id"] = calls2[0]["id"]
    for case in (body, body2):
        ids = [call.id for call in read_turn(case, request=_request(), model="m").tool_calls]
        assert len(set(ids)) == 2 and all(ids)


def test_text_where_a_call_was_required_is_flagged_not_raised():
    turn = read_turn(_fixture("omlx_final_answer"), request=_request(tool_choice="required"), model="m")
    assert turn.missing_tool_call and turn.stop_reason is StopReason.END and turn.text
    assert not read_turn(_fixture("omlx_final_answer"), request=_request(), model="m").missing_tool_call


def test_a_call_written_into_the_text_is_read_as_the_call():
    body = _fixture("omlx_final_answer")
    _message(body)["content"] = (
        'Let me check.\n<tool_call>\n{"name": "vocabulary_list", "arguments": {"kind": "location"}}\n</tool_call>'
    )
    turn = read_turn(body, request=_request(tool_choice="required"), model="m")
    [call] = turn.tool_calls
    assert call.from_text and call.name == "vocabulary_list" and dict(call.arguments) == {"kind": "location"}
    assert turn.text == "Let me check." and turn.stop_reason is StopReason.TOOL_USE
    assert not turn.missing_tool_call


def test_a_text_call_block_with_broken_json_is_a_problem_call():
    body = _fixture("omlx_final_answer")
    _message(body)["content"] = '<tool_call>{"name": "vocabulary_list", "arguments": {"kind": }</tool_call>'
    [call] = read_turn(body, request=_request(), model="m").tool_calls
    assert call.from_text and call.problem is not None
    assert call.problem.kind is CallProblemKind.MALFORMED_ARGUMENTS


def test_a_text_call_block_naming_no_offered_tool_stays_text():
    body = _fixture("omlx_final_answer")
    quoted = 'Tools look like <tool_call>{"name": "rm", "arguments": {}}</tool_call> in my format.'
    _message(body)["content"] = quoted
    turn = read_turn(body, request=_request(), model="m")
    assert turn.tool_calls == () and turn.text == quoted
    # With tools withheld, nothing in the text is a call either.
    _message(body)["content"] = '<tool_call>{"name": "vocabulary_list", "arguments": {}}</tool_call>'
    assert read_turn(body, request=_request(tool_choice="none"), model="m").tool_calls == ()


def test_thinking_left_in_the_content_moves_to_reasoning():
    body = _fixture("omlx_final_answer")
    _message(body)["content"] = "<think>The user wants workplace types.</think>\n\nOnsite, remote, hybrid."
    turn = read_turn(body, request=_request(), model="m")
    assert turn.text == "Onsite, remote, hybrid."
    assert turn.reasoning == "The user wants workplace types."


@pytest.mark.parametrize(
    ("change", "stop"),
    [
        ({"finish_reason": "length"}, StopReason.MAX_TOKENS),
        ({"finish_reason": "content_filter"}, StopReason.REFUSAL),
        ({"message": {"role": "assistant", "content": None, "refusal": "I can't help with that."}},
         StopReason.REFUSAL),
        ({"finish_reason": None}, StopReason.END),
    ],
)
def test_stop_reasons_are_normalized(change, stop):
    body = _fixture("omlx_final_answer")
    body["choices"][0].update(change)
    turn = read_turn(body, request=_request(), model="m")
    assert turn.stop_reason is stop
    if "message" in change:
        assert turn.text == "I can't help with that."


def test_a_call_cut_off_at_the_token_limit_stops_on_max_tokens_with_a_problem():
    body = _fixture("omlx_one_call")
    body["choices"][0]["finish_reason"] = "length"
    _message(body)["tool_calls"][0]["function"]["arguments"] = '{"kind": "workpl'
    turn = read_turn(body, request=_request(), model="m")
    assert turn.stop_reason is StopReason.MAX_TOKENS
    assert turn.tool_calls[0].problem is not None


@pytest.mark.parametrize("body", [{}, {"choices": []}, {"choices": ["x"]}, [], "text"])
def test_a_body_that_is_no_completion_is_a_validation_error(body):
    with pytest.raises(ToolTransportError) as caught:
        read_turn(body, request=_request(), model="m")
    assert caught.value.failure_class == "validation"


# --- the request body --------------------------------------------------------


def test_the_request_carries_the_conversation_in_the_format():
    good = ToolCall(id="call_1", name="vocabulary_list", arguments={"kind": "family"}, raw_arguments='{"kind":"family"}')
    bad_text = '{"kind": '
    arguments, raw, problem = parse_arguments(bad_text, name="vocabulary_list", offered=frozenset({"vocabulary_list"}))
    bad = ToolCall(id="call_2", name="vocabulary_list", arguments=arguments, raw_arguments=raw, problem=problem)
    request = ToolRequest(
        conversation=(
            QUESTION,
            AssistantMessage(text="Checking.", tool_calls=(good, bad)),
            ToolResults((ToolResult("call_1", '["data"]'), ToolResult.for_problem(bad))),
        ),
        tools=(VOCABULARY,),
        system="Answer from the tools.",
        tool_choice="required",
        parallel_tool_calls=False,
        max_tokens=256,
    )
    body = request_body(request, model="qwen", extra={"max_tokens": 32768, "temperature": 0.2})
    assert body["model"] == "qwen" and body["stream"] is False and body["temperature"] == 0.2
    assert body["max_tokens"] == 256, "the request's ceiling replaces the profile's"
    assert body["tool_choice"] == "required" and body["parallel_tool_calls"] is False
    assert body["tools"] == [{"type": "function", "function": {
        "name": "vocabulary_list", "description": VOCABULARY.description, "parameters": dict(VOCABULARY.parameters),
    }}]
    system, user, assistant, result_one, result_two = body["messages"]
    assert system == {"role": "system", "content": "Answer from the tools."}
    assert user == {"role": "user", "content": QUESTION.text}
    assert assistant["content"] == "Checking."
    assert [call["function"]["arguments"] for call in assistant["tool_calls"]] == ['{"kind":"family"}', "{}"], (
        "a parsed call goes back verbatim, a malformed one as an empty object"
    )
    assert result_one == {"role": "tool", "tool_call_id": "call_1", "content": '["data"]'}
    assert result_two["tool_call_id"] == "call_2" and result_two["content"].startswith("Error: ")
    assert bad_text in result_two["content"]


def test_without_tools_the_request_offers_none():
    body = request_body(ToolRequest(conversation=(QUESTION,)), model="m")
    assert "tools" not in body and "tool_choice" not in body and "parallel_tool_calls" not in body


# --- the transport, end to end over a mock server ---------------------------


@pytest.mark.asyncio
async def test_a_local_round_trip_sends_the_tool_result_back():
    endpoint = Endpoint(_fixture("omlx_one_call"), _fixture("omlx_final_answer"))
    async with endpoint.client() as client:
        transport = transport_for_tier(_local_tier(), thinking=False, http_client=client)
        conversation: list = [QUESTION]
        first = await transport.complete(conversation, tools=[VOCABULARY], system="Use the tools.")
        conversation += [first.message, ToolResults((ToolResult(first.tool_calls[0].id, '["onsite"]'),))]
        second = await transport.complete(conversation, tools=[VOCABULARY], system="Use the tools.")
    assert first.stop_reason is StopReason.TOOL_USE and second.stop_reason is StopReason.END
    request = endpoint.requests[0]
    assert str(request.url) == "http://127.0.0.1:8000/v1/chat/completions"
    assert request.headers["authorization"] == f"Bearer {LOCAL_KEY}"
    sent = endpoint.body(0)
    assert sent["chat_template_kwargs"] == {"enable_thinking": False} and "thinking_budget" not in sent
    replay = endpoint.body(1)["messages"]
    assert replay[2]["tool_calls"][0]["id"] == "call_976660ba"
    assert replay[3] == {"role": "tool", "tool_call_id": "call_976660ba", "content": '["onsite"]'}


@pytest.mark.asyncio
async def test_a_local_server_without_a_key_gets_no_authorization_header():
    endpoint = Endpoint(_fixture("omlx_final_answer"))
    tier = Tier(provider=LocalLLMProvider(LocalLLMProfile(id="localprofile2", name="Local", model="m")))
    async with endpoint.client() as client:
        await transport_for_tier(tier, http_client=client).complete([QUESTION])
    assert "authorization" not in endpoint.requests[0].headers


@pytest.mark.asyncio
async def test_a_cloud_openai_tier_uses_its_own_ceiling_field_and_key():
    profile = CloudLLMProfile(id="cloudprofile1", name="Cloud", provider="openai",
                              base_url="https://api.example.com/v1", model="gpt-test", enabled=True, api_key="sk-x")
    endpoint = Endpoint(_fixture("omlx_final_answer"))
    async with endpoint.client() as client:
        await transport_for_tier(Tier(provider=CloudLLMProvider(profile)), http_client=client).complete(
            [QUESTION], tools=[VOCABULARY], max_tokens=300
        )
    sent = endpoint.body(0)
    assert sent["max_completion_tokens"] == 300 and "max_tokens" not in sent
    assert "chat_template_kwargs" not in sent, "local server controls stay local"
    assert endpoint.requests[0].headers["authorization"] == "Bearer sk-x"
    assert str(endpoint.requests[0].url) == "https://api.example.com/v1/chat/completions"


def test_a_transport_never_shows_its_key():
    transport = transport_for_tier(_local_tier())
    assert LOCAL_KEY not in repr(transport) and LOCAL_KEY not in repr(transport._endpoint)


@pytest.mark.asyncio
async def test_a_slow_model_is_a_timeout_error():
    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(5)
        return httpx.Response(200, json=_fixture("omlx_final_answer"))

    async with httpx.AsyncClient(transport=httpx.MockTransport(slow)) as client:
        transport = transport_for_tier(_local_tier(), http_client=client)
        with pytest.raises(ToolTransportError) as caught:
            await transport.complete([QUESTION], timeout=0.05)
    assert caught.value.failure_class == "timeout" and caught.value.status_code == 504


@pytest.mark.asyncio
async def test_an_httpx_timeout_is_a_timeout_error():
    def stalled(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("read timed out", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(stalled)) as client:
        with pytest.raises(ToolTransportError) as caught:
            await transport_for_tier(_local_tier(), http_client=client).complete([QUESTION])
    assert caught.value.failure_class == "timeout"


@pytest.mark.asyncio
async def test_cancelling_the_caller_cancels_the_http_request():
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
        task = asyncio.create_task(transport_for_tier(_local_tier(), http_client=client).complete([QUESTION]))
        await asyncio.wait_for(started.wait(), 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert cancelled.is_set(), "the request in flight was cancelled, not left running"


@pytest.mark.asyncio
async def test_a_transport_closes_the_client_it_opened_also_when_cancelled(monkeypatch):
    closed: list[bool] = []
    started = asyncio.Event()

    async def hanging(request: httpx.Request) -> httpx.Response:
        started.set()
        await asyncio.sleep(3600)
        return httpx.Response(200, json={})

    class Tracked(httpx.AsyncClient):
        async def aclose(self) -> None:
            closed.append(True)
            await super().aclose()

    monkeypatch.setattr(transport_module, "make_client",
                        lambda timeout: Tracked(transport=httpx.MockTransport(hanging), timeout=timeout))
    task = asyncio.create_task(transport_for_tier(_local_tier()).complete([QUESTION]))
    await asyncio.wait_for(started.wait(), 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert closed == [True]


@pytest.mark.asyncio
async def test_an_unreachable_server_is_a_connection_error():
    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(refused)) as client:
        with pytest.raises(ToolTransportError) as caught:
            await transport_for_tier(_local_tier(), http_client=client).complete([QUESTION])
    assert caught.value.failure_class == "connection" and LOCAL_KEY not in str(caught.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "failure_class", "detail", "retry_after"),
    [
        (httpx.Response(429, headers={"retry-after": "7"}, json={"error": {"message": "slow down"}}),
         "rate_limited", "slow down", 7.0),
        (httpx.Response(400, json={"error": {"message": "prompt is longer than the context"}}),
         "http_error", "longer than the context", None),
        (httpx.Response(500, json={"detail": "model crashed"}), "http_error", "model crashed", None),
        (httpx.Response(502, text="<html>bad gateway</html>"), "http_error", "HTTP 502", None),
        (httpx.Response(200, text="not json"), "validation", "not JSON", None),
    ],
)
async def test_failed_requests_are_typed(response, failure_class, detail, retry_after):
    endpoint = Endpoint(response)
    async with endpoint.client() as client:
        with pytest.raises(ToolTransportError) as caught:
            await transport_for_tier(_local_tier(), http_client=client).complete([QUESTION])
    assert caught.value.failure_class == failure_class and detail in str(caught.value)
    assert caught.value.retry_after == retry_after


@pytest.mark.asyncio
async def test_a_conversation_no_format_can_send_never_reaches_the_server():
    endpoint = Endpoint()
    unanswered = AssistantMessage(tool_calls=(ToolCall(id="c1", name="vocabulary_list"),))
    async with endpoint.client() as client:
        with pytest.raises(ValueError, match="not answered"):
            await transport_for_tier(_local_tier(), http_client=client).complete(
                [QUESTION, unanswered, UserMessage("well?")]
            )
    assert endpoint.requests == []


def test_recorded_fixtures_carry_no_key():
    for path in FIXTURES.glob("*.json"):
        text = path.read_text()
        assert "api_key" not in text and "Bearer" not in text, path.name


def test_a_call_a_runner_built_goes_out_with_its_arguments_in_both_formats():
    from tracker.intelligence.tool_calls import anthropic_format

    call = ToolCall(id="call_7", name="vocabulary_list", arguments={"kind": "family"})
    request = ToolRequest(
        conversation=(QUESTION, AssistantMessage(tool_calls=(call,)), ToolResults((ToolResult("call_7", "[]"),))),
        tools=(VOCABULARY,),
    )
    sent = request_body(request, model="m")["messages"][1]["tool_calls"][0]["function"]["arguments"]
    assert json.loads(sent) == {"kind": "family"}
    other = anthropic_format.request_body(request, model="m")["messages"][1]["content"][0]["input"]
    assert other == json.loads(sent)


@pytest.mark.asyncio
async def test_a_redirect_is_never_followed_with_the_conversation():
    elsewhere: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "collector.example":
            elsewhere.append(request)
            return httpx.Response(200, json=_fixture("omlx_final_answer"))
        return httpx.Response(307, headers={"location": "https://collector.example/v1/chat/completions"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        with pytest.raises(ToolTransportError) as caught:
            await transport_for_tier(_local_tier(), http_client=client).complete([QUESTION])
    assert caught.value.status_code == 307 and elsewhere == []


def test_an_unclosed_call_block_with_a_long_tail_returns_promptly():
    import time

    body = _fixture("omlx_final_answer")
    _message(body)["content"] = "<tool_call>" + " " * 20_000
    started = time.perf_counter()
    turn = read_turn(body, request=_request(), model="m")
    assert time.perf_counter() - started < 0.5
    assert turn.tool_calls == ()


def test_text_around_and_between_call_blocks_is_kept_in_order():
    body = _fixture("omlx_final_answer")
    block = '<tool_call>{"name": "vocabulary_list", "arguments": {"kind": "%s"}}</tool_call>'
    quoted = '<tool_call>{"name": "rm", "arguments": {}}</tool_call>'
    _message(body)["content"] = f"First {block % 'family'} then {quoted} and {block % 'track'} done"
    turn = read_turn(body, request=_request(), model="m")
    assert [dict(call.arguments) for call in turn.tool_calls] == [{"kind": "family"}, {"kind": "track"}]
    assert turn.text == f"First  then {quoted} and  done"


@pytest.mark.parametrize("choice", [{}, {"message": None, "finish_reason": "stop"}, {"message": "hi"}])
def test_a_choice_without_a_message_is_a_validation_error_not_an_empty_answer(choice):
    with pytest.raises(ToolTransportError) as caught:
        read_turn({"choices": [choice]}, request=_request(), model="m")
    assert caught.value.failure_class == "validation"
