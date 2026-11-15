"""One tool-calling round trip against a model server on this computer.

    ROLEBAND_SMOKE_LOCAL_API_KEY=... .venv/bin/python -m scripts.smoke_model_tools \
        --model MODEL [--base-url http://127.0.0.1:8000/v1] [--record DIR]

Offers the model the real `vocabulary_list` tool, expects it to call it, sends
back a canned result and expects a final answer. Prints each turn's stop
reason, calls and tokens; exits 1 when the model never called the tool or
never answered. `--record` writes each raw response body to DIR, for test
fixtures. The address must be loopback (`LocalLLMProfile` refuses anything
else) and the key, if the server needs one, comes only from the environment.
Nothing reaches a database.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import cast

import httpx

from tracker.agents.operations.catalog import CATALOG
from tracker.agents.tool_definitions import tool_definition
from tracker.intelligence.provider import IntelligenceProvider
from tracker.intelligence.providers.local import LocalLLMProvider
from tracker.intelligence.router import Tier
from tracker.intelligence.tool_calls import (
    StopReason,
    ToolResult,
    ToolResults,
    Turn,
    UserMessage,
    transport_for_tier,
)
from tracker.local_llm.models import LocalLLMParameters, LocalLLMProfile

KEY_VARIABLE = "ROLEBAND_SMOKE_LOCAL_API_KEY"
QUESTION = "Which workplace types can I filter job searches by? Use the tool to find out."
CANNED_RESULT = json.dumps(
    {"values": [{"value": "onsite", "open_roles": 812}, {"value": "remote", "open_roles": 241},
                {"value": "hybrid", "open_roles": 377}]}
)


def _describe(label: str, turn: Turn) -> None:
    calls = [
        {"name": call.name, "arguments": dict(call.arguments), "problem": call.problem.kind if call.problem else None,
         "from_text": call.from_text}
        for call in turn.tool_calls
    ]
    print(f"{label}: stop={turn.stop_reason.value} raw_stop={turn.raw_stop} model={turn.model}")
    print(f"  tokens in={turn.usage.input_tokens} out={turn.usage.output_tokens} wall_ms={turn.usage.wall_time_ms}")
    if calls:
        print(f"  calls={json.dumps(calls)}")
    if turn.text:
        print(f"  text={turn.text[:400]!r}")


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--thinking", action="store_true", help="leave the model's thinking on")
    parser.add_argument("--record", type=Path, help="write each raw response body here")
    args = parser.parse_args(argv)

    profile = LocalLLMProfile(
        id="smoke-local", name="Smoke", provider="omlx", base_url=args.base_url, model=args.model,
        api_key=os.environ.get(KEY_VARIABLE) or None,
        parameters=LocalLLMParameters(max_tokens=2048, temperature=0, timeout_seconds=300),
    )
    descriptor = CATALOG.get("vocabulary.list")
    assert descriptor is not None
    tool = tool_definition(descriptor)
    bodies: list[dict] = []

    async def keep(response: httpx.Response) -> None:
        await response.aread()
        bodies.append(response.json())

    async with httpx.AsyncClient(timeout=300, event_hooks={"response": [keep]}) as client:
        transport = transport_for_tier(Tier(provider=cast(IntelligenceProvider, LocalLLMProvider(profile))), thinking=args.thinking,
                                       http_client=client)
        conversation: list = [UserMessage(QUESTION)]
        first = await transport.complete(conversation, tools=[tool], system="You answer from the tools you are given.")
        _describe("turn 1", first)
        if first.stop_reason is not StopReason.TOOL_USE or not first.tool_calls:
            print("FAIL: the model did not call the tool", file=sys.stderr)
            return 1
        conversation.append(first.message)
        conversation.append(ToolResults(tuple(
            ToolResult.for_problem(call) if call.problem else ToolResult(call.id, CANNED_RESULT)
            for call in first.tool_calls
        )))
        second = await transport.complete(conversation, tools=[tool], system="You answer from the tools you are given.")
        _describe("turn 2", second)

    if args.record:
        args.record.mkdir(parents=True, exist_ok=True)
        for index, body in enumerate(bodies, start=1):
            (args.record / f"turn{index}.json").write_text(json.dumps(body, indent=2) + "\n")
    total_in = sum(turn.usage.input_tokens or 0 for turn in (first, second))
    total_out = sum(turn.usage.output_tokens or 0 for turn in (first, second))
    print(f"total tokens in={total_in} out={total_out}")
    if second.stop_reason is not StopReason.END or not second.text:
        print("FAIL: no final answer after the tool result", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
