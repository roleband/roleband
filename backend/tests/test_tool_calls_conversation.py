"""The provider-neutral conversation: what a runner may send, and how a call
the model got wrong becomes something to feed back instead of a crash."""

from __future__ import annotations

import json

import pytest

from tracker.intelligence.tool_calls import (
    AssistantMessage,
    CallProblemKind,
    ToolCall,
    ToolDefinition,
    ToolResult,
    ToolResults,
    UserMessage,
)
from tracker.intelligence.tool_calls.conversation import check_conversation, parse_arguments

OFFERED = frozenset({"vocabulary_list"})


def _call(call_id: str = "c1") -> ToolCall:
    return ToolCall(id=call_id, name="vocabulary_list", arguments={"kind": "family"}, raw_arguments='{"kind": "family"}')


def test_a_complete_exchange_passes():
    check_conversation([
        UserMessage("which families?"),
        AssistantMessage(tool_calls=(_call("a"), _call("b"))),
        ToolResults((ToolResult("b", "[]"), ToolResult("a", "[]"))),
        AssistantMessage(text="none yet"),
        UserMessage("thanks"),
    ])


@pytest.mark.parametrize(
    ("conversation", "complaint"),
    [
        ([], "at least one message"),
        ([AssistantMessage(text="hi")], "opens with a user message"),
        ([UserMessage("q"), AssistantMessage(tool_calls=(_call("a"),)), UserMessage("again")], "not answered"),
        ([UserMessage("q"), AssistantMessage(tool_calls=(_call("a"),))], "not answered"),
        ([UserMessage("q"), AssistantMessage(tool_calls=(_call("a"),)), ToolResults((ToolResult("z", "x"),))],
         "the calls were"),
        ([UserMessage("q"), AssistantMessage(tool_calls=(_call("a"), _call("a"))),
          ToolResults((ToolResult("a", "x"), ToolResult("a", "x")))], "share an id"),
        ([UserMessage("q"), ToolResults((ToolResult("a", "x"),))], "the calls were"),
    ],
)
def test_a_conversation_no_format_can_send_is_refused_before_sending(conversation, complaint):
    with pytest.raises(ValueError, match=complaint):
        check_conversation(conversation)


def test_two_tools_with_one_name_are_refused():
    tool = ToolDefinition("vocabulary_list", "List values.", {"type": "object", "properties": {}})
    with pytest.raises(ValueError, match="share a name"):
        check_conversation([UserMessage("q")], [tool, tool])


@pytest.mark.parametrize("name", ["opportunities.search", "", "a" * 65, "has space"])
def test_a_tool_name_either_format_refuses_is_refused(name):
    with pytest.raises(ValueError, match="tool name"):
        ToolDefinition(name, "Does a thing.", {"type": "object"})


def test_parameters_must_describe_an_object():
    with pytest.raises(ValueError, match="type object"):
        ToolDefinition("list_things", "Lists.", {"type": "array"})


def test_arguments_text_reads_into_an_object():
    arguments, text, problem = parse_arguments('{"kind": "family"}', name="vocabulary_list", offered=OFFERED)
    assert (arguments, text, problem) == ({"kind": "family"}, '{"kind": "family"}', None)


@pytest.mark.parametrize(
    ("raw", "detail"),
    [
        ('{"kind": "family"', "invalid JSON"),
        ("kind=family", "invalid JSON"),
        ('["family"]', "list, not an object"),
        ('"family"', "str, not an object"),
    ],
)
def test_malformed_arguments_are_a_problem_not_an_error(raw, detail):
    arguments, text, problem = parse_arguments(raw, name="vocabulary_list", offered=OFFERED)
    assert arguments == {}
    assert text == raw, "the model's own text is kept to quote back to it"
    assert problem is not None and problem.kind is CallProblemKind.MALFORMED_ARGUMENTS
    assert detail in problem.detail


@pytest.mark.parametrize("raw", [["family"], 7, True])
def test_parsed_arguments_that_are_not_an_object_are_a_problem(raw):
    arguments, text, problem = parse_arguments(raw, name="vocabulary_list", offered=OFFERED)
    assert arguments == {} and text == json.dumps(raw)
    assert problem is not None and problem.kind is CallProblemKind.MALFORMED_ARGUMENTS


def test_empty_arguments_are_an_empty_object():
    assert parse_arguments("", name="vocabulary_list", offered=OFFERED) == ({}, "{}", None)
    assert parse_arguments(None, name="vocabulary_list", offered=OFFERED) == ({}, "{}", None)


def test_a_tool_that_was_not_offered_is_a_problem_naming_the_offered_ones():
    _, _, problem = parse_arguments("{}", name="delete_everything", offered=OFFERED)
    assert problem is not None and problem.kind is CallProblemKind.UNKNOWN_TOOL
    assert "vocabulary_list" in problem.detail


def test_the_answer_to_a_malformed_call_quotes_what_the_model_sent():
    raw = '{"kind": "family"'
    arguments, text, problem = parse_arguments(raw, name="vocabulary_list", offered=OFFERED)
    call = ToolCall(id="c9", name="vocabulary_list", arguments=arguments, raw_arguments=text, problem=problem)
    result = ToolResult.for_problem(call)
    assert result.call_id == "c9" and result.is_error
    assert raw in result.content and "JSON object" in result.content


def test_the_answer_to_an_unknown_tool_names_the_tools_offered():
    _, text, problem = parse_arguments("{}", name="shell", offered=OFFERED)
    result = ToolResult.for_problem(ToolCall(id="c1", name="shell", raw_arguments=text, problem=problem))
    assert "no tool named 'shell'" in result.content and "vocabulary_list" in result.content


def test_a_call_without_a_problem_has_nothing_to_report():
    with pytest.raises(ValueError, match="no problem"):
        ToolResult.for_problem(_call())


@pytest.mark.parametrize("raw", ['{"n": ' + "9" * 5000 + "}", "[" * 100_000 + "]" * 100_000])
def test_json_no_reader_should_accept_is_a_problem_not_an_error(raw):
    arguments, _, problem = parse_arguments(raw, name="vocabulary_list", offered=OFFERED)
    assert arguments == {}
    assert problem is not None and problem.kind is CallProblemKind.MALFORMED_ARGUMENTS
